#!/usr/bin/env python3
"""Update dev app-config secret for beta.welllabs.org (Secrets Manager only)."""

from __future__ import annotations

import json
import os
import sys

import boto3

DEV_SECRET_ARN = os.environ.get(
    "APP_CONFIG_SECRET_ARN",
    "arn:aws:secretsmanager:ap-south-1:590183894970:secret:well-labs-dda-product/dev/app-config-0LuTAI",
)
BETA_ORIGIN = "https://beta.welllabs.org"
REGION = os.environ.get("AWS_DEFAULT_REGION", "ap-south-1")


def main() -> int:
    client = boto3.client("secretsmanager", region_name=REGION)
    current = client.get_secret_value(SecretId=DEV_SECRET_ARN)
    config = json.loads(current["SecretString"])

    old_origin = config.get("FRONTEND_ORIGIN", "")
    config["FRONTEND_ORIGIN"] = BETA_ORIGIN
    config.setdefault("SESSION_COOKIE_SECURE", "true")

    client.put_secret_value(
        SecretId=DEV_SECRET_ARN,
        SecretString=json.dumps(config, indent=2),
    )

    print(f"Updated secret: FRONTEND_ORIGIN {old_origin!r} -> {BETA_ORIGIN!r}")
    print(f"Keys preserved: {len(config)} total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
