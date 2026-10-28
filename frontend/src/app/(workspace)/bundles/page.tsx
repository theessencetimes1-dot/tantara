'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { ArrowRight, FileText, Plus } from 'lucide-react';
import { bundleApi, type Bundle, type CaseOption } from '@/features/bundles/api';
import { workspaceDateTimeDisplay } from '@/lib/datetime';
import '@/features/bundles/bundles.css';

type ListedBundle = Bundle;
const defaultSettings = { cover_page: true, index: true, synopsis: true, list_of_dates: true };
function formatFileSize(bytes?: number | null) {
  if (bytes == null) return 'Not generated';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
function formatUpdated(value?: string) {
  if (!value) return '—';
  return workspaceDateTimeDisplay(value);
}

export default function BundlesPage() {
  const [bundles, setBundles] = useState<ListedBundle[]>([]);
  const [cases, setCases] = useState<CaseOption[]>([]);
  const [name, setName] = useState('');
  const [caseId, setCaseId] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const reload = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [bundleResult, caseResult] = await Promise.all([bundleApi.list(), bundleApi.cases()]);
      setBundles(bundleResult.items);
      setCases(caseResult.items);
      setCaseId((current) => current || caseResult.items[0]?.id || '');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Filing bundles are unavailable.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => void reload(), [reload]);

  const createBundle = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim() || !caseId) return;
    setSaving(true);
    setError('');
    try {
      const bundle = await bundleApi.create({
        name: name.trim(),
        case_id: caseId,
        settings: defaultSettings,
      });
      window.location.assign(`/bundles/${bundle.id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not create this bundle.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bundle-page bundle-list-page">
      <header className="bundle-head">
        <div>
          <div className="bundle-eyebrow">MODULE 08 · DOCUMENT ASSEMBLY</div>
          <h1>Filing Bundles</h1>
          <p>Build, review, and download case paperbooks.</p>
        </div>
        <button className="bundle-primary" onClick={() => setShowCreate((value) => !value)}>
          <Plus size={16} /> {showCreate ? 'Close' : 'New bundle'}
        </button>
      </header>

      {error && (
        <div className="bundle-notice" role="alert">
          {error}
        </div>
      )}
      {showCreate && (
        <form className="bundle-card bundle-create-form" onSubmit={(event) => void createBundle(event)}>
          <h2>Create a filing bundle</h2>
          <div className="bundle-create-fields">
            <label>
              <span>Bundle name</span>
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
                maxLength={300}
              />
            </label>
            <label>
              <span>Case</span>
              <select value={caseId} onChange={(event) => setCaseId(event.target.value)} required>
                {cases.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <button className="bundle-primary" disabled={saving || !caseId || !name.trim()}>
            <Plus size={15} /> {saving ? 'Creating…' : 'Create bundle'}
          </button>
        </form>
      )}

      <section className="bundle-card bundle-list-card" aria-labelledby="bundle-list-title">
        <div className="bundle-list-heading">
          <div>
            <span className="bundle-step">YOUR WORKSPACE</span>
            <h2 id="bundle-list-title">Saved bundles</h2>
          </div>
          {!loading && (
            <span className="bundle-count">
              {bundles.length} {bundles.length === 1 ? 'bundle' : 'bundles'}
            </span>
          )}
        </div>
        {loading ? (
          <div className="bundle-load-state" role="status">
            Loading bundles…
          </div>
        ) : bundles.length ? (
          <div className="bundle-list">
            {bundles.map((bundle) => (
              <Link className="bundle-list-row" href={`/bundles/${bundle.id}`} key={bundle.id}>
                <span className="bundle-list-icon">
                  <FileText size={19} />
                </span>
                <span className="bundle-list-name">
                  <strong>{bundle.name}</strong>
                  <small>{bundle.case_title || 'Unassigned case'}</small>
                  <small>
                    {bundle.page_count ?? 0} pages · {formatFileSize(bundle.file_size_bytes)} · Updated{' '}
                    {formatUpdated(bundle.updated_at)}
                  </small>
                </span>
                <span className="bundle-list-meta">
                  <span className={`bundle-status-pill status-${bundle.status}`}>{bundle.status}</span>
                  <small>
                    {bundle.section_count ?? 0} {(bundle.section_count ?? 0) === 1 ? 'section' : 'sections'}
                  </small>
                </span>
                <ArrowRight size={17} className="bundle-list-arrow" />
              </Link>
            ))}
          </div>
        ) : (
          <div className="bundle-empty bundle-list-empty">
            <FileText size={27} />
            <strong>No filing bundles yet</strong>
            <span>Create a bundle, select a case, and add documents to prepare a paperbook.</span>
            <button className="bundle-primary" onClick={() => setShowCreate(true)}>
              <Plus size={15} /> Create your first bundle
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
