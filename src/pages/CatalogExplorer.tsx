import React, { useEffect, useState, useRef } from 'react';
import { api } from '../api/client';
import type { TableSummary } from '../types';
import { TableDetail as TableDetailPanel } from './TableDetail';
import {
  Database, Table2, ChevronDown, ChevronRight, RefreshCw, Plus,
  Upload, Trash2, Loader2, FileUp, X,
} from 'lucide-react';

export const CatalogExplorer: React.FC = () => {
  const [tables, setTables] = useState<TableSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const d = await api.listTables();
      setTables(d);
    } catch {
      setTables([]);
    } finally {
      setLoading(false);
    }
  };

  const drop = async (name: string) => {
    if (!window.confirm(`Drop table "${name}"? This cannot be undone.`)) return;
    try {
      await api.dropTable(name);
      if (selected === name) setSelected(null);
      await load();
    } catch (e: any) {
      alert(`Failed: ${e.message}`);
    }
  };

  return (
    <div className="h-full flex">
      {/* Tree */}
      <div className="w-64 shrink-0 border-r flex flex-col" style={{ background: 'var(--color-surface-1)' }}>
        <div className="h-12 flex items-center justify-between px-4 border-b">
          <span className="text-micro uppercase">Catalog</span>
          <div className="flex items-center gap-1">
            <button onClick={() => setShowCreate(true)} className="btn-icon btn-subtle" title="Create table"><Plus size={15} /></button>
            <button onClick={load} className="btn-icon btn-subtle" title="Refresh"><RefreshCw size={14} /></button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          {loading ? (
            <div className="flex justify-center py-8"><Loader2 size={18} className="animate-spin" style={{ color: '#52525b' }} /></div>
          ) : (
            <>
              <button
                onClick={() => setExpanded(!expanded)}
                className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg transition-colors"
                onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-surface-3)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                <Database size={14} style={{ color: 'var(--color-accent)' }} />
                <span className="text-body font-medium">default</span>
                <span className="text-micro mono ml-auto">{tables.length}</span>
              </button>

              {expanded && (
                <div className="mt-1 pl-3 space-y-0.5">
                  {tables.length === 0 && <div className="px-3 py-3 text-meta">No tables yet</div>}
                  {tables.map((t) => {
                    const isSel = selected === t.name;
                    return (
                      <div key={t.identifier} className="group flex items-center">
                        <button
                          onClick={() => setSelected(t.name)}
                          className="flex-1 flex items-center gap-2 px-2.5 py-2 rounded-lg transition-colors text-left min-w-0"
                          style={{ background: isSel ? 'var(--color-accent-subtle)' : 'transparent', color: isSel ? '#c7d2fe' : '#a1a1aa' }}
                          onMouseEnter={(e) => { if (!isSel) e.currentTarget.style.background = 'var(--color-surface-3)'; }}
                          onMouseLeave={(e) => { if (!isSel) e.currentTarget.style.background = 'transparent'; }}
                        >
                          <Table2 size={13} style={{ color: isSel ? 'var(--color-accent)' : '#52525b' }} />
                          <span className="text-body truncate">{t.name}</span>
                          <span className="text-micro mono ml-auto shrink-0">{t.total_records.toLocaleString()}</span>
                        </button>
                        <button
                          onClick={() => drop(t.name)}
                          className="btn-icon btn-danger opacity-0 group-hover:opacity-100 transition-opacity"
                          title="Drop"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Detail */}
      <div className="flex-1 overflow-hidden">
        {selected ? (
          <TableDetailPanel tableName={selected} onChanged={load} />
        ) : (
          <div className="h-full flex items-center justify-center">
            <div className="text-center">
              <Table2 size={32} style={{ color: '#3f3f46', margin: '0 auto 14px' }} />
              <div className="text-body" style={{ color: '#71717a' }}>Select a table to inspect</div>
              <button onClick={() => setShowCreate(true)} className="btn btn-ghost btn-sm mt-4"><Plus size={13} /> Create table</button>
            </div>
          </div>
        )}
      </div>

      {showCreate && <CreateModal onClose={() => setShowCreate(false)} onCreated={(n) => { setShowCreate(false); load(); setSelected(n); }} />}
    </div>
  );
};

// ---- Create Table Modal ----

const CreateModal: React.FC<{ onClose: () => void; onCreated: (name: string) => void }> = ({ onClose, onCreated }) => {
  const [name, setName] = useState('');
  const [path, setPath] = useState('');
  const [uploaded, setUploaded] = useState<File | null>(null);
  const [serverFile, setServerFile] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const upload = async (f: File) => {
    setUploaded(f);
    setUploading(true);
    setError(null);
    try {
      const p = await api.previewFile(f);
      setServerFile(p.file);
      setPath(p.file);
      if (!name) setName(f.name.replace(/\.[^.]+$/, '').replace(/[^a-zA-Z0-9_]/g, '_').toLowerCase());
    } catch (e: any) {
      setError(`Upload failed: ${e.message}`);
      setUploaded(null);
    } finally {
      setUploading(false);
    }
  };

  const create = async () => {
    const file = serverFile || path.trim();
    if (!name.trim() || !file) return;
    setCreating(true);
    setError(null);
    try {
      await api.createTable(name.trim(), file);
      onCreated(name.trim().toLowerCase());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.6)' }} onClick={onClose}>
      <div className="panel w-full max-w-md animate-in" style={{ background: 'var(--color-surface-1)' }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <span className="text-title">Create Table</span>
          <button onClick={onClose} className="btn-icon btn-subtle"><X size={16} /></button>
        </div>

        <div className="p-5 space-y-4">
          {/* Upload */}
          <div
            onClick={() => fileRef.current?.click()}
            className="rounded-lg p-6 text-center cursor-pointer transition-colors"
            style={{ border: `1.5px dashed ${uploaded ? 'var(--color-accent)' : 'var(--color-border-strong)'}`, background: uploaded ? 'var(--color-accent-subtle)' : 'var(--color-surface-0)' }}
          >
            <input ref={fileRef} type="file" className="hidden" accept=".csv,.json,.jsonl,.ndjson,.parquet,.pq" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
            {uploading ? (
              <div className="flex items-center justify-center gap-2 text-meta"><Loader2 size={15} className="animate-spin" /> Uploading…</div>
            ) : uploaded ? (
              <div className="flex items-center justify-center gap-2">
                <FileUp size={16} style={{ color: 'var(--color-accent)' }} />
                <span className="text-body" style={{ color: '#c7d2fe' }}>{uploaded.name}</span>
                <span className="text-micro">({(uploaded.size / 1024).toFixed(1)} KB)</span>
              </div>
            ) : (
              <>
                <Upload size={20} style={{ color: '#52525b', margin: '0 auto 8px' }} />
                <div className="text-body" style={{ color: '#a1a1aa' }}>Click to upload a file</div>
                <div className="text-micro mt-1">CSV · JSON · Parquet</div>
              </>
            )}
          </div>

          {!uploaded && (
            <div>
              <label className="text-micro uppercase">Or server path</label>
              <input className="input mt-1.5" value={path} onChange={(e) => setPath(e.target.value)} placeholder="sales.csv" />
            </div>
          )}

          <div>
            <label className="text-micro uppercase">Table name</label>
            <input className="input mt-1.5" value={name} onChange={(e) => setName(e.target.value)} placeholder="my_table" />
          </div>

          {error && <div className="text-meta px-3 py-2 rounded-md" style={{ background: 'rgba(248,113,113,0.1)', color: '#f87171' }}>{error}</div>}
        </div>

        <div className="flex justify-end gap-2 px-5 py-4 border-t">
          <button onClick={onClose} className="btn btn-ghost">Cancel</button>
          <button onClick={create} disabled={creating || !name.trim() || (!path.trim() && !serverFile)} className="btn btn-primary">
            {creating ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} Create
          </button>
        </div>
      </div>
    </div>
  );
};
