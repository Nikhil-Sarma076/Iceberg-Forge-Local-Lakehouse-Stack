import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Boxes, GitBranch, Database, Terminal, Activity } from 'lucide-react';

export type Tab = 'architecture' | 'catalog' | 'query' | 'jobs';

interface AppShellProps {
  children?: React.ReactNode;
  activeTab: Tab;
  onTabChange: (tab: Tab) => void;
}

const NAV: { id: Tab; label: string; icon: React.ReactNode; hint: string }[] = [
  { id: 'architecture', label: 'Architecture', icon: <GitBranch size={18} />, hint: 'Service topology & health' },
  { id: 'catalog', label: 'Catalog', icon: <Database size={18} />, hint: 'Tables, schema & maintenance' },
  { id: 'query', label: 'Query', icon: <Terminal size={18} />, hint: 'SQL workspace' },
  { id: 'jobs', label: 'Jobs', icon: <Activity size={18} />, hint: 'Async ingestion queue' },
];

export const AppShell: React.FC<AppShellProps> = ({ children, activeTab, onTabChange }) => {
  const [ready, setReady] = useState<boolean | null>(null);
  const [version, setVersion] = useState<string>('');

  useEffect(() => {
    let mounted = true;
    const check = async () => {
      try {
        const h = await api.checkHealth();
        if (mounted) { setReady(true); setVersion(h.version); }
      } catch {
        if (mounted) setReady(false);
      }
    };
    check();
    const id = setInterval(check, 8000);
    return () => { mounted = false; clearInterval(id); };
  }, []);

  const active = NAV.find((n) => n.id === activeTab);

  return (
    <div className="h-full flex" style={{ background: 'var(--color-surface-0)' }}>
      {/* Sidebar */}
      <aside className="w-60 shrink-0 flex flex-col border-r" style={{ background: 'var(--color-surface-1)' }}>
        {/* Brand */}
        <div className="h-16 flex items-center gap-2.5 px-5 border-b">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'var(--color-accent)' }}>
            <Boxes size={18} className="text-white" />
          </div>
          <div>
            <div className="text-title leading-tight">Iceberg Forge</div>
            <div className="text-micro">Lakehouse Console</div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 p-3 space-y-1">
          {NAV.map((n) => {
            const isActive = activeTab === n.id;
            return (
              <button
                key={n.id}
                onClick={() => onTabChange(n.id)}
                className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all text-left group"
                style={{
                  background: isActive ? 'var(--color-accent-subtle)' : 'transparent',
                  color: isActive ? '#c7d2fe' : '#a1a1aa',
                }}
                onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = 'var(--color-surface-3)'; }}
                onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.background = 'transparent'; }}
              >
                <span style={{ color: isActive ? 'var(--color-accent)' : '#71717a' }}>{n.icon}</span>
                <span className="text-body font-medium">{n.label}</span>
                {isActive && <span className="ml-auto w-1.5 h-1.5 rounded-full" style={{ background: 'var(--color-accent)' }} />}
              </button>
            );
          })}
        </nav>

        {/* Footer / status */}
        <div className="p-4 border-t space-y-2">
          <div className="flex items-center gap-2">
            <span
              className="w-2 h-2 rounded-full"
              style={{ background: ready ? '#22c55e' : ready === false ? '#ef4444' : '#71717a' }}
            />
            <span className="text-meta">
              {ready === null ? 'Connecting…' : ready ? 'API online' : 'API offline'}
            </span>
          </div>
          {version && <div className="text-micro mono">v{version}</div>}
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="h-16 shrink-0 flex items-center justify-between px-6 border-b" style={{ background: 'var(--color-surface-1)' }}>
          <div>
            <h1 className="text-display leading-tight">{active?.label}</h1>
            <p className="text-meta">{active?.hint}</p>
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-hidden animate-in" style={{ background: 'var(--color-surface-0)' }}>
          {children}
        </main>
      </div>
    </div>
  );
};
