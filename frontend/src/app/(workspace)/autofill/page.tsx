'use client';

import { useEffect, useMemo, useState } from 'react';
import { autofillApi, type AutofillField } from '@/features/autofill/api';
import { dateKey, normalizeAutofillField, validDate } from '@/features/autofill/normalize';
import '@/features/autofill/styles.css';
const provenanceLabel = (p: string) =>
  p === 'verified'
    ? 'User-verified'
    : p === 'extracted_reviewed'
      ? 'Extracted & reviewed'
      : 'Unverified AI suggestion';
export default function AutofillPage() {
  const [cases, setCases] = useState<any[]>([]),
    [caseId, setCaseId] = useState(''),
    [fields, setFields] = useState<AutofillField[]>([]),
    [sourceDocs, setSourceDocs] = useState<any[]>([]),
    [drafts, setDrafts] = useState<any[]>([]),
    [draftId, setDraftId] = useState(''),
    [draftContent, setDraftContent] = useState(''),
    [choices, setChoices] = useState<Record<string, 'accept' | 'reject' | 'edit'>>({}),
    [overrides, setOverrides] = useState<Record<string, boolean>>({}),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(''),
    [error, setError] = useState(''),
    [previewed, setPreviewed] = useState(false);
  const refresh = async (id: string, preserveChoices = false) => {
    const [result, docs] = await Promise.all([autofillApi.get(id), autofillApi.documents(id)]);
    const lookup = docs.items ?? [];
    const rows = (result.fields ?? []).map((f: any) => {
      const normalized = normalizeAutofillField(f);
      const doc = lookup.find((d: any) => d.title === normalized.source_document);
      return { ...normalized, document_id: normalized.document_id ?? doc?.id };
    });
    setFields(rows);
    setSourceDocs(result.source_documents ?? lookup);
    if (!preserveChoices) setChoices({});
    setPreviewed(false);
    if (result.status === 'record_based')
      setMessage(
        'Showing case-record and extracted values. This API exposes no model suggestion route; no AI values are being presented as extracted facts.',
      );
  };
  useEffect(() => {
    autofillApi
      .cases()
      .then((r) => setCases(r.items ?? []))
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (!caseId) return;
    setError('');
    setMessage('');
    refresh(caseId).catch((e) => setError(`Autofill data unavailable: ${e.message}`));
    autofillApi
      .drafts()
      .then((r) => {
        const rows = (r.items ?? []).filter((d) => d.case_id === caseId);
        setDrafts(rows);
        setDraftId(rows[0]?.id ?? '');
      })
      .catch(() => {
        setDrafts([]);
        setDraftId('');
      });
  }, [caseId]);
  useEffect(() => {
    if (!draftId) return;
    autofillApi
      .draft(draftId)
      .then((d) => setDraftContent(String(d.content_markdown ?? '')))
      .catch((e) => setError(`Selected draft unavailable: ${e.message}`));
  }, [draftId]);
  const reviewed = useMemo(
    () => fields.filter((f) => f.provenance === 'extracted_reviewed' && f.value),
    [fields],
  );
  const doPreview = async () => {
    if (!caseId) return;
    setBusy(true);
    setError('');
    try {
      const result = await autofillApi.preview(
        caseId,
        fields.map((f) => f.key),
      );
      const rows = (result.fields ?? []).map((raw: any) => {
        const field = normalizeAutofillField(raw),
          previous = fields.find((x) => x.key === field.key);
        return {
          ...field,
          document_id: field.document_id ?? previous?.document_id,
          source_document: field.source_document ?? previous?.source_document,
        };
      });
      setFields(rows);
      setPreviewed(true);
      setMessage(
        rows.length
          ? 'Preview loaded. Confirm source and value for each field before applying.'
          : 'Preview returned no populated fields.',
      );
    } catch (e: any) {
      setError(`Preview failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };
  const apply = async () => {
    if (!caseId || !draftId) return;
    const accepted = fields.filter(
      (f) =>
        (choices[f.key] === 'accept' || choices[f.key] === 'edit') &&
        (!dateKey(f.key) || validDate(f.value)) &&
        (!f.provenance.startsWith('verified') || !overrides[f.key] || choices[f.key] === 'edit'),
    );
    if (!accepted.length) {
      setError('Accept at least one field before applying.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const currentDraft = await autofillApi.draft(draftId);
      const r = await autofillApi.apply(caseId, {
        fields: accepted.map((f) => ({ key: f.key, value: f.value, provenance: f.provenance })),
      });
      const base = String(currentDraft.content_markdown ?? draftContent)
        .split('\n## Accepted case details (autofill)\n')[0]
        .trimEnd();
      const detailLines = accepted.map(
        (f) =>
          `- ${f.label}: ${f.value} (provenance: ${f.provenance})${f.source_document ? ` (source: ${f.source_document}${f.page_number ? `, page ${f.page_number}` : ''})` : ''}${f.provenance === 'ai_suggested' ? ' [REVIEW: AI suggestion; verify before use]' : ''}`,
      );
      const updated = `${base}\n\n## Accepted case details (autofill)\n\n${detailLines.join('\n')}\n`;
      await autofillApi.saveDraftVersion(draftId, {
        content_markdown: updated,
        change_note: 'Applied reviewed autofill values',
      });
      setDraftContent(updated);
      const notice = `Applied ${accepted.length} accepted field(s) to the draft. Case record: ${r.applied?.length ?? 0} updated${r.skipped?.length ? `, ${r.skipped.length} skipped by server safeguards` : ''}.`;
      await refresh(caseId, true);
      setMessage(notice);
    } catch (e: any) {
      setError(`Apply failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };
  const bulkReviewed = () => {
    const next = { ...choices };
    reviewed.forEach((f) => {
      next[f.key] = 'accept';
    });
    setChoices(next);
  };
  const update = (key: string, value: string) => {
    setFields((rows) => rows.map((f) => (f.key === key ? { ...f, value, status: 'edited' } : f)));
    setChoices({ ...choices, [key]: 'edit' });
  };

  return (
    <main className="autofill">
      <header className="autofill-head">
        <div>
          <h1>Smart Autofill</h1>
          <p>Review every extracted value and its source before applying it.</p>
        </div>
        <a className="auto-button secondary" href="/drafts">
          AI Case Drafts →
        </a>
      </header>
      {error && (
        <div className="auto-message auto-error" role="alert">
          {error}{' '}
          <button className="auto-button secondary" onClick={() => caseId && refresh(caseId).catch(() => {})}>
            Retry
          </button>
        </div>
      )}
      {message && (
        <div className="auto-message" role="status">
          {message}
        </div>
      )}
      <section className="auto-card">
        <div className="auto-controls">
          <label htmlFor="autofill-case">
            <strong>Case</strong>
          </label>
          <select
            id="autofill-case"
            className="auto-select"
            value={caseId}
            onChange={(e) => {
              setCaseId(e.target.value);
              setDraftId('');
            }}
          >
            <option value="">Choose a case</option>
            {cases.map((c) => (
              <option value={c.id} key={c.id}>
                {c.title ?? c.case_title ?? c.name}
              </option>
            ))}
          </select>
          <label htmlFor="autofill-draft">
            <strong>Draft</strong>
          </label>
          <select
            id="autofill-draft"
            className="auto-select"
            value={draftId}
            onChange={(e) => setDraftId(e.target.value)}
            disabled={!caseId || !drafts.length}
          >
            <option value="">Choose a draft</option>
            {drafts.map((d) => (
              <option value={d.id} key={d.id}>
                {d.title ?? d.document_type ?? 'Draft'}
              </option>
            ))}
          </select>
          <button className="auto-button" disabled={!caseId || busy} onClick={doPreview}>
            {busy ? 'Loading…' : 'Preview fields'}
          </button>
          {fields.length > 0 && (
            <div className="auto-actions auto-apply-sticky">
              <button
                className="auto-button"
                disabled={!caseId || !draftId || busy || !previewed}
                onClick={apply}
              >
                Apply to Draft (
                {fields.filter((f) => choices[f.key] === 'accept' || choices[f.key] === 'edit').length}{' '}
                accepted)
              </button>
            </div>
          )}
        </div>
      </section>
      <details className="auto-card auto-sources">
        <summary>Extracted from Your Documents · {sourceDocs.length} sources</summary>
        {sourceDocs.length ? (
          sourceDocs.map((s, i) => (
            <div className="auto-source" key={s.id ?? i}>
              <span>▤</span>
              <div>
                <strong>{s.title ?? s.document_title ?? s.name}</strong>
                <small>
                  {s.pages ? `${s.pages} pages · ` : ''}
                  {s.status ?? 'Case library source'}
                </small>
              </div>
            </div>
          ))
        ) : (
          <p>
            {caseId
              ? 'Source locations are shown beside extracted fields where the API provides them.'
              : 'Choose a case to see available values.'}
          </p>
        )}
      </details>
      <section className="auto-card">
        <div className="autofill-head" style={{ marginBottom: 15 }}>
          <div>
            <h2 style={{ margin: 0 }}>Review extracted fields</h2>
            <p style={{ fontSize: 12, marginTop: 5 }}>
              Low-confidence or unsupported dates remain blank and require review.
            </p>
          </div>
          <button className="auto-button secondary" disabled={!reviewed.length} onClick={bulkReviewed}>
            Accept reviewed only ({reviewed.length})
          </button>
        </div>
        {!fields.length ? (
          <p className="auto-missing">
            Select a case, then preview the values available from its case record and documents.
          </p>
        ) : (
          <div className="auto-grid">
            {fields.map((f) => {
              const verified = f.provenance === 'verified',
                reviewedField = f.provenance === 'extracted_reviewed',
                choice = choices[f.key],
                decision =
                  choice === 'accept' || choice === 'edit'
                    ? 'Accepted'
                    : choice === 'reject'
                      ? 'Rejected'
                      : 'Not reviewed';
              return (
                <article className="auto-field" key={f.key} aria-label={`${f.label} ${decision}`}>
                  <div className="auto-field-top">
                    <label htmlFor={`field-${f.key}`}>{f.label}</label>
                    <span
                      className={`auto-provenance ${verified ? 'verified' : reviewedField ? 'reviewed' : 'suggested'}`}
                    >
                      {provenanceLabel(f.provenance)}
                    </span>
                  </div>
                  <input
                    id={`field-${f.key}`}
                    value={typeof f.value === 'string' ? f.value : String(f.value ?? '')}
                    placeholder="No value extracted"
                    readOnly={verified && !overrides[f.key]}
                    onChange={(e) => update(f.key, e.target.value)}
                  />
                  {String(f.value ?? '').length > 50 && (
                    <details className="auto-full-value">
                      <summary>Read full value</summary>
                      <p>{String(f.value)}</p>
                    </details>
                  )}
                  {decision !== 'Not reviewed' && (
                    <strong
                      className={`auto-decision ${choice === 'reject' ? 'rejected' : ''}`}
                      role="status"
                    >
                      {decision}
                    </strong>
                  )}
                  {verified && (
                    <div className="auto-actions">
                      <button
                        className="auto-button secondary"
                        onClick={() => {
                          setOverrides({ ...overrides, [f.key]: !overrides[f.key] });
                          setChoices({ ...choices, [f.key]: 'edit' });
                        }}
                      >
                        {overrides[f.key] ? 'Cancel override' : 'Override verified value'}
                      </button>
                    </div>
                  )}
                  {f.status === 'needs_review' && (
                    <div className="auto-conflict">
                      Date candidate rejected: a year alone or invalid calendar date is not accepted. Review
                      the source before entering a date.
                    </div>
                  )}
                  {f.source_document && (
                    <>
                      {f.document_id ? (
                        <a
                          className="auto-source-link"
                          href={`/documents/${f.document_id}?page=${f.page_number ?? 1}`}
                        >
                          {f.source_document}
                          {f.page_number ? ` · p. ${f.page_number}` : ''}
                        </a>
                      ) : (
                        <span className="auto-source-link">Source page unavailable</span>
                      )}
                    </>
                  )}
                  <div className="auto-actions">
                    <button
                      className="auto-button secondary"
                      onClick={() => setChoices({ ...choices, [f.key]: 'accept' })}
                    >
                      Accept
                    </button>
                    <button
                      className="auto-button secondary"
                      onClick={() => setChoices({ ...choices, [f.key]: 'reject' })}
                    >
                      Reject
                    </button>
                    <span className="auto-missing">
                      Confidence {f.confidence === undefined ? '—' : `${Math.round(f.confidence * 100)}%`}
                    </span>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}
