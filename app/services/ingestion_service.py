"""
Ingestion Service
=================
Resolves dataset files, triggers PyArrow parsing, and manages schema inference.
"""

from pathlib import Path
from typing import Optional, Tuple, Union
import pyarrow as pa
from pyiceberg.schema import Schema

from app.config.settings import settings
from iceberg.schema import infer_arrow_schema_from_file, read_file_to_arrow_table


class DatasetResolutionError(Exception):
    """Raised when an input dataset file cannot be located or accessed."""
    pass


class IngestionService:
    """
    Handles local dataset file resolution and PyArrow parsing.
    """

    def __init__(self, sample_data_dir: Union[str, Path] = settings.SAMPLE_DATA_DIR):
        self.sample_data_dir = Path(sample_data_dir)

    def resolve_file_path(self, file_param: str) -> Path:
        """
        Locates a file either by absolute path, relative to current working directory,
        or within the configured sample_data_dir.
        """
        raw_path = Path(file_param)

        # 1. Direct path exists
        if raw_path.exists() and raw_path.is_file():
            return raw_path.resolve()

        # 2. Check inside sample_data_dir
        in_sample = self.sample_data_dir / file_param
        if in_sample.exists() and in_sample.is_file():
            return in_sample.resolve()

        # 3. Check stripped filename inside sample_data_dir
        in_sample_name = self.sample_data_dir / raw_path.name
        if in_sample_name.exists() and in_sample_name.is_file():
            return in_sample_name.resolve()

        raise DatasetResolutionError(
            f"Input file '{file_param}' was not found. "
            f"Searched in '{raw_path.resolve()}' and '{self.sample_data_dir.resolve()}'."
        )

    def load_and_infer(
        self, file_param: str, sample_rows: Optional[int] = None
    ) -> Tuple[pa.Table, Schema, str, str]:
        """
        Locates the file, reads it into an Arrow table, and infers the Iceberg schema.

        Args:
            file_param: File name or path to resolve.
            sample_rows: When set, only this many rows are read to infer column
                types (used for preview). None reads the whole file (ingestion).

        Returns:
            Tuple of (arrow_table, iceberg_schema, detected_format, resolved_file_path_str)
        """
        resolved_path = self.resolve_file_path(file_param)
        arrow_table, iceberg_schema, file_format = infer_arrow_schema_from_file(
            resolved_path, sample_rows=sample_rows
        )
        return arrow_table, iceberg_schema, file_format, str(resolved_path)

    def load_table_data(self, file_param: str) -> Tuple[pa.Table, str, str]:
        """
        Locates the file and reads it into an Arrow table for appending.

        Returns:
            Tuple of (arrow_table, detected_format, resolved_file_path_str)
        """
        resolved_path = self.resolve_file_path(file_param)
        arrow_table, file_format = read_file_to_arrow_table(resolved_path)
        return arrow_table, file_format, str(resolved_path)
