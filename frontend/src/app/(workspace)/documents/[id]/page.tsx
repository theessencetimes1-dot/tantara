'use client';
import { useState } from 'react';
import type { ReactNode } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { api, authToken } from '@/lib/api/client';
import { RefreshCw, FileText, Download, Sparkles, Pencil, Check } from 'lucide-react';
import { documentsApi } from '@/features/documents/api';
import { aiFailureMessage, classifyAiFailure, type AiFailure } from '@/features/documents/ai-read-errors';
import { DocumentStatus } from '@/features/documents/DocumentStatus';
import { WorkspaceModuleNav } from '@/features/documents/WorkspaceModuleNav';
import { PdfDocumentViewer } from '@/features/viewer/PdfDocumentViewer';
import { toast } from 'sonner';
import '@/features/documents/documents.css';
import './document-detail.css';
type Doc = {
  id: string;
  title: string;
  document_type?: string;
  status?: string;
  jurisdiction?: string;
  case_id?: string;
  created_at?: string;
  pages?: number;
  page_count?: number;
  filename?: string;
  content_hash?: string;
  size_bytes?: number;
  is_demo?: boolean;
  source_label?: string;
  processed_at?: string;
};
type Page = { page_number: number; text?: string; ocr_confidence?: number; warnings?: string[] };
type Extraction = {
  review_required?: boolean;
  fields?: Record<
    string,
    { value: unknown; provenance?: string; source?: string; review_required?: boolean }
  >;
};
type ChunkHit = {
  document_id: string;
  page_number: number;
  snippet?: string;
  retrieval_score?: number;
  retreival_score?: number;
  score?: number;
};

function renderExtractionValue(value: unknown): ReactNode {
  if (value == null || value === '') return <span className="ai-read-not-found">Not extracted</span>;
  if (Array.isArray(value)) {
    if (!value.length) return <span className="ai-read-not-found">Not extracted</span>;
    return (
      <ul>
        {value.map((item, index) => (
          <li key={index}>{renderExtractionValue(item)}</li>
        ))}
      </ul>
    );
  }
  if (typeof value === 'string' && /^[\[{]/.test(value.trim())) {
    try {
      return renderExtractionValue(JSON.parse(value));
    } catch {
      return <span>{value}</span>;
    }
  }
  if (typeof value === 'object') {
    const fields = value as Record<string, unknown>;
    if (fields.found === false) return <span className="ai-read-not-found">Not extracted</span>;
    if ('value' in fields) return renderExtractionValue(fields.value);
    if (typeof fields.quote === 'string' && fields.quote.trim())
      return <blockquote>{fields.quote}</blockquote>;
    const entries = Object.entries(fields).filter(
      ([key, entry]) =>
        !['page', 'page_number', 'source_page'].includes(key) && entry != null && entry !== '',
    );
    if (!entries.length) return <span className="ai-read-not-found">Not extracted</span>;
    return (
      <ul>
        {entries.map(([key, entry]) => (
          <li key={key}>
            <strong>{key.replaceAll('_', ' ')}:</strong> {renderExtractionValue(entry)}
          </li>
        ))}
      </ul>
    );
  }
  return String(value);
}

function extractionSourcePage(value: unknown): number | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  const fields = value as Record<string, unknown>;
  const page = fields.page ?? fields.page_number ?? fields.source_page;
  if (typeof page === 'number' && Number.isFinite(page) && page > 0) return page;
  return extractionSourcePage(fields.value);
}

function provenanceLabel(value?: string, source?: string) {
  if (source?.toLowerCase().includes('local text extraction'))
    return 'Local text extraction · candidate only';
  if (value === 'ai_suggested') return 'AI suggestion';
  if (value === 'extracted_reviewed') return 'Reviewed extraction';
  return value ? value.replaceAll('_', ' ') : 'Candidate extraction';
}

function deduplicateExtractedText(value: unknown): unknown {
  if (typeof value !== 'string') return value;
  const sentences = value.match(/[^.!?]+[.!?]?/g) ?? [value];
  const seen = new Set<string>();
  return sentences
    .map((sentence) => sentence.trim())
    .filter((sentence) => {
      const normalized = sentence.replace(/\s+/g, ' ').toLocaleLowerCase();
      if (!normalized || seen.has(normalized)) return false;
      seen.add(normalized);
      return true;
    })
    .join(' ');
}

function formatMetadataDate(value?: string) {
  if (!value) return '—';
  return new Date(value).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

export default function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const doc = useQuery({ queryKey: ['documents', id], queryFn: () => api.get<Doc>(`/documents/${id}`) });
  const text = useQuery({
    queryKey: ['documents', id, 'text'],
    queryFn: () => api.get<{ text?: string; pages?: Page[] }>(`/documents/${id}/text`),
  });
  const pages = useQuery({
    queryKey: ['documents', id, 'pages'],
    queryFn: () => api.get<{ pages?: Page[] }>(`/documents/${id}/pages`),
  });
  const extraction = useQuery({
    queryKey: ['documents', id, 'ai-read'],
    queryFn: () => api.get<Extraction>(`/documents/${id}/ai-read`),
  });
  const aiSettings = useQuery({
    queryKey: ['settings', 'ai'],
    queryFn: () => documentsApi.aiStatus(),
  });
  const [reading, setReading] = useState(false);
  const [editingField, setEditingField] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const [aiOutcome, setAiOutcome] = useState<
    'idle' | 'ready' | 'model_unavailable' | 'no_evidence' | AiFailure
  >('idle');
  const [copiedHash, setCopiedHash] = useState(false);
  const [chunkSearch, setChunkSearch] = useState('');
  const [submittedChunkSearch, setSubmittedChunkSearch] = useState('');
  const chunkHits = useQuery({
    queryKey: ['document-chunks', id, submittedChunkSearch],
    enabled: submittedChunkSearch.trim().length > 1,
    queryFn: () =>
      api.get<{ items: ChunkHit[] }>(
        `/search/documents?query=${encodeURIComponent(submittedChunkSearch)}&page_size=100`,
      ),
  });
  const download = async () => {
    try {
      const base = process.env.NEXT_PUBLIC_API_BASE_URL
        ? `${process.env.NEXT_PUBLIC_API_BASE_URL.replace(/\/$/, '')}/api/v1`
        : '/api/v1';
      const r = await fetch(`${base}/documents/${id}/file`, {
        headers: authToken() ? { Authorization: `Bearer ${authToken()}` } : {},
      });
      if (!r.ok) throw new Error('Document download unavailable');
      const url = URL.createObjectURL(await r.blob()),
        a = document.createElement('a');
      a.href = url;
      a.download = `${doc.data?.title || 'document'}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Unable to download document');
    }
  };
  if (doc.isLoading)
    return (
      <div className="card surface" role="status">
        Loading document…
      </div>
    );
  if (doc.isError)
    return (
      <div className="offline">
        <strong>Document not available</strong>
        <p>Confirm this document is in your workspace and the API is running.</p>
        <button className="primary" onClick={() => void doc.refetch()}>
          <RefreshCw size={15} /> Retry
        </button>
      </div>
    );
  if (!doc.data) return <div className="offline">Document details were not returned.</div>;
  const pageItems = pages.data?.pages;
  const extractedCharacters = pageItems?.reduce((total, item) => total + (item.text?.length ?? 0), 0);
  const runAiRead = async () => {
    setReading(true);
    try {
      try {
        await documentsApi.aiRead(id);
      } catch (error) {
        setAiOutcome(classifyAiFailure(error, 'extraction_failure'));
        return;
      }
      const hasEvidence = Boolean(text.data?.text?.trim() || pageItems?.some((page) => page.text?.trim()));
      if (!hasEvidence) {
        await extraction.refetch();
        setAiOutcome('no_evidence');
        return;
      }
      const loadedExtraction = await extraction.refetch();
      if (loadedExtraction.isError) {
        setAiOutcome('response_loading_failure');
        return;
      }
      setAiOutcome('ready');
    } finally {
      setReading(false);
    }
  };
  const saveExtraction = async (key: string) => {
    try {
      await api.patch(`/documents/${id}/extraction`, { fields: { [key]: editValue } });
      setEditingField(null);
      await extraction.refetch();
      toast.success('Reviewed extraction saved');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Unable to save review');
    }
  };
  const showExtractionFields =
    aiOutcome === 'ready' || (aiOutcome === 'idle' && Boolean(extraction.data?.fields));
  return (
    <div className="document-detail-page">
      <WorkspaceModuleNav />
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          gap: 12,
          alignItems: 'start',
          flexWrap: 'wrap',
        }}
      >
        <div>
          <small className="muted">Documents / Preview</small>
          <h1
            className="title document-detail-title"
            style={{ marginTop: 8 }}
            aria-label={doc.data.title}
            title={doc.data.title}
          >
            {doc.data.title}
          </h1>
          <p className="subheading">
            {doc.data.document_type || 'Document'} · <DocumentStatus status={doc.data.status} />
            {doc.data.jurisdiction ? ` · ${doc.data.jurisdiction}` : ''}
          </p>
        </div>
        <button className="primary" onClick={() => void download()}>
          <Download size={15} /> Download PDF
        </button>
      </div>
      <div className="document-detail-columns">
        <div className="document-detail-primary">
          {doc.data.filename?.toLowerCase().endsWith('.pdf') && <PdfDocumentViewer documentId={id} />}
          <section className="document-metadata card" aria-label="Document metadata">
            <dl>
              <div className="metadata-hash-row">
                <div
                  className="metadata-definition-row"
                  role="group"
                  aria-label={`SHA-256 ${doc.data.content_hash ? `${doc.data.content_hash.slice(0, 16)}…` : '—'}`}
                >
                  <dt>SHA-256</dt>{' '}
                  <dd>{doc.data.content_hash ? `${doc.data.content_hash.slice(0, 16)}…` : '—'}</dd>
                </div>
                {doc.data.content_hash && (
                  <button
                    aria-label="Copy SHA-256"
                    onClick={async () => {
                      await navigator.clipboard.writeText(doc.data!.content_hash!);
                      setCopiedHash(true);
                      window.setTimeout(() => setCopiedHash(false), 2200);
                    }}
                  >
                    {copiedHash ? 'Copied' : 'Copy'}
                  </button>
                )}
                {copiedHash && <span role="status">SHA-256 copied</span>}
              </div>
              <div
                className="metadata-definition-row"
                role="group"
                aria-label={`Filename ${doc.data.filename || doc.data.title}`}
              >
                <dt>Filename</dt> <dd>{doc.data.filename || doc.data.title}</dd>
              </div>
              <div
                className="metadata-definition-row"
                role="group"
                aria-label={`Pages ${doc.data.page_count ?? pageItems?.length ?? '—'}`}
              >
                <dt>Pages</dt> <dd>{doc.data.page_count ?? pageItems?.length ?? '—'}</dd>
              </div>
              <div
                className="metadata-definition-row"
                role="group"
                aria-label={`Characters ${extractedCharacters == null ? '—' : extractedCharacters.toLocaleString()}`}
              >
                <dt>Characters</dt>{' '}
                <dd>{extractedCharacters == null ? '—' : extractedCharacters.toLocaleString()}</dd>
              </div>
              <div
                className="metadata-definition-row"
                role="group"
                aria-label={`Created ${formatMetadataDate(doc.data.created_at)}`}
              >
                <dt>Created</dt> <dd>{formatMetadataDate(doc.data.created_at)}</dd>
              </div>
              <div
                className="metadata-definition-row"
                role="group"
                aria-label={`Document processed ${formatMetadataDate(doc.data.processed_at)}`}
              >
                <dt>Document processed</dt> <dd>{formatMetadataDate(doc.data.processed_at)}</dd>
              </div>
              <div
                className="metadata-definition-row metadata-review-state"
                role="group"
                aria-label={`AI review ${extraction.isLoading ? 'Checking' : extraction.isError ? 'Unavailable' : extraction.data?.fields ? (extraction.data.review_required ? 'Review required' : 'Reviewed') : 'Not started'}`}
              >
                <dt>AI review</dt>
                <dd>
                  {extraction.isLoading
                    ? 'Checking'
                    : extraction.isError
                      ? 'Unavailable'
                      : extraction.data?.fields
                        ? extraction.data.review_required
                          ? 'Review required'
                          : 'Reviewed'
                        : 'Not started'}
                </dd>
              </div>
              <div
                className="metadata-definition-row"
                role="group"
                aria-label={`Jurisdiction ${doc.data.jurisdiction || '—'}`}
              >
                <dt>Jurisdiction</dt> <dd>{doc.data.jurisdiction || '—'}</dd>
              </div>
              <div
                className="metadata-definition-row"
                role="group"
                aria-label={`Source ${doc.data.source_label || '—'}`}
              >
                <dt>Source</dt> <dd>{doc.data.source_label || '—'}</dd>
              </div>
            </dl>
            {doc.data.is_demo && <span className="badge-demo">Demo document</span>}
          </section>
        </div>
        <aside className="document-detail-aside">
          <section className="card ai-read-panel" aria-label="Document extraction">
            <div className="ai-read-heading">
              <div>
                <h2>
                  <Sparkles size={17} /> Document extraction
                </h2>
                <p>Local text extraction · candidate only · review before relying on it.</p>
                {(aiSettings.data?.runtime_status?.model || aiSettings.data?.model) && (
                  <small className="ai-configured-model">
                    Configured model (not used for these fields):{' '}
                    {aiSettings.data.runtime_status?.model || aiSettings.data.model}
                  </small>
                )}
              </div>
              <button
                className="primary"
                aria-label={
                  reading
                    ? 'Extracting document'
                    : aiOutcome === 'ready'
                      ? 'Run again'
                      : 'Run document extraction'
                }
                disabled={reading}
                onClick={() => void runAiRead()}
              >
                {reading ? 'Extracting…' : aiOutcome === 'ready' ? 'Run again' : 'Run extraction'}
              </button>
            </div>
            {aiOutcome === 'model_unavailable' && (
              <div className="ai-read-degradation" role="status" data-error-category="model_unavailable">
                <strong>AI model unavailable</strong>
                <p>The configured model could not respond. No extraction fields are being shown.</p>
                <button className="primary" onClick={() => void runAiRead()}>
                  Retry extraction
                </button>
              </div>
            )}
            {aiOutcome === 'no_evidence' && (
              <div className="ai-read-degradation" role="status">
                <strong>No evidence found</strong>
                <p>
                  The document search returned no source passages for this document, so there are no candidate
                  fields to review.
                </p>
              </div>
            )}
            {(
              ['auth_failure', 'embedding_failure', 'extraction_failure', 'response_loading_failure'] as const
            ).includes(aiOutcome as Exclude<AiFailure, 'model_unavailable'>) && (
              <div className="ai-read-error-category" role="status" data-error-category={aiOutcome}>
                <strong>{aiOutcome.replaceAll('_', ' ')}</strong>
                <p>{aiFailureMessage(aiOutcome as Exclude<AiFailure, 'model_unavailable'>)}</p>
                <button className="primary" onClick={() => void runAiRead()}>
                  Retry extraction
                </button>
              </div>
            )}
            {extraction.isError && aiOutcome === 'ready' && (
              <div
                className="ai-read-error-category"
                role="status"
                data-error-category="response_loading_failure"
              >
                <strong>Response loading failure</strong>
                <p>{aiFailureMessage('response_loading_failure')}</p>
              </div>
            )}
            {extraction.data?.fields && showExtractionFields && (
              <div className="ai-read-fields">
                {Object.entries(extraction.data.fields).map(([key, field]) => {
                  const value = key === 'summary' ? deduplicateExtractedText(field.value) : field.value;
                  const sourcePage = extractionSourcePage(value);
                  const provenanceKey = field.provenance || 'candidate_extraction';
                  return (
                    <div
                      className="ai-read-field"
                      data-field-key={key}
                      data-provenance-key={provenanceKey}
                      key={key}
                    >
                      <strong>
                        {key === 'summary' ? 'Extracted text (de-duplicated)' : key.replaceAll('_', ' ')}
                      </strong>
                      {editingField === key ? (
                        <textarea
                          aria-label={`Edit ${key}`}
                          value={editValue}
                          onChange={(event) => setEditValue(event.target.value)}
                        />
                      ) : (
                        <div className="ai-read-value">
                          {key === 'summary' && typeof value === 'string' ? (
                            <details className="ai-read-summary-disclosure">
                              <summary>
                                {value.slice(0, 180)}
                                {value.length > 180 ? '…' : ''}
                              </summary>
                              <div>{renderExtractionValue(value)}</div>
                            </details>
                          ) : (
                            renderExtractionValue(value)
                          )}
                          <small className="ai-read-provenance">
                            {provenanceLabel(field.provenance, field.source)}
                            {field.source &&
                              !field.source.toLowerCase().includes('local text extraction') &&
                              ` · ${field.source}`}
                            {field.review_required ? ' · Review required' : ''}
                          </small>
                          {sourcePage ? (
                            <a className="ai-source-page" href={`?page=${sourcePage}`}>
                              Page {sourcePage}
                            </a>
                          ) : (
                            <span className="ai-source-page-unavailable">Source page unavailable</span>
                          )}
                        </div>
                      )}
                      {editingField === key ? (
                        <button aria-label={`Save ${key}`} onClick={() => void saveExtraction(key)}>
                          <Check size={15} />
                        </button>
                      ) : (
                        <button
                          aria-label={`Edit ${key}`}
                          onClick={() => {
                            setEditingField(key);
                            setEditValue(typeof value === 'string' ? value : JSON.stringify(value, null, 2));
                          }}
                        >
                          <Pencil size={14} />
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </aside>
      </div>
      {text.isLoading ? (
        <div className="card surface" style={{ marginTop: 18 }}>
          <span role="status">Loading extracted text…</span>
        </div>
      ) : text.isError ? (
        <div className="offline" style={{ marginTop: 18 }}>
          Text extraction is unavailable for this document.{' '}
          <button className="primary" onClick={() => void text.refetch()}>
            <RefreshCw size={14} /> Retry
          </button>
        </div>
      ) : pageItems?.length ? (
        <section className="document-chunk-panel card" aria-label="Document page chunks">
          <form
            className="document-chunk-search"
            onSubmit={(event) => {
              event.preventDefault();
              setSubmittedChunkSearch(chunkSearch.trim());
            }}
          >
            <label htmlFor="document-chunk-query">Search this document</label>
            <input
              id="document-chunk-query"
              value={chunkSearch}
              onChange={(event) => setChunkSearch(event.target.value)}
              placeholder="Search text, for example SIAC Rules"
            />
            <button className="primary" type="submit">
              Find chunks
            </button>
          </form>
          {chunkHits.isLoading && <p role="status">Searching document text…</p>}
          {chunkHits.data?.items
            .filter((hit) => hit.document_id === id)
            .map((hit, index) => {
              const relevance = hit.retrieval_score ?? hit.retreival_score ?? hit.score;
              return (
                <article className="citation-chunk" key={`${hit.page_number}-${index}`}>
                  <p>{hit.snippet || 'Matching document passage'}</p>
                  <div>
                    <span>Page {hit.page_number}</span>
                    <span>Relevance {typeof relevance === 'number' ? relevance.toFixed(3) : '—'}</span>
                    <a
                      href={`?page=${hit.page_number}&highlight=${encodeURIComponent(submittedChunkSearch)}`}
                    >
                      Open page {hit.page_number}
                    </a>
                  </div>
                </article>
              );
            })}
          {submittedChunkSearch &&
            chunkHits.data &&
            !chunkHits.data.items.some((hit) => hit.document_id === id) && (
              <p className="muted">No matching chunks in this document.</p>
            )}
          <details className="document-page-text-list" open={searchParams.has('page')}>
            <summary>Extracted text by page</summary>
            <div className="document-pages">
              {pageItems.map((p) => (
                <article className="card document-page" id={`page-${p.page_number}`} key={p.page_number}>
                  <div className="page-heading">
                    <a className="document-page-citation" href={`?page=${p.page_number}`}>
                      <FileText size={15} /> Page {p.page_number}
                    </a>
                    {p.ocr_confidence != null && (
                      <small className="muted">OCR confidence {Math.round(p.ocr_confidence * 100)}%</small>
                    )}
                  </div>
                  <p>
                    {p.text ||
                      text.data?.pages?.find((x) => x.page_number === p.page_number)?.text ||
                      'No extracted text on this page.'}
                  </p>
                </article>
              ))}
            </div>
          </details>
        </section>
      ) : (
        <article className="card document-page" style={{ marginTop: 18 }}>
          <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit', lineHeight: 1.7 }}>
            {text.data?.text || 'No extracted text is available for this document.'}
          </pre>
        </article>
      )}
      {pageItems?.some((page) => page.warnings?.length) && (
        <div className="extraction-warnings" role="note">
          <strong>Extraction warnings</strong>
          {pageItems
            .flatMap((page) => page.warnings || [])
            .map((warning, index) => (
              <p key={`${warning}-${index}`}>{warning}</p>
            ))}
        </div>
      )}
    </div>
  );
}
