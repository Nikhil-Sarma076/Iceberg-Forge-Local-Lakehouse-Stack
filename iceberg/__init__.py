"""
Iceberg Module
==============
Provides Apache Iceberg schema conversion, catalog initialization,
and table operations using PyIceberg and PyArrow.
"""

from iceberg.catalog import get_iceberg_catalog
from iceberg.schema import arrow_to_iceberg_schema, infer_arrow_schema_from_file
from iceberg.tables import (
    IcebergTableManager,
    TableMetadataSummary,
    TableDetailMetadata,
)

__all__ = [
    "get_iceberg_catalog",
    "arrow_to_iceberg_schema",
    "infer_arrow_schema_from_file",
    "IcebergTableManager",
    "TableMetadataSummary",
    "TableDetailMetadata",
]
