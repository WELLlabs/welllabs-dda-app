from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://geofield:geofield@localhost:5432/dda_product"
    titiler_url: str = "http://localhost:8000"
    titiler_public_url: str = "http://localhost:8000"
    aws_s3_bucket: str = ""
    aws_default_region: str = "us-east-1"
    cog_layers: str = "lulc.cog.tif"
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

    frontend_origin: str = "http://localhost:5173"
    session_cookie_name: str = "dda_session"
    session_ttl_days: int = 30
    session_cookie_secure: bool = False

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
