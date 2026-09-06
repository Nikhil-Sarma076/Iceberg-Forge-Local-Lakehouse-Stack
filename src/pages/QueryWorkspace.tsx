import React, { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { TableSummary, QueryResponse } from '../types';
import { Play, Table2, Clock, Download, Loader2, AlertCircle, Database } from 'lucide-react';

interface HistoryEntry {
  sql: string;
  at: number;
  rows: number;
  ok: boolean;
}

const STARTER_SQL = 'SELECT *\nFROM iceberg.default.<table>\nLIMIT 100';

export const QueryWorkspace: React.FC = () => {
  const [tables, setTables] = useState<TableSummary[]>([]);
  const [sql, setSql] = useState(STARTER_SQL);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState<number | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    api.listTables().then(setTables).catch(() => {});
  }, []);

  const run = async () => {
    if (!sql.trim() || running) return;
    setRunning(true);
    setError(null);
    setResult(null);
    const start = performance.now();
    try {
      const data = await api.executeQuery(sql);
      const ms = Math.round(performance.now() - start);
      setResult(data);
      setElapsed(ms);
      setHistory((h) => [{ sql, at: Date.now(), rows: data.row_count, ok: true }, ...h].slice(0, 20));
    } catch (err: any) {
      setError(err.message);
      setElapsed(Math.round(performance.now() - start));
      setHistory((h) => [{ sql, at: Date.now(), rows: 0, ok: false }, ...h].slice(0, 20));
    } finally {
      setRunning(false);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      run();
    }
  };

  const insertTable = (name: string) => {
    const stmt = `SELECT *\nFROM iceberg.default.${name}\nLIMIT 100`;
    setSql(stmt);
    textareaRef.current?.focus();
  };

  const exportCsv = () => {
    if (!result) return;
    const header = result.columns.join(',');
    const body = result.rows
      .map((r) => r.map((c) => (c === null ? '' : `"${String(c).replace(/"/g, '""')}"`)).join(','))
      .join('\n');
    const blob = new Blob([`${header}\n${body}`], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'query_result.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="h-full flex">
      {/* Left rail: tables + history */}
      <div className="w-60 shrink-0 border-r flex flex-col" style={{ background: 'var(--color-surface-1)' }}>
        <div className="px-4 py-3 border-b">
          <div className="text-micro uppercase">Tables</div>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {tables.length === 0 ? (
            <div className="px-2 py-4 text-meta">No tables. Ingest data first.</div>
          ) : (
            tables.map((t) => (
              <button
                key={t.identifier}
                onClick={() => insertTable(t.name)}
                className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-left transition-colors"
                onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-surface-3)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                <Table2 size={14} style={{ color: '#71717a' }} />
                <span className="text-body truncate">{t.name}</span>
                <span className="text-micro mono ml-auto">{t.total_records.toLocaleString()}</span>
              </button>
            ))
          )}
        </div>

        {history.length > 0 && (
          <div className="border-t max-h-56 overflow-y-auto">
            <div className="px-4 py-3 border-b flex items-center gap-1.5">
              <Clock size={12} style={{ color: '#71717a' }} />
              <span className="text-micro uppercase">History</span>
            </div>
            <div className="p-2 space-y-1">
              {history.map((h, i) => (
                <button
                  key={i}
                  onClick={() => setSql(h.sql)}
                  className="w-full text-left px-2.5 py-1.5 rounded-md transition-colors group"
                  onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-surface-3)')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                >
                  <div className="flex items-center gap-1.5">
                    <span
                      className="w-1.5 h-1.5 rounded-full shrink-0"
                      style={{ background: h.ok ? '#22c55e' : '#ef4444' }}
                    />
                    <span className="text-micro mono truncate">
                      {h.sql.replace(/\s+/g, ' ').slice(0, 32)}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Editor + results */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Editor */}
        <div className="p-4 border-b" style={{ background: 'var(--color-surface-1)' }}>
          <div className="panel overflow-hidden" style={{ background: 'var(--color-surface-0)' }}>
            <textarea
              ref={textareaRef}
              value={sql}
              onChange={(e) => setSql(e.target.value)}
              onKeyDown={onKeyDown}
              spellCheck={false}
              className="w-full h-40 p-4 mono resize-none bg-transparent outline-none"
              style={{ fontSize: '13px', lineHeight: '1.6', color: '#e4e4e7' }}
              placeholder="Write SQL — read-only SELECT queries via Trino"
            />
            <div className="flex items-center justify-between px-3 py-2 border-t" style={{ background: 'var(--color-surface-1)' }}>
              <div className="flex items-center gap-3">
                <button onClick={run} disabled={running || !sql.trim()} className="btn btn-primary btn-sm">
                  {running ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
                  Run
                </button>
                <span className="text-micro">⌘/Ctrl + Enter</span>
              </div>
              {elapsed !== null && !running && (
                <span className="text-micro mono">{elapsed} ms</span>
              )}
            </div>
          </div>
        </div>

        {/* Results */}
        <div className="flex-1 overflow-hidden flex flex-col">
          {error ? (
            <div className="p-4">
              <div className="card p-4 flex items-start gap-3" style={{ borderColor: 'rgba(248,113,113,0.3)' }}>
                <AlertCircle size={16} className="text-red-400 mt-0.5 shrink-0" />
                <div>
                  <div className="text-body font-medium text-red-400">Query failed</div>
                  <div className="text-meta mono mt-1">{error}</div>
                </div>
              </div>
            </div>
          ) : result ? (
            <>
              <div className="flex items-center justify-between px-4 py-2.5 border-b">
                <span className="text-meta">
                  <span className="text-body font-medium" style={{ color: '#f4f4f5' }}>{result.row_count}</span> row{result.row_count !== 1 ? 's' : ''} · {result.columns.length} column{result.columns.length !== 1 ? 's' : ''}
                </span>
                <button onClick={exportCsv} className="btn btn-subtle btn-sm">
                  <Download size={13} /> Export CSV
                </button>
              </div>
              <div className="flex-1 overflow-auto">
                {result.row_count === 0 ? (
                  <div className="h-full flex items-center justify-center text-meta">Query returned no rows.</div>
                ) : (
                  <table className="dtable">
                    <thead>
                      <tr>
                        <th style={{ width: 44 }}>#</th>
                        {result.columns.map((c, i) => (
                          <th key={i} className="whitespace-nowrap">{c}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.rows.map((row, ri) => (
                        <tr key={ri}>
                          <td className="mono" style={{ color: '#52525b' }}>{ri + 1}</td>
                          {row.map((cell, ci) => (
                            <td key={ci} className="mono whitespace-nowrap">
                              {cell === null ? <span style={{ color: '#52525b', fontStyle: 'italic' }}>null</span> : String(cell)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </>
          ) : (
            <div className="h-full flex items-center justify-center">
              <div className="text-center">
                <Database size={28} style={{ color: '#3f3f46', margin: '0 auto 12px' }} />
                <div className="text-body" style={{ color: '#71717a' }}>Run a query to see results</div>
                <div className="text-meta mt-1">Pick a table on the left or write SQL above</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
