import React, { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { JobResponse, JobStatus } from '../types';
import { Play, Loader2, CheckCircle2, XCircle, Clock, RefreshCw, Plus, Upload, FileUp, X } from 'lucide-react';

export const JobsMonitor: React.FC = () => {
  const [jobs, setJobs] = useState<JobResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [showSubmit, setShowSubmit] = useState(false);

  useEffect(() => {
    load();
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, []);

  const load = async () => {
    try { setJobs(await api.listJobs()); } catch {}
    setLoading(false);
  };

  const counts = {
    running: jobs.filter((j) => j.status === 'RUNNING' || j.status === 'QUEUED').length,
    completed: jobs.filter((j) => j.status === 'COMPLETED').length,
    failed: jobs.filter((j) => j.status === 'FAILED').length,
  };

  return (
    <div className="h-full flex flex-col">
      {/* Toolbar */}
      <div className="h-14 shrink-0 flex items-center justify-between px-6 border-b" style={{ background: 'var(--color-surface-1)' }}>
        <div className="flex items-center gap-2">
          <span className="badge badge-info">{jobs.length} total</span>
          {counts.running > 0 && <span className="badge badge-warn"><Loader2 size={11} className="animate-spin" /> {counts.running} active</span>}
          {counts.completed > 0 && <span className="badge badge-success">{counts.completed} done</span>}
          {counts.failed > 0 && <span className="badge badge-error">{counts.failed} failed</span>}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowSubmit(true)} className="btn btn-primary btn-sm"><Plus size={14} /> Submit Job</button>
          <button onClick={load} className="btn-icon btn-subtle"><RefreshCw size={14} /></button>
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-auto p-6">
        {loading ? (
          <div className="flex justify-center py-20"><Loader2 size={22} className="animate-spin" style={{ color: '#52525b' }} /></div>
        ) : jobs.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center">
              <Clock size={32} style={{ color: '#3f3f46', margin: '0 auto 14px' }} />
              <div className="text-body" style={{ color: '#71717a' }}>No jobs submitted yet</div>
              <button onClick={() => setShowSubmit(true)} className="btn btn-ghost btn-sm mt-4"><Plus size={13} /> Submit a job</button>
            </div>
          </div>
        ) : (
          <div className="panel overflow-hidden">
            <table className="dtable">
              <thead>
                <tr><th style={{ width: 120 }}>Status</th><th>Job ID</th><th>Table</th><th>File</th><th style={{ width: 90 }}>Duration</th><th style={{ width: 110 }}>Submitted</th></tr>
              </thead>
              <tbody>
                {jobs.map((j) => (
                  <tr key={j.job_id}>
                    <td><StatusBadge status={j.status} /></td>
                    <td className="mono" style={{ color: '#71717a' }} title={j.job_id}>{j.job_id.slice(0, 8)}…</td>
                    <td style={{ color: '#f4f4f5' }}>{j.request?.name || '—'}</td>
                    <td className="mono text-meta">{j.request?.file || '—'}</td>
                    <td className="mono text-meta">{duration(j)}</td>
                    <td className="text-meta">{ago(j.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showSubmit && <SubmitModal onClose={() => setShowSubmit(false)} onSubmitted={() => { setShowSubmit(false); load(); }} />}
    </div>
  );
};

const SubmitModal: React.FC<{ onClose: () => void; onSubmitted: () => void }> = ({ onClose, onSubmitted }) => {
  const [name, setName] = useState('');
  const [path, setPath] = useState('');
  const [uploaded, setUploaded] = useState<File | null>(null);
  const [serverFile, setServerFile] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const upload = async (f: File) => {
    setUploaded(f); setUploading(true); setError(null);
    try {
      const p = await api.previewFile(f);
      setServerFile(p.file); setPath(p.file);
      if (!name) setName(f.name.replace(/\.[^.]+$/, '').replace(/[^a-zA-Z0-9_]/g, '_').toLowerCase());
    } catch (e: any) { setError(`Upload failed: ${e.message}`); setUploaded(null); }
    finally { setUploading(false); }
  };

  const submit = async () => {
    const file = serverFile || path.trim();
    if (!name.trim() || !file) return;
    setBusy(true); setError(null);
    try {
      await api.submitJob(name.trim(), file);
      onSubmitted();
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.6)' }} onClick={onClose}>
      <div className="panel w-full max-w-md animate-in" style={{ background: 'var(--color-surface-1)' }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <span className="text-title">Submit Ingestion Job</span>
          <button onClick={onClose} className="btn-icon btn-subtle"><X size={16} /></button>
        </div>
        <div className="p-5 space-y-4">
          <div
            onClick={() => fileRef.current?.click()}
            className="rounded-lg p-6 text-center cursor-pointer"
            style={{ border: `1.5px dashed ${uploaded ? 'var(--color-accent)' : 'var(--color-border-strong)'}`, background: uploaded ? 'var(--color-accent-subtle)' : 'var(--color-surface-0)' }}
          >
            <input ref={fileRef} type="file" className="hidden" accept=".csv,.json,.jsonl,.ndjson,.parquet,.pq" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
            {uploading ? <div className="flex items-center justify-center gap-2 text-meta"><Loader2 size={15} className="animate-spin" /> Uploading…</div>
              : uploaded ? <div className="flex items-center justify-center gap-2"><FileUp size={16} style={{ color: 'var(--color-accent)' }} /><span className="text-body" style={{ color: '#c7d2fe' }}>{uploaded.name}</span></div>
              : <><Upload size={20} style={{ color: '#52525b', margin: '0 auto 8px' }} /><div className="text-body" style={{ color: '#a1a1aa' }}>Click to upload</div><div className="text-micro mt-1">CSV · JSON · Parquet</div></>}
          </div>
          {!uploaded && <div><label className="text-micro uppercase">Or server path</label><input className="input mt-1.5" value={path} onChange={(e) => setPath(e.target.value)} placeholder="sales.csv" /></div>}
          <div><label className="text-micro uppercase">Table name</label><input className="input mt-1.5" value={name} onChange={(e) => setName(e.target.value)} placeholder="my_table" /></div>
          {error && <div className="text-meta px-3 py-2 rounded-md" style={{ background: 'rgba(248,113,113,0.1)', color: '#f87171' }}>{error}</div>}
        </div>
        <div className="flex justify-end gap-2 px-5 py-4 border-t">
          <button onClick={onClose} className="btn btn-ghost">Cancel</button>
          <button onClick={submit} disabled={busy || !name.trim() || (!path.trim() && !serverFile)} className="btn btn-primary">{busy ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} Submit</button>
        </div>
      </div>
    </div>
  );
};

const StatusBadge: React.FC<{ status: JobStatus }> = ({ status }) => {
  const map: Record<JobStatus, { cls: string; icon: React.ReactNode }> = {
    QUEUED: { cls: 'badge-neutral', icon: <Clock size={11} /> },
    RUNNING: { cls: 'badge-info', icon: <Loader2 size={11} className="animate-spin" /> },
    COMPLETED: { cls: 'badge-success', icon: <CheckCircle2 size={11} /> },
    FAILED: { cls: 'badge-error', icon: <XCircle size={11} /> },
  };
  const { cls, icon } = map[status];
  return <span className={`badge ${cls}`}>{icon} {status}</span>;
};

function duration(j: JobResponse): string {
  if (!j.started_at || !j.completed_at) return j.status === 'RUNNING' ? '···' : '—';
  const ms = new Date(j.completed_at).getTime() - new Date(j.started_at).getTime();
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

function ago(iso: string): string {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    if (diff < 60000) return 'just now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch { return iso; }
}
