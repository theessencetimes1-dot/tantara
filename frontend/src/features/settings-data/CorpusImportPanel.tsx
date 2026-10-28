'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api/client';

type Manifest = Record<string, unknown>;
function entries(value: unknown): Array<[string, unknown]> {
  if (Array.isArray(value)) return value.map((item, index) => [String(index + 1), item]);
  if (value && typeof value === 'object') return Object.entries(value as Record<string, unknown>);
  return [];
}
function show(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}
export function CorpusImportPanel() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const pollCount = useRef(0);
  const importStartedAt = useRef<number | null>(null);
  const refresh = useCallback(async () => {
    try {
      const result = await api.get<Manifest>('/settings/data/import');
      setManifest(result);
      setError('');
      const status = String(result.status ?? '').toLowerCase();
      const active = ['queued', 'running', 'pending', 'started', 'importing'].includes(status);
      if (active) {
        setPending(true);
      } else if (status !== 'not_imported') {
        const retrievedAt = Date.parse(String(result.retrieved_at ?? ''));
        const hasFreshManifest = importStartedAt.current === null || retrievedAt > importStartedAt.current;
        if (hasFreshManifest) {
          importStartedAt.current = null;
          setPending(false);
          pollCount.current = 0;
        }
      }
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : 'Manifest unavailable');
    }
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  useEffect(() => {
    if (!pending) return;
    const timer = window.setInterval(() => {
      pollCount.current += 1;
      if (pollCount.current > 90) {
        setPending(false);
        setError('Import was accepted, but no terminal manifest was returned after 225 seconds.');
        return;
      }
      void refresh();
    }, 2500);
    return () => window.clearInterval(timer);
  }, [pending, refresh]);
  async function start() {
    if (
      !window.confirm(
        'This downloads public legal corpus sources from the internet and indexes them in this workspace. It requires an internet connection. Continue?',
      )
    )
      return;
    setBusy(true);
    setError('');
    const requestedAt = Date.now();
    try {
      await api.post<{ status: string; process_id: number }>('/settings/data/import');
      pollCount.current = 0;
      importStartedAt.current = requestedAt;
      setPending(true);
    } catch (issue) {
      importStartedAt.current = null;
      setError(issue instanceof Error ? issue.message : 'Import could not be started');
    } finally {
      setBusy(false);
    }
  }
  const records = manifest ? entries(manifest.sources ?? manifest.items ?? manifest.manifest) : [];
  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <p className="muted">
        Review the last recorded corpus manifest, or start a public source import. Importing needs internet
        access.
      </p>
      {error && (
        <p role="alert" className="offline">
          {error}
        </p>
      )}
      <button className="primary" disabled={busy} onClick={() => void start()}>
        {busy ? 'Starting import…' : 'Import public legal corpus'}
      </button>
      {pending && <p role="status">Import is in progress. Status refreshes automatically.</p>}
      <section>
        <h3>Corpus manifest</h3>
        {manifest && (
          <p>
            Status: <strong>{show(manifest.status)}</strong>
            {' · '}Source records: {records.length || '—'}
          </p>
        )}
        {manifest ? (
          records.length ? (
            records.map(([key, item]) => (
              <article className="card" key={key} style={{ padding: 14, marginBottom: 10 }}>
                <strong>
                  {typeof item === 'object' && item
                    ? show((item as Manifest).source_name ?? (item as Manifest).name ?? key)
                    : key}
                </strong>
                <dl className="data-list">
                  {entries(item).map(([field, value]) => (
                    <div key={field}>
                      <dt>{field.replaceAll('_', ' ')}</dt>
                      <dd>{show(value)}</dd>
                    </div>
                  ))}
                </dl>
              </article>
            ))
          ) : (
            <dl className="data-list">
              {entries(manifest).map(([key, value]) => (
                <div key={key}>
                  <dt>{key.replaceAll('_', ' ')}</dt>
                  <dd>{show(value)}</dd>
                </div>
              ))}
            </dl>
          )
        ) : (
          <p role="status">Loading manifest…</p>
        )}
      </section>
      <section>
        <h3>Storage and index</h3>
        <p>
          Data directory:{' '}
          <code>{show(manifest?.data_dir ?? manifest?.tantara_data_dir ?? 'Not reported by this API')}</code>
        </p>
        <p>
          Index size: {show(manifest?.index_size ?? manifest?.index_size_bytes ?? 'Not reported by this API')}
        </p>
        <p className="muted">
          To rebuild the index, run from the repository root:{' '}
          <code>
            TANTARA_DATA_DIR=/path/to/data DATABASE_URL=sqlite:////path/to/data/tantara.db
            backend/.venv/bin/python scripts/rebuild_index.py
          </code>
        </p>
      </section>
    </div>
  );
}
