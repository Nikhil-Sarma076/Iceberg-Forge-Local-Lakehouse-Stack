import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { CheckCircle2, XCircle, Loader2, Database, Server, HardDrive, Search, Cpu, Globe } from 'lucide-react';

type Status = 'healthy' | 'unhealthy' | 'checking';

interface ServiceNode {
  id: string;
  label: string;
  subtitle: string;
  icon: React.ReactNode;
  x: number;
  y: number;
  status: Status;
  detail: string[];
}

interface Flow {
  from: string;
  to: string;
  label: string;
  animated?: boolean;
}

const NODE_W = 168;
const NODE_H = 64;

export const ArchitectureView: React.FC = () => {
  const [services, setServices] = useState<ServiceNode[]>(initial());
  const [selected, setSelected] = useState<string | null>('fastapi');
  const [tableCount, setTableCount] = useState(0);

  useEffect(() => {
    check();
    const id = setInterval(check, 10000);
    return () => clearInterval(id);
  }, []);

  async function check() {
    try {
      const h = await api.checkHealth();
      set('fastapi', 'healthy', [`status: ${h.status}`, `version: ${h.version}`, 'framework: FastAPI', 'port: 8000']);
    } catch {
      set('fastapi', 'unhealthy', ['connection refused']);
    }
    try {
      const t = await api.listTables();
      setTableCount(t.length);
      set('catalog', 'healthy', [`tables: ${t.length}`, 'type: REST', 'backend: SQLite', 'uri: rest:8181']);
      set('minio', 'healthy', ['bucket: iceberg-warehouse', 'endpoint: minio:9000', t.length > 0 ? 'format: Parquet' : 'no data files']);
    } catch {
      set('catalog', 'unhealthy', ['catalog unreachable']);
      set('minio', 'unhealthy', ['storage unreachable']);
    }
    try {
      await api.executeQuery('SELECT 1');
      set('trino', 'healthy', ['engine: Trino 438', 'catalog: iceberg', 'schema: default', 'port: 8080']);
    } catch {
      set('trino', 'unhealthy', ['not responding']);
    }
    set('jobqueue', 'healthy', ['type: asyncio.Queue', 'workers: 1', 'storage: in-memory']);
    set('client', 'healthy', ['framework: React 19', 'bundler: Vite', 'port: 3001']);
  }

  function set(id: string, status: Status, detail: string[]) {
    setServices((prev) => prev.map((s) => (s.id === id ? { ...s, status, detail } : s)));
  }

  const flows: Flow[] = [
    { from: 'client', to: 'fastapi', label: 'HTTP', animated: true },
    { from: 'fastapi', to: 'jobqueue', label: 'enqueue' },
    { from: 'fastapi', to: 'catalog', label: 'PyIceberg' },
    { from: 'catalog', to: 'minio', label: 'Parquet' },
    { from: 'trino', to: 'catalog', label: 'metadata' },
    { from: 'trino', to: 'minio', label: 'scan' },
  ];

  const sel = services.find((s) => s.id === selected);
  const healthy = services.filter((s) => s.status === 'healthy').length;

  return (
    <div className="h-full flex">
      {/* Canvas */}
      <div className="flex-1 relative overflow-auto" style={{ background: 'radial-gradient(circle at 30% 20%, #131316 0%, var(--color-surface-0) 60%)' }}>
        {/* Legend */}
        <div className="absolute top-4 left-4 z-10 flex items-center gap-3">
          <div className="badge badge-neutral">{healthy}/{services.length} services healthy</div>
          <div className="badge badge-info">{tableCount} tables</div>
        </div>

        <svg className="absolute inset-0 w-full h-full pointer-events-none" style={{ minWidth: 820, minHeight: 520 }}>
          <defs>
            <marker id="arrow" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto">
              <polygon points="0 0, 6 3, 0 6" fill="#3f3f46" />
            </marker>
          </defs>
          {flows.map((f, i) => {
            const a = services.find((s) => s.id === f.from)!;
            const b = services.find((s) => s.id === f.to)!;
            const x1 = a.x + NODE_W / 2, y1 = a.y + NODE_H / 2;
            const x2 = b.x + NODE_W / 2, y2 = b.y + NODE_H / 2;
            return (
              <g key={i}>
                <line
                  x1={x1} y1={y1} x2={x2} y2={y2}
                  stroke={f.animated ? 'var(--color-accent)' : '#2a2a30'}
                  strokeWidth="1.5"
                  strokeDasharray={f.animated ? '4 4' : undefined}
                  markerEnd="url(#arrow)"
                  opacity={f.animated ? 0.6 : 1}
                >
                  {f.animated && (
                    <animate attributeName="stroke-dashoffset" from="8" to="0" dur="0.6s" repeatCount="indefinite" />
                  )}
                </line>
                <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 6} textAnchor="middle" fill="#52525b" style={{ fontSize: 10, fontFamily: 'var(--font-mono)' }}>
                  {f.label}
                </text>
              </g>
            );
          })}
        </svg>

        {services.map((n) => {
          const isSel = selected === n.id;
          return (
            <button
              key={n.id}
              onClick={() => setSelected(n.id)}
              className="absolute card flex items-center gap-3 px-3.5 transition-all"
              style={{
                left: n.x, top: n.y, width: NODE_W, height: NODE_H,
                borderColor: isSel ? 'var(--color-accent)' : 'var(--color-border)',
                boxShadow: isSel ? '0 0 0 3px rgba(99,102,241,0.15)' : 'none',
                background: 'var(--color-surface-2)',
              }}
            >
              <div
                className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                style={{ background: 'var(--color-surface-3)', color: isSel ? 'var(--color-accent)' : '#a1a1aa' }}
              >
                {n.icon}
              </div>
              <div className="text-left min-w-0">
                <div className="text-body font-medium truncate" style={{ color: '#f4f4f5' }}>{n.label}</div>
                <div className="text-micro truncate">{n.subtitle}</div>
              </div>
              <div className="ml-auto shrink-0">
                {n.status === 'checking' && <Loader2 size={14} className="animate-spin" style={{ color: '#52525b' }} />}
                {n.status === 'healthy' && <CheckCircle2 size={14} style={{ color: '#22c55e' }} />}
                {n.status === 'unhealthy' && <XCircle size={14} style={{ color: '#ef4444' }} />}
              </div>
            </button>
          );
        })}
      </div>

      {/* Inspector */}
      <div className="w-72 shrink-0 border-l flex flex-col" style={{ background: 'var(--color-surface-1)' }}>
        {sel ? (
          <div className="flex-1 overflow-y-auto">
            <div className="p-5 border-b">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: 'var(--color-surface-3)', color: 'var(--color-accent)' }}>
                  {sel.icon}
                </div>
                <div>
                  <div className="text-title">{sel.label}</div>
                  <div className="text-meta">{sel.subtitle}</div>
                </div>
              </div>
              <div className="mt-3">
                {sel.status === 'healthy' && <span className="badge badge-success"><CheckCircle2 size={12} /> Healthy</span>}
                {sel.status === 'unhealthy' && <span className="badge badge-error"><XCircle size={12} /> Unhealthy</span>}
                {sel.status === 'checking' && <span className="badge badge-neutral"><Loader2 size={12} className="animate-spin" /> Checking</span>}
              </div>
            </div>

            <div className="p-5 space-y-1.5">
              <div className="text-micro uppercase mb-2">Configuration</div>
              {sel.detail.map((d, i) => (
                <div key={i} className="text-meta mono px-3 py-1.5 rounded-md" style={{ background: 'var(--color-surface-0)' }}>{d}</div>
              ))}
            </div>

            {sel.id === 'fastapi' && (
              <div className="p-5 pt-0 space-y-1.5">
                <div className="text-micro uppercase mb-2">Endpoints</div>
                {['POST /v1/tables', 'POST /v1/jobs/ingest', 'POST /v1/tables/{t}/compact', 'POST /v1/tables/{t}/evolve-schema', 'POST /v1/query'].map((e) => (
                  <div key={e} className="text-meta mono" style={{ color: '#a5b4fc' }}>{e}</div>
                ))}
              </div>
            )}
            {sel.id === 'catalog' && (
              <div className="p-5 pt-0 space-y-1.5">
                <div className="text-micro uppercase mb-2">Iceberg Features</div>
                {['Schema evolution (stable IDs)', 'Snapshot isolation (MVCC)', 'Hidden partitioning', 'Time-travel queries'].map((c) => (
                  <div key={c} className="text-meta">{c}</div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-meta">Select a service</div>
        )}
      </div>
    </div>
  );
};

function initial(): ServiceNode[] {
  return [
    { id: 'client', label: 'React Client', subtitle: 'Web console', icon: <Globe size={18} />, x: 60, y: 120, status: 'healthy', detail: [] },
    { id: 'fastapi', label: 'FastAPI', subtitle: 'Ingestion API', icon: <Server size={18} />, x: 320, y: 120, status: 'checking', detail: [] },
    { id: 'jobqueue', label: 'Job Queue', subtitle: 'Async worker', icon: <Cpu size={18} />, x: 320, y: 280, status: 'checking', detail: [] },
    { id: 'catalog', label: 'Iceberg Catalog', subtitle: 'REST + SQLite', icon: <Database size={18} />, x: 580, y: 120, status: 'checking', detail: [] },
    { id: 'minio', label: 'MinIO', subtitle: 'S3 storage', icon: <HardDrive size={18} />, x: 580, y: 280, status: 'checking', detail: [] },
    { id: 'trino', label: 'Trino', subtitle: 'Query engine', icon: <Search size={18} />, x: 580, y: 420, status: 'checking', detail: [] },
  ];
}
