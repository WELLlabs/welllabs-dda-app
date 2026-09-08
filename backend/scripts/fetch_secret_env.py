#!/usr/bin/env python3
"""Fetch AWS Secrets Manager app-config JSON and write a local .env file."""

from __future__ import annotations

import argparse
import json
import os
import sys

import boto3


def _escape(value: object) -> str:
    s = "" if value is None else str(value)
    return (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("$", "\\$")
        .replace("`", "\\`")
    )


def secret_to_env_lines(config: dict[str, object]) -> list[str]:
    return [f'{key}="{_escape(value)}"' for key, value in sorted(config.items())]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--secret-id",
        default=os.environ.get(
            "APP_CONFIG_SECRET_ARN",
            "well-labs-dda-product/prod/app-config",
        ),
        help="Secrets Manager secret id or ARN",
    )
    parser.add_argument(
        "--output",
        default="backend/.env.prod",
        help="Output .env path relative to repo root or absolute",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_DEFAULT_REGION", "ap-south-1"),
    )
    args = parser.parse_args(argv)

    client = boto3.client("secretsmanager", region_name=args.region)
    resp = client.get_secret_value(SecretId=args.secret_id)
    config = json.loads(resp["SecretString"])

    out_path = args.output
    if not os.path.isabs(out_path):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        out_path = os.path.join(repo_root, out_path)

    header = (
        f"# Fetched from AWS Secrets Manager: {args.secret_id}\n"
        f"# DO NOT COMMIT — local reference only\n"
    )
    body = "\n".join(secret_to_env_lines(config)) + "\n"
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(header + body)

    print(f"Wrote {len(config)} keys to {out_path}")
    print(f"Keys: {', '.join(sorted(config.keys()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
