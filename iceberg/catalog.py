"""
Iceberg Catalog Factory
=======================
Initializes and manages the Apache Iceberg REST catalog connection
backed by MinIO (S3).
"""
import os
from typing import Any, Dict, Optional

from pyiceberg.catalog import Catalog, load_catalog
from app.config.settings import settings

def build_catalog_properties(
    warehouse: Optional[str] = None,
    s3_endpoint: Optional[str] = None,
    s3_access_key: Optional[str] = None,
    s3_secret_key: Optional[str] = None,
    catalog_uri: Optional[str] = None,
    catalog_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Constructs the PyIceberg catalog configuration properties dictionary.
    Uses centralized settings singleton.
    """
    endpoint = s3_endpoint or settings.AWS_S3_ENDPOINT
    access_key = s3_access_key or settings.AWS_ACCESS_KEY_ID
    secret_key = s3_secret_key or settings.AWS_SECRET_ACCESS_KEY
    wh = warehouse or settings.ICEBERG_WAREHOUSE
    cat_type = catalog_type or settings.ICEBERG_CATALOG_TYPE
    cat_uri = catalog_uri or settings.ICEBERG_CATALOG_URI
    region = settings.AWS_REGION

    properties: Dict[str, Any] = {
        "type": cat_type,
        "uri": cat_uri,
        "warehouse": wh,
        "s3.endpoint": endpoint,
        "s3.access-key-id": access_key,
        "s3.secret-access-key": secret_key,
        "s3.region": region,
        "s3.path-style-access": str(settings.AWS_S3_PATH_STYLE_ACCESS).lower(),
        "s3.ssl.enabled": "false",
        "py-io-impl": "pyiceberg.io.pyarrow.PyArrowFileIO",
    }
    return properties

def get_iceberg_catalog(
    name: str = "default",
    properties: Optional[Dict[str, Any]] = None,
) -> Catalog:
    """
    Initializes and returns a PyIceberg Catalog instance.
    """
    if properties is None:
        properties = build_catalog_properties()
        
    return load_catalog(name, **properties)
