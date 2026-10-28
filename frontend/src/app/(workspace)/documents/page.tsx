'use client';

import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  FileText,
  Grid2X2,
  List,
  Search,
  UploadCloud,
  RefreshCw,
  Trash2,
  ArrowUpRight,
  Eye,
} from 'lucide-react';
import { documentsApi, type DocumentRecord, type IngestionJob } from '@/features/documents/api';
import { WorkspaceModuleNav } from '@/features/documents/WorkspaceModuleNav';
import { DocumentStatus } from '@/features/documents/DocumentStatus';
import { PdfDocumentViewer } from '@/features/viewer/PdfDocumentViewer';
import { api } from '@/lib/api/client';
import '@/features/documents/documents.css';

type UploadItem = { name: string; progress: number; status: string; error?: string; id?: string };

export default function DocumentsPage() {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const [layout, setLayout] = useState<'grid' | 'list'>('list');
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [previewId, setPreviewId] = useState('');
  const picker = useRef<HTMLInputElement>(null);
  const params = useMemo(() => {
    const search = new URLSearchParams();
    if (query) search.set('q', query);
    if (status) search.set('status', status);
    return search.size ? `?${search}` : '';
  }, [query, status]);
  const documents = useQuery({
    queryKey: ['documents', params],
    queryFn: () => documentsApi.list(params),
    refetchInterval: 4000,
  });
  const cases = useQuery({
    queryKey: ['document-case-labels'],
    queryFn: () => api.get<{ items: Array<{ id: string; title: string }> }>('/cases?page=1&page_size=100'),
  });

  useEffect(() => {
    if (documents.data?.total === 0 && status) setStatus('');
  }, [documents.data?.total, status]);

  useEffect(() => {
    const active =
      documents.data?.items.filter((document) => ['queued', 'processing'].includes(document.status)) ?? [];
    if (!active.length) return;
    const refresh = async () => {
      await Promise.all(active.map((document) => documentsApi.job(document.id).catch(() => null)));
      await queryClient.invalidateQueries({ queryKey: ['documents'] });
    };
    void refresh();
  }, [documents.data, queryClient]);

  const uploadFiles = async (files: FileList | File[]) => {
    const batch = Array.from(files);
    setUploads(batch.map((file) => ({ name: file.name, progress: 0, status: 'Uploading' })));
    await Promise.all(
      batch.map(async (file, index) => {
        try {
          const result = await documentsApi.upload(file, (progress) =>
            setUploads((items) => items.map((item, at) => (at === index ? { ...item, progress } : item))),
          );
          setUploads((items) =>
            items.map((item, at) =>
              at === index ? { ...item, progress: 100, status: 'Processing', id: result.document_id } : item,
            ),
          );
          await queryClient.invalidateQueries({ queryKey: ['documents'] });
        } catch (error) {
          const failure = error as Error & {
            status?: number;
            body?: { detail?: { existing_document?: { id: string } } };
          };
          const duplicate = failure.status === 409;
          setUploads((items) =>
            items.map((item, at) =>
              at === index
                ? {
                    ...item,
                    status: duplicate ? 'Already in library' : 'Upload failed',
                    error: failure.message,
                    id: failure.body?.detail?.existing_document?.id,
                  }
                : item,
            ),
          );
        }
      }),
    );
  };

  const remove = async (document: DocumentRecord) => {
    if (!window.confirm(`Delete “${document.title}” from your library? This cannot be undone.`)) return;
    await documentsApi.remove(document.id);
    setSelected((current) => current.filter((id) => id !== document.id));
    await queryClient.invalidateQueries({ queryKey: ['documents'] });
  };

  const bulkDelete = async () => {
    if (
      !selected.length ||
      !window.confirm(`Delete ${selected.length} selected documents? This cannot be undone.`)
    )
      return;
    await Promise.all(selected.map((id) => documentsApi.remove(id)));
    setSelected([]);
    await queryClient.invalidateQueries({ queryKey: ['documents'] });
  };

  const documentsList = documents.data?.items ?? [];
  const selectedPreview = documentsList.find((document) => document.id === previewId) ?? documentsList[0];
  const maximumUploadMb = 25;
  const caseTitles = new Map((cases.data?.items ?? []).map((item) => [item.id, item.title]));
  return (
    <main className="documents-page">
      <WorkspaceModuleNav />
      <header className="documents-heading">
        <div>
          <p className="documents-eyebrow">Workspace</p>
          <h1>Documents</h1>
          <p>Upload, review, and find arbitration records.</p>
        </div>
        <button className="documents-button documents-button-primary" onClick={() => picker.current?.click()}>
          <UploadCloud size={17} /> Upload documents
        </button>
        <input
          ref={picker}
          hidden
          type="file"
          multiple
          accept=".pdf,.docx,.txt,.md"
          onChange={(event) => event.target.files && void uploadFiles(event.target.files)}
        />
      </header>

      <section
        className="documents-upload"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          void uploadFiles(event.dataTransfer.files);
        }}
      >
        <UploadCloud size={32} strokeWidth={1.7} />
        <strong>Drag &amp; drop arbitration documents here</strong>
        <span>
          or <button onClick={() => picker.current?.click()}>click to upload</button>
        </span>
        <small>
          PDF, DOCX, TXT, MD · maximum {maximumUploadMb} MB ·{' '}
          <details className="upload-mime-details">
            <summary>Accepted MIME types</summary>
            <span>
              application/pdf, application/octet-stream,
              application/vnd.openxmlformats-officedocument.wordprocessingml.document, text/plain,
              text/markdown
            </span>
          </details>
        </small>
      </section>

      {uploads.length > 0 && (
        <section className="documents-queue card">
          <div className="documents-section-title">
            <h2>Upload queue</h2>
            <button aria-label="Clear upload queue" onClick={() => setUploads([])}>
              Clear
            </button>
          </div>
          {uploads.map((item) => (
            <div className="queue-item" key={item.name}>
              <div>
                <strong>{item.name}</strong>
                <span>{item.error || item.status}</span>
                {item.id && item.status === 'Already in library' && (
                  <Link href={`/documents/${item.id}`}>
                    Open existing document <ArrowUpRight size={13} />
                  </Link>
                )}
              </div>
              <progress max="100" value={item.progress} aria-label={`${item.name} upload progress`} />
            </div>
          ))}
        </section>
      )}

      <section className="documents-library card">
        <div className="documents-library-toolbar">
          <div>
            <h2>Library</h2>
            <span>
              {documents.isError
                ? '—'
                : query && documents.data?.total === 0
                  ? '0 matching documents'
                  : `${documents.data?.total ?? '—'} documents`}
            </span>
          </div>
          <div className="documents-toolbar-controls">
            <label className="documents-search">
              <Search size={16} />
              <input
                aria-label="Search documents"
                placeholder="Search documents"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            <select
              aria-label="Filter by status"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="">All statuses</option>
              <option value="ready">Ready</option>
              <option value="processing">Processing</option>
              <option value="queued">Queued</option>
              <option value="failed">Failed</option>
            </select>
            <button
              className={layout === 'list' ? 'view-active' : ''}
              aria-label="List view"
              onClick={() => setLayout('list')}
            >
              <List size={17} />
            </button>
            <button
              className={layout === 'grid' ? 'view-active' : ''}
              aria-label="Grid view"
              onClick={() => setLayout('grid')}
            >
              <Grid2X2 size={17} />
            </button>
          </div>
        </div>
        {selected.length > 0 && (
          <div className="bulk-bar">
            <span>{selected.length} selected</span>
            <button onClick={() => void bulkDelete()}>
              <Trash2 size={15} /> Delete selected
            </button>
          </div>
        )}
        {documents.isLoading ? (
          <div className="documents-loading" role="status">
            Loading your documents…
          </div>
        ) : documents.isError ? (
          <div className="documents-empty">
            <FileText size={32} />
            <h3>Documents are unavailable</h3>
            <p>Check your connection to the workspace, then try again.</p>
            <button className="documents-button" onClick={() => void documents.refetch()}>
              <RefreshCw size={15} /> Retry
            </button>
          </div>
        ) : documentsList.length === 0 ? (
          <div className="documents-empty">
            <FileText size={32} />
            <h3>{query ? '0 matching documents' : 'Your library is ready'}</h3>
            <p>
              {query
                ? 'Try another search term or clear your filters.'
                : 'Upload an arbitration document to begin reading and organizing your materials.'}
            </p>
            {!query && (
              <button
                className="documents-button documents-button-primary"
                onClick={() => picker.current?.click()}
              >
                <UploadCloud size={16} /> Upload your first document
              </button>
            )}
          </div>
        ) : (
          <div className={`documents-workspace ${layout}`}>
            <div className="documents-table-wrap">
              <div className="documents-mobile-cards">
                {documentsList.map((document) => (
                  <DocumentCard
                    key={document.id}
                    document={document}
                    selected={selected.includes(document.id)}
                    onSelect={() =>
                      setSelected((current) =>
                        current.includes(document.id)
                          ? current.filter((id) => id !== document.id)
                          : [...current, document.id],
                      )
                    }
                    onDelete={() => void remove(document)}
                    onRetry={async () => {
                      await documentsApi.retry(document.id);
                      await queryClient.invalidateQueries({ queryKey: ['documents'] });
                    }}
                  />
                ))}
              </div>
              {layout === 'list' ? (
                <table className="documents-table">
                  <thead>
                    <tr>
                      <th scope="col">Document title</th>
                      <th scope="col">File</th>
                      <th scope="col">Case</th>
                      <th scope="col">Pages</th>
                      <th scope="col">Uploaded</th>
                      <th scope="col">Status</th>
                      <th scope="col">
                        <span className="visually-hidden">Select</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {documentsList.map((document) => (
                      <DocumentRow
                        key={document.id}
                        document={document}
                        caseTitle={caseTitles.get(document.case_id ?? '')}
                        selected={selected.includes(document.id)}
                        previewed={selectedPreview?.id === document.id}
                        onSelect={() =>
                          setSelected((current) =>
                            current.includes(document.id)
                              ? current.filter((id) => id !== document.id)
                              : [...current, document.id],
                          )
                        }
                        onPreview={() => setPreviewId(document.id)}
                        onDelete={() => void remove(document)}
                        onRetry={async () => {
                          await documentsApi.retry(document.id);
                          await queryClient.invalidateQueries({ queryKey: ['documents'] });
                        }}
                      />
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="documents-list grid">
                  {documentsList.map((document) => (
                    <DocumentCard
                      key={document.id}
                      document={document}
                      selected={selected.includes(document.id)}
                      onSelect={() =>
                        setSelected((current) =>
                          current.includes(document.id)
                            ? current.filter((id) => id !== document.id)
                            : [...current, document.id],
                        )
                      }
                      onDelete={() => void remove(document)}
                      onRetry={async () => {
                        await documentsApi.retry(document.id);
                        await queryClient.invalidateQueries({ queryKey: ['documents'] });
                      }}
                    />
                  ))}
                </div>
              )}
            </div>
            {layout === 'list' && selectedPreview && (
              <aside className="document-preview-pane">
                <div className="document-preview-heading">
                  <div>
                    <span>Preview</span>
                    <strong>{selectedPreview.title}</strong>
                  </div>
                  <Link
                    href={`/documents/${selectedPreview.id}`}
                    aria-label={`Open ${selectedPreview.title}`}
                  >
                    <Eye size={16} />
                  </Link>
                </div>
                {selectedPreview.filename?.toLowerCase().endsWith('.pdf') ? (
                  <PdfDocumentViewer documentId={selectedPreview.id} firstPageOnly />
                ) : (
                  <div className="preview-unavailable">
                    Preview is available for PDF files.{' '}
                    <Link href={`/documents/${selectedPreview.id}`}>Open extracted text</Link>
                  </div>
                )}
              </aside>
            )}
          </div>
        )}
      </section>
    </main>
  );
}

function DocumentRow({
  document,
  caseTitle,
  selected,
  previewed,
  onSelect,
  onPreview,
  onDelete,
  onRetry,
}: {
  document: DocumentRecord;
  caseTitle?: string;
  selected: boolean;
  previewed: boolean;
  onSelect: () => void;
  onPreview: () => void;
  onDelete: () => void;
  onRetry: () => void;
}) {
  const job = useQuery<IngestionJob>({
    queryKey: ['documents', document.id, 'job'],
    queryFn: () => documentsApi.job(document.id),
    enabled: ['queued', 'processing', 'failed'].includes(document.status),
    refetchInterval: ['queued', 'processing'].includes(document.status) ? 1800 : false,
  });
  const uploaded = document.created_at ? new Date(document.created_at).toLocaleDateString() : '—';
  const pageCount = document.page_count ?? document.pages;
  return (
    <tr
      className={previewed ? 'document-row previewed' : 'document-row'}
      data-document-id={document.id}
      onClick={onPreview}
    >
      <td>
        <div className="document-row-title">
          <input
            type="checkbox"
            aria-label={`Select ${document.title}`}
            checked={selected}
            onClick={(event) => event.stopPropagation()}
            onChange={onSelect}
          />
          <FileText size={16} />
          <Link href={`/documents/${document.id}`} onClick={(event) => event.stopPropagation()}>
            {document.title}
          </Link>
        </div>
      </td>
      <td className="document-file-cell" title={document.filename}>
        {document.filename || '—'}
      </td>
      <td>{document.case_id ? <Link href={`/cases/${document.case_id}`}>{caseTitle || '—'}</Link> : '—'}</td>
      <td>{pageCount == null ? '—' : pageCount}</td>
      <td>{uploaded}</td>
      <td>
        <DocumentStatus status={job.data?.status || document.status} />
        {job.data?.status === 'failed' && (
          <button
            className="row-retry"
            onClick={(event) => {
              event.stopPropagation();
              onRetry();
            }}
          >
            Retry
          </button>
        )}
      </td>
      <td>
        <button
          className="row-delete"
          aria-label={`Delete ${document.title}`}
          onClick={(event) => {
            event.stopPropagation();
            onDelete();
          }}
        >
          <Trash2 size={14} />
        </button>
      </td>
    </tr>
  );
}

function DocumentCard({
  document,
  selected,
  onSelect,
  onDelete,
  onRetry,
}: {
  document: DocumentRecord;
  selected: boolean;
  onSelect: () => void;
  onDelete: () => void;
  onRetry: () => void;
}) {
  const job = useQuery<IngestionJob>({
    queryKey: ['documents', document.id, 'job'],
    queryFn: () => documentsApi.job(document.id),
    enabled: ['queued', 'processing', 'failed'].includes(document.status),
    refetchInterval: ['queued', 'processing'].includes(document.status) ? 1800 : false,
  });
  return (
    <article className="document-card" data-document-id={document.id}>
      <div className="document-card-top">
        <input
          type="checkbox"
          aria-label={`Select ${document.title}`}
          checked={selected}
          onChange={onSelect}
        />
        <DocumentStatus status={job.data?.status || document.status} />
      </div>
      <Link className="document-card-link" href={`/documents/${document.id}`}>
        <div className="document-icon">
          <FileText size={21} />
        </div>
        <h3>{document.title}</h3>
        <p>{document.filename}</p>
      </Link>
      <div className="document-card-meta">
        <span>{document.document_type || 'Document'}</span>
        <span>{document.pages ? `${document.pages} pages` : '—'}</span>
      </div>
      {job.data && (
        <div className="document-job">
          <progress max="100" value={job.data.progress} />
          <span>
            {job.data.status === 'failed'
              ? job.data.error || 'Processing failed'
              : `${job.data.progress}% · ${job.data.status}`}
          </span>
          {job.data.status === 'failed' && <button onClick={onRetry}>Retry</button>}
        </div>
      )}
      <div className="document-card-actions">
        <Link href={`/documents/${document.id}`}>
          Open document <ArrowUpRight size={13} />
        </Link>
        <button aria-label={`Delete ${document.title}`} onClick={onDelete}>
          <Trash2 size={15} />
        </button>
      </div>
    </article>
  );
}
