import React, { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { TableDetail as TD, SnapshotDetail, CompactResponse, SchemaEvolutionResponse, WriteMode } from '../types';
import { Loader2, Shrink, Clock, PlusCircle, AlertCircle, CheckCircle2, Layers, HardDrive, Rows3, Upload, FileUp, Plus, Replace, GitMerge } from 'lucide-react';

type SubTab = 'schema' | 'snapshots' | 'update' | 'maintenance' | 'evolve';

interface Props {
  tableName: string;
  onChanged?: () => void;
}

export const TableDetail: React.FC<Props> = ({ tableName, onChanged }) => {
  const [table, setTable] = useState<TD | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<SubTab>('schema');

  useEffect(() => { load(); }, [tableName]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setTable(await api.getTable(tableName));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div className="h-full flex items-center justify-center"><Loader2 size={22} className="animate-spin" style={{ color: '#52525b' }} /></div>;
  if (error || !table) return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center"><AlertCircle size={24} className="text-red-400 mx-auto mb-2" /><div className="text-body text-red-400">{error || 'Not found'}</div></div>
    </div>
  );

  const tabs: { id: SubTab; label: string }[] = [
    { id: 'schema', label: 'Schema' },
    { id: 'update', label: 'Update' },
    { id: 'snapshots', label: 'Snapshots' },
    { id: 'maintenance', label: 'Maintenance' },
    { id: 'evolve', label: 'Evolve' },
  ];

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="px-6 pt-5 pb-0 border-b" style={{ background: 'var(--color-surface-1)' }}>
        <div className="flex items-start justify-between">
          <div>
            <div className="text-display">{table.name}</div>
            <div className="text-meta mono mt-0.5">{table.identifier}</div>
          </div>
        </div>

        {/* Stat chips */}
        <div className="flex gap-2 mt-4">
          <Stat icon={<Rows3 size={13} />} label="Rows" value={table.total_records.toLocaleString()} />
          <Stat icon={<HardDrive size={13} />} label="Files" value={String(table.total_files)} />
          <Stat icon={<Layers size={13} />} label="Size" value={`${(table.total_data_size_bytes / 1024).toFixed(1)} KB`} />
          <Stat icon={<Layers size={13} />} label="Format" value={`Iceberg v${table.format_version}`} />
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mt-4 -mb-px">
          {tabs.map((t) => {
            const on = tab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className="px-3.5 py-2.5 text-body font-medium transition-colors"
                style={{
                  color: on ? '#f4f4f5' : '#71717a',
                  borderBottom: on ? '2px solid var(--color-accent)' : '2px solid transparent',
                }}
              >
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-6">
        {tab === 'schema' && <SchemaTab table={table} />}
        {tab === 'update' && <UpdateTab table={table} onDone={() => { load(); onChanged?.(); }} />}
        {tab === 'snapshots' && <SnapshotsTab tableName={tableName} />}
        {tab === 'maintenance' && <MaintenanceTab tableName={tableName} onDone={load} />}
        {tab === 'evolve' && <EvolveTab tableName={tableName} onDone={() => { load(); onChanged?.(); }} />}
      </div>
    </div>
  );
};

const Stat: React.FC<{ icon: React.ReactNode; label: string; value: string }> = ({ icon, label, value }) => (
  <div className="card px-3 py-2 flex items-center gap-2.5" style={{ background: 'var(--color-surface-2)' }}>
    <span style={{ color: '#71717a' }}>{icon}</span>
    <div>
      <div className="text-micro uppercase leading-none">{label}</div>
      <div className="text-body font-medium mono leading-tight mt-0.5" style={{ color: '#f4f4f5' }}>{value}</div>
    </div>
  </div>
);

// ---- Schema ----
const SchemaTab: React.FC<{ table: TD }> = ({ table }) => (
  <div className="space-y-5 animate-in">
    <div className="panel overflow-hidden">
      <table className="dtable">
        <thead><tr><th style={{ width: 56 }}>ID</th><th>Column</th><th>Type</th><th style={{ width: 100 }}>Required</th></tr></thead>
        <tbody>
          {table.schema_fields.map((f) => (
            <tr key={f.field_id}>
              <td className="mono" style={{ color: '#52525b' }}>{f.field_id}</td>
              <td style={{ color: '#f4f4f5' }}>{f.name}</td>
              <td className="mono" style={{ color: '#a5b4fc' }}>{f.type}</td>
              <td className="text-meta">{f.required ? 'yes' : 'no'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>

  </div>
);

// ---- Update (append / overwrite / merge) ----
const MODES: { id: WriteMode; label: string; icon: React.ReactNode; desc: string }[] = [
  { id: 'append', label: 'Append', icon: <Plus size={15} />, desc: 'Add the incoming rows as a new snapshot. Existing data is untouched.' },
  { id: 'overwrite', label: 'Overwrite', icon: <Replace size={15} />, desc: 'Replace ALL existing data with the incoming rows.' },
  { id: 'merge', label: 'Merge', icon: <GitMerge size={15} />, desc: 'Upsert on a key column — matching rows are replaced, new rows added, others kept.' },
];

const UpdateTab: React.FC<{ table: TD; onDone: () => void }> = ({ table, onDone }) => {
  const [mode, setMode] = useState<WriteMode>('append');
  const [mergeKey, setMergeKey] = useState<string>(table.schema_fields[0]?.name || '');
  const [uploaded, setUploaded] = useState<File | null>(null);
  const [serverFile, setServerFile] = useState<string | null>(null);
  const [path, setPath] = useState('');
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const upload = async (f: File) => {
    setUploaded(f); setUploading(true); setError(null); setOkMsg(null);
    try {
      const p = await api.previewFile(f);
      setServerFile(p.file); setPath(p.file);
    } catch (e: any) { setError(`Upload failed: ${e.message}`); setUploaded(null); }
    finally { setUploading(false); }
  };

  const run = async () => {
    const file = serverFile || path.trim();
    if (!file) return;
    setBusy(true); setError(null); setOkMsg(null);
    try {
      const res = await api.writeTable(table.name, file, mode, mode === 'merge' ? mergeKey : undefined);
      setOkMsg(`${mode} complete — table now has ${res.total_records.toLocaleString()} rows.`);
      setUploaded(null); setServerFile(null); setPath('');
      onDone();
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };

  const selMode = MODES.find((m) => m.id === mode)!;

  return (
    <div className="space-y-5 max-w-2xl animate-in">
      {/* Mode selector */}
      <div>
        <div className="text-micro uppercase mb-2">Write Mode</div>
        <div className="grid grid-cols-3 gap-2">
          {MODES.map((m) => {
            const on = mode === m.id;
            return (
              <button
                key={m.id}
                onClick={() => setMode(m.id)}
                className="card p-3 text-left transition-all"
                style={{
                  borderColor: on ? 'var(--color-accent)' : 'var(--color-border)',
                  background: on ? 'var(--color-accent-subtle)' : 'var(--color-surface-2)',
                }}
              >
                <div className="flex items-center gap-2" style={{ color: on ? '#c7d2fe' : '#a1a1aa' }}>
                  {m.icon}<span className="text-body font-medium">{m.label}</span>
                </div>
              </button>
            );
          })}
        </div>
        <p className="text-meta mt-2">{selMode.desc}</p>
      </div>

      {/* Merge key */}
      {mode === 'merge' && (
        <div>
          <div className="text-micro uppercase mb-2">Merge Key (upsert column)</div>
          <select className="input" value={mergeKey} onChange={(e) => setMergeKey(e.target.value)}>
            {table.schema_fields.map((f) => (
              <option key={f.field_id} value={f.name}>{f.name} · {f.type}</option>
            ))}
          </select>
        </div>
      )}

      {/* File */}
      <div>
        <div className="text-micro uppercase mb-2">Data File</div>
        <div
          onClick={() => fileRef.current?.click()}
          className="rounded-lg p-6 text-center cursor-pointer"
          style={{ border: `1.5px dashed ${uploaded ? 'var(--color-accent)' : 'var(--color-border-strong)'}`, background: uploaded ? 'var(--color-accent-subtle)' : 'var(--color-surface-0)' }}
        >
          <input ref={fileRef} type="file" className="hidden" accept=".csv,.json,.jsonl,.ndjson,.parquet,.pq" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          {uploading ? <div className="flex items-center justify-center gap-2 text-meta"><Loader2 size={15} className="animate-spin" /> Uploading…</div>
            : uploaded ? <div className="flex items-center justify-center gap-2"><FileUp size={16} style={{ color: 'var(--color-accent)' }} /><span className="text-body" style={{ color: '#c7d2fe' }}>{uploaded.name}</span></div>
            : <><Upload size={20} style={{ color: '#52525b', margin: '0 auto 8px' }} /><div className="text-body" style={{ color: '#a1a1aa' }}>Click to upload a file</div><div className="text-micro mt-1">CSV · JSON · Parquet</div></>}
        </div>
        {!uploaded && (
          <input className="input mt-2" value={path} onChange={(e) => setPath(e.target.value)} placeholder="…or server path (e.g. orders_append.csv)" />
        )}
      </div>

      <button onClick={run} disabled={busy || (!serverFile && !path.trim())} className="btn btn-primary">
        {busy ? <Loader2 size={13} className="animate-spin" /> : selMode.icon}
        Run {selMode.label}
      </button>

      {error && <div className="card p-3 text-meta" style={{ borderColor: 'rgba(248,113,113,0.3)', color: '#f87171' }}>{error}</div>}
      {okMsg && <div className="flex items-center gap-1.5 text-meta" style={{ color: '#4ade80' }}><CheckCircle2 size={13} /> {okMsg}</div>}
    </div>
  );
};

// ---- Snapshots ----
const SnapshotsTab: React.FC<{ tableName: string }> = ({ tableName }) => {
  const [snaps, setSnaps] = useState<SnapshotDetail[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => { api.listSnapshots(tableName).then(setSnaps).catch(() => {}).finally(() => setLoading(false)); }, [tableName]);
  if (loading) return <Loader2 size={18} className="animate-spin" style={{ color: '#52525b' }} />;
  return (
    <div className="space-y-3 animate-in">
      {snaps.length === 0 && <div className="text-meta">No snapshots</div>}
      {snaps.map((s, i) => (
        <div key={s.snapshot_id} className="card p-4 flex items-start gap-3">
          <div className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 mono text-micro" style={{ background: 'var(--color-surface-3)', color: '#a1a1aa' }}>{snaps.length - i}</div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="mono text-meta truncate">#{s.snapshot_id}</span>
              <span className={`badge ${s.operation === 'append' ? 'badge-success' : s.operation === 'overwrite' ? 'badge-warn' : 'badge-neutral'}`}>{s.operation}</span>
            </div>
            <div className="text-micro mt-1">{s.timestamp_utc}</div>
            {s.summary['total-records'] && <div className="text-micro mono mt-1">records: {s.summary['total-records']} · files: {s.summary['total-data-files'] || '—'}</div>}
          </div>
        </div>
      ))}
    </div>
  );
};

// ---- Maintenance ----
const MaintenanceTab: React.FC<{ tableName: string; onDone: () => void }> = ({ tableName, onDone }) => {
  const [compact, setCompact] = useState<CompactResponse | null>(null);
  const [expireRes, setExpireRes] = useState<{ expired_count: number; remaining_count: number } | null>(null);
  const [busy, setBusy] = useState<'' | 'compact' | 'expire'>('');
  const [error, setError] = useState<string | null>(null);

  const doCompact = async () => {
    setBusy('compact'); setError(null);
    try { setCompact(await api.compactTable(tableName)); onDone(); } catch (e: any) { setError(e.message); } finally { setBusy(''); }
  };
  const doExpire = async () => {
    setBusy('expire'); setError(null);
    try { setExpireRes(await api.expireSnapshots(tableName, 1)); onDone(); } catch (e: any) { setError(e.message); } finally { setBusy(''); }
  };

  return (
    <div className="space-y-4 max-w-xl animate-in">
      {error && <div className="card p-3 text-meta" style={{ borderColor: 'rgba(248,113,113,0.3)', color: '#f87171' }}>{error}</div>}

      <div className="card p-5">
        <div className="flex items-center gap-2 mb-1"><Shrink size={16} style={{ color: 'var(--color-accent)' }} /><span className="text-title">Compact Data Files</span></div>
        <p className="text-meta mb-3">Rewrite all data files into a single consolidated Parquet file to reduce file count.</p>
        <button onClick={doCompact} disabled={busy === 'compact'} className="btn btn-ghost btn-sm">{busy === 'compact' ? <Loader2 size={13} className="animate-spin" /> : <Shrink size={13} />} Run Compaction</button>
        {compact && <div className="mt-3 text-meta mono card p-3" style={{ background: 'var(--color-surface-1)' }}>files: {compact.files_before} → {compact.files_after} · size: {(compact.size_before_bytes / 1024).toFixed(1)} → {(compact.size_after_bytes / 1024).toFixed(1)} KB</div>}
      </div>

      <div className="card p-5">
        <div className="flex items-center gap-2 mb-1"><Clock size={16} style={{ color: '#facc15' }} /><span className="text-title">Expire Snapshots</span></div>
        <p className="text-meta mb-3">Remove snapshots older than 1 day to reclaim metadata and storage.</p>
        <button onClick={doExpire} disabled={busy === 'expire'} className="btn btn-ghost btn-sm">{busy === 'expire' ? <Loader2 size={13} className="animate-spin" /> : <Clock size={13} />} Expire Old</button>
        {expireRes && <div className="mt-3 text-meta mono card p-3" style={{ background: 'var(--color-surface-1)' }}>expired: {expireRes.expired_count} · remaining: {expireRes.remaining_count}</div>}
      </div>
    </div>
  );
};

// ---- Evolve ----
const EvolveTab: React.FC<{ tableName: string; onDone: () => void }> = ({ tableName, onDone }) => {
  const [name, setName] = useState('');
  const [type, setType] = useState('string');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SchemaEvolutionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const add = async () => {
    if (!name.trim()) return;
    setBusy(true); setError(null); setResult(null);
    try {
      setResult(await api.evolveSchema(tableName, [{ name: name.trim(), type }]));
      setName('');
      onDone();
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };

  const types = ['string', 'long', 'integer', 'double', 'float', 'boolean', 'date', 'timestamp', 'binary'];

  return (
    <div className="space-y-5 max-w-2xl animate-in">
      <div className="card p-5">
        <div className="flex items-center gap-2 mb-3"><PlusCircle size={16} style={{ color: '#22c55e' }} /><span className="text-title">Add Column</span></div>
        <div className="flex gap-2">
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="column_name" />
          <select className="input" style={{ width: 130 }} value={type} onChange={(e) => setType(e.target.value)}>
            {types.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <button onClick={add} disabled={busy || !name.trim()} className="btn btn-primary">{busy ? <Loader2 size={13} className="animate-spin" /> : <PlusCircle size={13} />} Add</button>
        </div>
        {error && <div className="mt-2 text-meta" style={{ color: '#f87171' }}>{error}</div>}
        {result && <div className="mt-3 flex items-center gap-1.5 text-meta" style={{ color: '#4ade80' }}><CheckCircle2 size={13} /> {result.message}</div>}
      </div>

      {result && (
        <div>
          <div className="text-micro uppercase mb-2">Updated Schema</div>
          <div className="panel overflow-hidden">
            <table className="dtable">
              <thead><tr><th style={{ width: 56 }}>ID</th><th>Column</th><th>Type</th></tr></thead>
              <tbody>
                {result.schema_fields.map((f) => (
                  <tr key={f.field_id}><td className="mono" style={{ color: '#52525b' }}>{f.field_id}</td><td style={{ color: '#f4f4f5' }}>{f.name}</td><td className="mono" style={{ color: '#a5b4fc' }}>{f.type}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
