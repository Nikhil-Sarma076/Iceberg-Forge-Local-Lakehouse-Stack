import type {
  TableSummary,
  TableDetail,
  PreviewResponse,
  QueryResponse,
  JobSubmitResponse,
  JobResponse,
  CompactResponse,
  ExpireSnapshotsResponse,
  SnapshotDetail,
  SchemaEvolutionResponse,
  WriteMode,
} from '../types';

const API_BASE = `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}`;

async function fetchApi<T = any>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = endpoint.startsWith('/v1') ? `${API_BASE}${endpoint}` : `${API_BASE}${endpoint}`;
  const response = await fetch(url, options);

  if (!response.ok) {
    let message = `API request failed: ${response.statusText}`;
    try {
      const errorData = await response.json();
      message = errorData.detail || errorData.error || message;
    } catch (_) {}
    throw new Error(message);
  }

  return response.json();
}

export const api = {
  // --- System ---
  checkHealth: async () => fetchApi<{ status: string; version: string }>('/health'),

  // --- Tables ---
  listTables: async (): Promise<TableSummary[]> => fetchApi('/v1/tables'),

  getTable: async (name: string): Promise<TableDetail> => fetchApi(`/v1/tables/${name}`),

  createTable: async (name: string, file: string): Promise<TableDetail> =>
    fetchApi('/v1/tables', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, file }),
    }),

  dropTable: async (name: string) =>
    fetchApi(`/v1/tables/${name}`, { method: 'DELETE' }),

  appendTable: async (name: string, file: string) =>
    fetchApi(`/v1/tables/${name}/append`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file }),
    }),

  writeTable: async (
    name: string,
    file: string,
    mode: WriteMode,
    mergeKey?: string,
  ): Promise<TableDetail> =>
    fetchApi(`/v1/tables/${name}/write`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file, mode, merge_key: mergeKey || undefined }),
    }),

  // --- Preview ---
  previewFile: async (file: File): Promise<PreviewResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    return fetchApi('/v1/preview', { method: 'POST', body: formData });
  },

  // --- Query ---
  executeQuery: async (query: string): Promise<QueryResponse> =>
    fetchApi('/v1/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    }),

  // --- Jobs ---
  submitJob: async (name: string, file: string): Promise<JobSubmitResponse> =>
    fetchApi('/v1/jobs/ingest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, file }),
    }),

  listJobs: async (): Promise<JobResponse[]> => fetchApi('/v1/jobs'),

  getJob: async (jobId: string): Promise<JobResponse> => fetchApi(`/v1/jobs/${jobId}`),

  // --- Maintenance ---
  compactTable: async (name: string): Promise<CompactResponse> =>
    fetchApi(`/v1/tables/${name}/compact`, { method: 'POST' }),

  expireSnapshots: async (name: string, olderThanDays: number = 30): Promise<ExpireSnapshotsResponse> =>
    fetchApi(`/v1/tables/${name}/expire-snapshots`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ older_than_days: olderThanDays }),
    }),

  listSnapshots: async (name: string): Promise<SnapshotDetail[]> =>
    fetchApi(`/v1/tables/${name}/snapshots`),

  // --- Schema Evolution ---
  evolveSchema: async (
    name: string,
    addColumns?: { name: string; type: string; doc?: string }[],
    renameColumns?: { from: string; to: string }[],
  ): Promise<SchemaEvolutionResponse> =>
    fetchApi(`/v1/tables/${name}/evolve-schema`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        add_columns: addColumns || undefined,
        rename_columns: renameColumns || undefined,
      }),
    }),
};
