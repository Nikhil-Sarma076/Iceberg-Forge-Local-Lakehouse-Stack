"""
Job Service
===========
In-memory async job queue with a background worker for ingestion tasks.
Demonstrates the submit → queue → execute → poll pattern used in
distributed job execution systems (EMR, Spark submit, Airflow).
"""

import asyncio
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.models.job import JobIngestRequest, JobResponse, JobStatus, JobSubmitResponse
from app.models.table import CreateTableRequest, TableDetailResponse
from app.services.table_service import TableService


class JobRecord:
    """Internal mutable job state (not exposed directly via API)."""

    __slots__ = (
        "job_id", "status", "created_at", "started_at", "completed_at",
        "request", "result", "error",
    )

    def __init__(self, job_id: str, request: JobIngestRequest):
        self.job_id = job_id
        self.status = JobStatus.QUEUED
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.started_at: Optional[str] = None
        self.completed_at: Optional[str] = None
        self.request = request
        self.result: Optional[TableDetailResponse] = None
        self.error: Optional[str] = None

    def to_response(self) -> JobResponse:
        return JobResponse(
            job_id=self.job_id,
            status=self.status,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
            request=self.request.model_dump(),
            result=self.result,
            error=self.error,
        )


# ponytail: global in-memory store — ceiling: lost on restart, no persistence.
# Upgrade path: swap dict for Redis or a DB-backed store.
_jobs: OrderedDict[str, JobRecord] = OrderedDict()
_queue: asyncio.Queue = asyncio.Queue()
_worker_task: Optional[asyncio.Task] = None


def submit_job(request: JobIngestRequest) -> JobSubmitResponse:
    """Enqueue an ingestion job and return immediately with a job_id."""
    job_id = str(uuid.uuid4())
    record = JobRecord(job_id=job_id, request=request)
    _jobs[job_id] = record
    _queue.put_nowait(record)
    return JobSubmitResponse(job_id=job_id, status=JobStatus.QUEUED)


def get_job(job_id: str) -> Optional[JobResponse]:
    """Retrieve job status by ID."""
    record = _jobs.get(job_id)
    if record is None:
        return None
    return record.to_response()


def list_jobs(limit: int = 50) -> List[JobResponse]:
    """List recent jobs, newest first."""
    items = list(reversed(_jobs.values()))[:limit]
    return [r.to_response() for r in items]


async def _process_job(record: JobRecord, table_service: TableService) -> None:
    """Execute a single ingestion job using the existing TableService pipeline."""
    record.status = JobStatus.RUNNING
    record.started_at = datetime.now(timezone.utc).isoformat()

    try:
        # Build a CreateTableRequest from the job payload
        create_req = CreateTableRequest(
            name=record.request.name,
            file=record.request.file,
            namespace=record.request.namespace,
        )
        result = table_service.create_table(create_req)
        record.status = JobStatus.COMPLETED
        record.result = result
    except Exception as e:
        record.status = JobStatus.FAILED
        record.error = str(e)
    finally:
        record.completed_at = datetime.now(timezone.utc).isoformat()


async def _worker(table_service: TableService) -> None:
    """Background worker that consumes jobs from the queue sequentially."""
    while True:
        record: JobRecord = await _queue.get()
        await _process_job(record, table_service)
        _queue.task_done()


def start_worker(table_service: TableService) -> None:
    """Start the background worker task. Call once at app startup."""
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_worker(table_service))
