"""
Pydantic Models
===============
Request and response data transfer objects for Iceberg table ingestion & inspection.
"""

import re
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


TABLE_NAME_REGEX = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    version: Optional[str] = "1.0.0"


class CreateTableRequest(BaseModel):
    """Payload for creating a new Iceberg table from a file."""
    name: str = Field(
        ...,
        description="Name of the Iceberg table to create (alphanumeric and underscores).",
        examples=["sales", "events_log", "products_v2"],
    )
    file: str = Field(
        ...,
        description="Path or filename of the dataset (relative to sample-data or absolute).",
        examples=["sales.csv", "events.json", "products.csv"],
    )
    namespace: Optional[str] = Field(
        default="default",
        description="Iceberg catalog namespace (schema). Defaults to 'default'.",
    )

    @field_validator("name")
    @classmethod
    def validate_table_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Table name must not be empty.")
        if not TABLE_NAME_REGEX.match(cleaned):
            raise ValueError(
                f"Invalid table name '{cleaned}'. Table names must start with a letter, "
                "contain only letters, digits, and underscores, and be at most 64 characters long."
            )
        return cleaned.lower()

    @field_validator("file")
    @classmethod
    def validate_file_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("File path must not be empty.")
        return cleaned


class AppendTableRequest(BaseModel):
    """Payload for appending records to an existing Iceberg table."""
    file: str = Field(
        ...,
        description="Path or filename of the dataset to append.",
        examples=["orders_append.csv", "batch_2.json"],
    )
    namespace: Optional[str] = Field(
        default="default",
        description="Iceberg catalog namespace. Defaults to 'default'.",
    )

    @field_validator("file")
    @classmethod
    def validate_file_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("File path must not be empty.")
        return cleaned


class WriteMode(str, Enum):
    """Supported write modes for updating table data."""
    APPEND = "append"
    OVERWRITE = "overwrite"
    MERGE = "merge"


class WriteTableRequest(BaseModel):
    """Payload for writing data to an existing table with a chosen mode."""
    file: str = Field(
        ...,
        description="Path or filename of the dataset to write.",
        examples=["orders_append.csv", "updates.json"],
    )
    mode: WriteMode = Field(
        default=WriteMode.APPEND,
        description="Write mode: append (add rows), overwrite (replace all), or merge (upsert on merge_key).",
    )
    merge_key: Optional[str] = Field(
        default=None,
        description="Key column for merge/upsert. Required when mode is 'merge'.",
    )
    namespace: Optional[str] = Field(
        default="default",
        description="Iceberg catalog namespace. Defaults to 'default'.",
    )

    @field_validator("file")
    @classmethod
    def validate_file_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("File path must not be empty.")
        return cleaned

    @model_validator(mode="after")
    def validate_merge_key(self) -> "WriteTableRequest":
        if self.mode == WriteMode.MERGE and not (self.merge_key and self.merge_key.strip()):
            raise ValueError("merge_key is required when mode is 'merge'.")
        return self


class FieldSchemaModel(BaseModel):
    """Metadata for an individual Iceberg table field."""
    field_id: int
    name: str
    type: str
    required: bool
    doc: Optional[str] = None


class SnapshotModel(BaseModel):
    """Metadata for an Iceberg commit snapshot."""
    snapshot_id: int
    parent_snapshot_id: Optional[int] = None
    timestamp_ms: int
    operation: str
    summary: Dict[str, str] = Field(default_factory=dict)
    manifest_list: Optional[str] = None


class TableSummaryModel(BaseModel):
    """Concise summary of an Iceberg table."""
    name: str
    namespace: str
    identifier: str
    location: str
    total_records: int
    current_snapshot_id: Optional[int] = None
    schema_fields_count: int


class TableDetailResponse(BaseModel):
    """Comprehensive Iceberg table metadata and schema."""
    name: str
    namespace: str
    identifier: str
    location: str
    format_version: int
    current_snapshot_id: Optional[int] = None
    total_records: int
    total_files: int
    total_data_size_bytes: int
    schema_fields: List[FieldSchemaModel]
    properties: Dict[str, Any] = Field(default_factory=dict)
    snapshots: List[SnapshotModel] = Field(default_factory=list)
    created_at_utc: Optional[str] = None
    inferred_from_file: Optional[str] = None
    detected_format: Optional[str] = None


class TableDeleteResponse(BaseModel):
    """Confirmation of table deletion."""
    status: str = "deleted"
    identifier: str
    message: str


class PreviewTableRequest(BaseModel):
    file: str = Field(
        ...,
        description="Path or filename of the dataset to preview.",
    )

class PreviewTableResponse(BaseModel):
    file: str
    original_filename: str
    detected_format: str
    row_count: Optional[int] = None
    schema_fields: List[FieldSchemaModel]

class ErrorResponse(BaseModel):
    """Standardized error structure."""
    error: str
    detail: Optional[str] = None

class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    columns: List[str]
    rows: List[List[Any]]
    row_count: int


# --- Schema Evolution Models ---

class AddColumnSpec(BaseModel):
    """Specification for adding a column."""
    name: str = Field(..., description="Column name to add.")
    type: str = Field(..., description="Iceberg type string, e.g. 'string', 'long', 'double', 'boolean'.")
    doc: Optional[str] = Field(default=None, description="Optional column documentation.")


class RenameColumnSpec(BaseModel):
    """Specification for renaming a column."""
    from_name: str = Field(..., alias="from", description="Current column name.")
    to_name: str = Field(..., alias="to", description="New column name.")

    model_config = {"populate_by_name": True}


class SchemaEvolutionRequest(BaseModel):
    """Request body for evolving a table's schema."""
    add_columns: Optional[List[AddColumnSpec]] = Field(default=None, description="Columns to add.")
    rename_columns: Optional[List[RenameColumnSpec]] = Field(default=None, description="Columns to rename.")


class SchemaEvolutionResponse(BaseModel):
    """Response showing the evolved schema with stable field IDs."""
    table_name: str
    namespace: str
    schema_fields: List[FieldSchemaModel]
    message: str


# --- Maintenance Models ---

class CompactResponse(BaseModel):
    """Result of a table compaction."""
    table_name: str
    namespace: str
    files_before: int
    files_after: int
    size_before_bytes: int
    size_after_bytes: int
    new_snapshot_id: Optional[int] = None


class ExpireSnapshotsRequest(BaseModel):
    """Request body for snapshot expiration."""
    older_than_days: int = Field(default=30, ge=1, description="Expire snapshots older than this many days.")


class ExpireSnapshotsResponse(BaseModel):
    """Result of snapshot expiration."""
    table_name: str
    namespace: str
    expired_count: int
    remaining_count: int


class SnapshotDetailModel(BaseModel):
    """Detailed snapshot info for the list-snapshots endpoint."""
    snapshot_id: int
    parent_snapshot_id: Optional[int] = None
    timestamp_ms: int
    timestamp_utc: str
    operation: str
    summary: Dict[str, str] = Field(default_factory=dict)
    manifest_list: Optional[str] = None
