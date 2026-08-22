from urllib.parse import urlparse

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://geofield:geofield@localhost:5432/dda_product"
    titiler_url: str = "http://localhost:8000"
    titiler_public_url: str = "http://localhost:8000"
    aws_s3_bucket: str = ""
    aws_default_region: str = "us-east-1"
    cog_layers: str = "lulc.cog.tif"
    vector_layers: str = ""
    watersheds_fgb_key: str = "watersheds.fbg"
    qfield_cloud_url: str = "https://app.qfield.cloud/api/v1/"
    qfield_project_name: str = "geo-field-pipeline"
    postgis_public_host: str = "localhost"
    postgis_public_port: int = 5432
    packages_dir: str = "/app/packages"
    qfield_raster_min_zoom: int = 8
    qfield_raster_max_zoom: int = 16
    qfield_raster_max_pixels: int = 2048

    # ODK Central configuration
    odk_base_url: str = ""
    odk_username: str = ""
    odk_password: str = ""
    # All MEL intervention forms are published into this single ODK project.
    odk_project_id: int | None = None

    # Metabase signed embedding
    metabase_embed_secret_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "METABASE_EMBED_SECRET_KEY",
            "METABASE_EMBEDD_SECRET_KEY",
        ),
    )
    # Browser-reachable Metabase URL — returned to the frontend so it can load
    # embed.js and point the web component at the instance.
    metabase_public_url: str = "http://localhost:3000"

    # Browser origin for CORS / cookies (no path). Production example: https://ai.welllabs.org
    frontend_origin: str = "http://localhost:5173"
    # SvelteKit kit.paths.base in production (empty locally). Example: /wst
    frontend_base_path: str = ""
    # Browser API segment under frontend_base_path (/backend avoids CF Worker 1101 on /wst/api POST)
    api_public_segment: str = "/backend"
    session_cookie_name: str = "dda_session"
    session_ttl_days: int = 30
    session_cookie_secure: bool = False

    # FastAPI Users / JWT
    auth_jwt_secret: str = "change-me-in-production"
    # Internal API URL for server-side tooling — browsers should use the Vite
    # origin (5173/5174) and the /api proxy, not this URL directly.
    api_public_url: str = "http://localhost:8080"

    # Brevo transactional email (optional in local — sends are skipped if unset)
    brevo_api_key: str = ""
    brevo_sender_email: str = ""
    brevo_sender_name: str = "Water Security Tool"

    # Google OAuth (optional — Google button disabled if unset)
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}

    @field_validator("odk_project_id", mode="before")
    @classmethod
    def empty_odk_project_id(cls, value):
        if value == "" or value is None:
            return None
        return value

    @field_validator("frontend_base_path", mode="before")
    @classmethod
    def normalize_base_path(cls, value):
        if value is None or value == "":
            return ""
        text = str(value).strip()
        if not text or text == "/":
            return ""
        if not text.startswith("/"):
            text = f"/{text}"
        return text.rstrip("/")

    @property
    def public_app_origin(self) -> str:
        """Scheme + host only (for CORS / Origin comparisons)."""
        parsed = urlparse(self.frontend_origin)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return self.frontend_origin.rstrip("/")

    @property
    def public_app_base(self) -> str:
        """Public URL prefix for email links and redirects (origin + optional /wst)."""
        return f"{self.public_app_origin}{self.frontend_base_path}"

    @property
    def api_public_prefix(self) -> str:
        """Browser-visible API path prefix (e.g. /wst/backend in production)."""
        seg = self.api_public_segment if self.api_public_segment.startswith("/") else f"/{self.api_public_segment}"
        if self.frontend_base_path:
            return f"{self.frontend_base_path}{seg.rstrip('/')}"
        return seg.rstrip("/") or "/backend"

    @property
    def api_public_origin(self) -> str:
        """Absolute public API base URL for OAuth redirect URIs."""
        return f"{self.public_app_origin}{self.api_public_prefix}"

    @property
    def cors_origins(self) -> list[str]:
        """Browser origins allowed to call the API with credentials.

        Local Vite may bind 5173 or fall back to 5174 — allow both (and 127.0.0.1).
        """
        origins = [self.public_app_origin]
        for host in ("localhost", "127.0.0.1"):
            for port in (5173, 5174):
                origin = f"http://{host}:{port}"
                if origin not in origins:
                    origins.append(origin)
        return origins


settings = Settings()
