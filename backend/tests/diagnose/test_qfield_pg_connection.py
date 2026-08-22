"""QField packaging: PostgreSQL connection for ogr2ogr."""

from __future__ import annotations

from app.modules.diagnose.services import qfield_sync
from app.shared.config import settings


def test_ogr_pg_connection_decodes_password_and_uses_pgpassword(monkeypatch):
    monkeypatch.setattr(
        settings,
        "database_url",
        "postgresql://postgres:PG%26Usz3SE%25927%409tKUjdy%26@127.0.0.1:5432/ddaapp",
    )

    dsn, env = qfield_sync._ogr_pg_connection()

    assert "password=" not in dsn
    assert "dbname=ddaapp" in dsn
    assert "host=127.0.0.1" in dsn
    assert "port=5432" in dsn
    assert "user=postgres" in dsn
    assert env["PGPASSWORD"] == "PG&Usz3SE%927@9tKUjdy&"


def test_ogr_pg_connection_plain_password(monkeypatch):
    monkeypatch.setattr(
        settings,
        "database_url",
        "postgresql://geofield:geofield@localhost:5432/dda_product",
    )

    dsn, env = qfield_sync._ogr_pg_connection()

    assert env["PGPASSWORD"] == "geofield"
    assert "dbname=dda_product" in dsn
    assert "user=geofield" in dsn
