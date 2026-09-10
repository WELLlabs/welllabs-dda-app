#!/usr/bin/env python3
"""Sync selected fields from local backend/.env into the **dev** app-config secret.

Updates beta FRONTEND_ORIGIN, Google OAuth, and diagnose layer enablement
(COG_LAYERS / VECTOR_LAYERS / WATERSHEDS_FGB_KEY) so beta matches local layer config.

Does NOT touch the prod secret.
"""

from __future__ import annotations

import json
import os
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

# Layer / OAuth keys copied from local .env when present.
SYNC_KEYS = (
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "COG_LAYERS",
    "VECTOR_LAYERS",
    "WATERSHEDS_FGB_KEY",
)

# Hierarchy stack — always loaded via preview_context, never via VECTOR_LAYERS.
HIERARCHY_KEYS = (
    "vector/Basin.fgb",
    "vector/Sub Basins of india.fgb",
    "vector/india_basins_level_7.fgb",
    "vector/india_rivers_level_12.fgb",
)


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


def _layer_filenames(csv_value: str) -> list[str]:
    text = str(csv_value or "").strip()
    if not text or text.lower() in {"*", "all"}:
        return ["(all layers.yaml keys)"]
    return [part.strip().rsplit("/", 1)[-1] for part in text.split(",") if part.strip()]


def main() -> int:
    client = boto3.client("secretsmanager", region_name=REGION)
    current = client.get_secret_value(SecretId=DEV_SECRET_ARN)
    config = json.loads(current["SecretString"])
    local = _parse_env(ENV_PATH)

    config["FRONTEND_ORIGIN"] = BETA_ORIGIN
    config.setdefault("SESSION_COOKIE_SECURE", "true")

    updated: list[str] = []
    for key in SYNC_KEYS:
        if local.get(key):
            config[key] = local[key]
            updated.append(key)

    client.put_secret_value(
        SecretId=DEV_SECRET_ARN,
        SecretString=json.dumps(config, indent=2),
    )

    oauth_id = config.get("GOOGLE_OAUTH_CLIENT_ID", "")
    masked = oauth_id[:20] + "..." if len(oauth_id) > 20 else oauth_id
    print(f"Updated DEV secret only (prod untouched) FRONTEND_ORIGIN={BETA_ORIGIN!r}")
    print(f"GOOGLE_OAUTH_CLIENT_ID={masked}")
    print(f"Synced from .env: {', '.join(updated) or '(none)'}")
    print(f"COG_LAYERS: {_layer_filenames(str(config.get('COG_LAYERS') or ''))}")
    print(f"VECTOR_LAYERS: {_layer_filenames(str(config.get('VECTOR_LAYERS') or ''))}")
    print("Hierarchy (not in VECTOR_LAYERS):")
    for key in HIERARCHY_KEYS:
        print(f"  - {key}")
    print(f"WATERSHEDS_FGB_KEY (L12 micro): {config.get('WATERSHEDS_FGB_KEY')}")
    print(f"Keys preserved: {len(config)} total")
    print("Note: API must restart / redeploy to load the new secret into the container.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
