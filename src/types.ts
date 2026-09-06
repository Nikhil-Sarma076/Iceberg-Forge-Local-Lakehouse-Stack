export interface FieldSchema {
  field_id: number;
  name: string;
  type: string;
  required: boolean;
  doc?: string;
}

export interface TableSummary {
  name: string;
  namespace: string;
  identifier: string;
  location: string;
  total_records: number;
  current_snapshot_id?: number;
  schema_fields_count: number;
}

export interface Snapshot {
  snapshot_id: number;
  parent_snapshot_id?: number;
  timestamp_ms: number;
  operation: string;
  summary: Record<string, string>;
  manifest_list?: string;
}

export interface TableDetail {
  name: string;
  namespace: string;
  identifier: string;
  location: string;
  format_version: number;
  current_snapshot_id?: number;
  total_records: number;
  total_files: number;
  total_data_size_bytes: number;
  schema_fields: FieldSchema[];
  properties: Record<string, any>;
  snapshots: Snapshot[];
  created_at_utc?: string;
  inferred_from_file?: string;
  detected_format?: string;
}

export interface PreviewResponse {
  file: string;
  original_filename: string;
  detected_format: string;
  row_count?: number;
  schema_fields: FieldSchema[];
}

export interface QueryResponse {
  columns: string[];
  rows: any[][];
  row_count: number;
}

// --- Job Queue Types ---

export type JobStatus = 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED';

export interface JobSubmitResponse {
  job_id: string;
  status: JobStatus;
  message: string;
}

export interface JobResponse {
  job_id: string;
  status: JobStatus;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  request: Record<string, any>;
  result?: TableDetail;
  error?: string;
}

// --- Maintenance Types ---

export interface CompactResponse {
  table_name: string;
  namespace: string;
  files_before: number;
  files_after: number;
  size_before_bytes: number;
  size_after_bytes: number;
  new_snapshot_id?: number;
}

export interface ExpireSnapshotsResponse {
  table_name: string;
  namespace: string;
  expired_count: number;
  remaining_count: number;
}

export interface SnapshotDetail {
  snapshot_id: number;
  parent_snapshot_id?: number;
  timestamp_ms: number;
  timestamp_utc: string;
  operation: string;
  summary: Record<string, string>;
  manifest_list?: string;
}

// --- Schema Evolution Types ---

export interface SchemaEvolutionResponse {
  table_name: string;
  namespace: string;
  schema_fields: FieldSchema[];
  message: string;
}

// --- Write / Update Types ---

export type WriteMode = 'append' | 'overwrite' | 'merge';
