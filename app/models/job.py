"""
Job Models
==========
Request and response models for async ingestion job tracking.
"""

from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, field_validator

from app.models.table import TABLE_NAME_REGEX, TableDetailResponse


class JobStatus(str, Enum):
    """Possible states of an ingestion job."""
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class JobIngestRequest(BaseModel):
    """Payload for submitting an async ingestion job."""
    name: str = Field(
        ...,
        description="Name of the Iceberg table to create.",
        examples=["sales", "events_log"],
    )
    file: str = Field(
        ...,
        description="Path or filename of the dataset.",
        examples=["sales.csv", "events.json"],
    )
    namespace: Optional[str] = Field(
        default="default",
        description="Iceberg catalog namespace.",
    )

    @field_validator("name")
    @classmethod
    def validate_table_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Table name must not be empty.")
        if not TABLE_NAME_REGEX.match(cleaned):
            raise ValueError(
                f"Invalid table name '{cleaned}'. Must start with a letter, "
                "contain only letters, digits, underscores, max 64 chars."
            )
        return cleaned.lower()

    @field_validator("file")
    @classmethod
    def validate_file_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("File path must not be empty.")
        return cleaned


class JobSubmitResponse(BaseModel):
    """Returned immediately when a job is submitted."""
    job_id: str
    status: JobStatus = JobStatus.QUEUED
    message: str = "Job queued for processing."


class JobResponse(BaseModel):
    """Full status of a job including result on completion."""
    job_id: str
    status: JobStatus
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    request: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[TableDetailResponse] = None
    error: Optional[str] = None
