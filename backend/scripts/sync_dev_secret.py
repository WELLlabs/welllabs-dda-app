#!/usr/bin/env python3
"""Sync dev app-config secret from local backend/.env (beta + Google OAuth)."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import boto3

DEV_SECRET_ARN = os.environ.get(
    "APP_CONFIG_SECRET_ARN",
    "arn:aws:secretsmanager:ap-south-1:590183894970:secret:well-labs-dda-product/dev/app-config-0LuTAI",
)
BETA_ORIGIN = "https://beta.welllabs.org"
REGION = os.environ.get("AWS_DEFAULT_REGION", "ap-south-1")
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def _parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        key = key.strip()
        value = raw.strip().strip('"').strip("'")
        values[key] = value
    return values


def main() -> int:
    client = boto3.client("secretsmanager", region_name=REGION)
    current = client.get_secret_value(SecretId=DEV_SECRET_ARN)
    config = json.loads(current["SecretString"])
    local = _parse_env(ENV_PATH)

    config["FRONTEND_ORIGIN"] = BETA_ORIGIN
    config.setdefault("SESSION_COOKIE_SECURE", "true")

    for key in ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"):
        if local.get(key):
            config[key] = local[key]

    client.put_secret_value(
        SecretId=DEV_SECRET_ARN,
        SecretString=json.dumps(config, indent=2),
    )

    oauth_id = config.get("GOOGLE_OAUTH_CLIENT_ID", "")
    masked = oauth_id[:20] + "..." if len(oauth_id) > 20 else oauth_id
    print(f"Updated dev secret FRONTEND_ORIGIN={BETA_ORIGIN!r}")
    print(f"GOOGLE_OAUTH_CLIENT_ID={masked}")
    print(f"Keys preserved: {len(config)} total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
