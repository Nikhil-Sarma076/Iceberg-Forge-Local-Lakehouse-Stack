"""
Application Configuration
=========================
Centralized settings management using Pydantic Settings.
Reads configuration from environment variables.
"""
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Service configuration parameters.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Configuration
    APP_NAME: str = "Local Iceberg Ingestion Toolkit"
    APP_VERSION: str = "1.0.0"
    API_V1_STR: str = "/v1"
    DEBUG: bool = False
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # MinIO / Object Storage
    MINIO_ENDPOINT: str = "http://minio:9000"
    MINIO_ACCESS_KEY: str = "admin"
    MINIO_SECRET_KEY: str = "minioadmin123"
    MINIO_BUCKET: str = "iceberg-warehouse"
    MINIO_REGION: str = "us-east-1"

    # Iceberg Configuration
    ICEBERG_WAREHOUSE: str = "s3://iceberg-warehouse/warehouse"
    ICEBERG_CATALOG_TYPE: str = "rest"
    ICEBERG_CATALOG_URI: str = "http://rest:8181"
    ICEBERG_NAMESPACE: str = "default"

    # AWS / S3 (For PyIceberg and REST catalog mapping)
    AWS_ACCESS_KEY_ID: str = "admin"
    AWS_SECRET_ACCESS_KEY: str = "minioadmin123"
    AWS_REGION: str = "us-east-1"
    AWS_S3_ENDPOINT: str = "http://minio:9000"
    AWS_S3_PATH_STYLE_ACCESS: bool = True

    # Trino Configuration
    TRINO_HOST: str = "trino"
    TRINO_PORT: int = 8080
    TRINO_CATALOG: str = "iceberg"
    TRINO_SCHEMA: str = "default"

    # Input Data Directory
    SAMPLE_DATA_DIR: str = str(Path(__file__).resolve().parent.parent.parent / "sample-data")

# Global settings singleton
settings = Settings()
