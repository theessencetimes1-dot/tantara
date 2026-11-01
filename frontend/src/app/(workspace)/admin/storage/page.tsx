'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  Database,
  FolderUp,
  HardDriveUpload,
  LoaderCircle,
  RefreshCw,
  Trash2,
  Upload,
} from 'lucide-react';
import { documentsApi } from '@/features/documents/api';
import { api } from '@/lib/api/client';
import './storage.css';

type UploadState = {
  key: string;
  name: string;
  status: 'queued' | 'uploading' | 'indexing' | 'ready' | 'failed' | 'deleted';
  progress: number;
  message?: string;
  documentId?: string;
  indexConfidence?: number | null;
};

type KnowledgeFile = {
  filename: string;
  status: string;
  progress: number;
  chunks: number;
  index_confidence?: number | null;
  document_id?: string | null;
  error?: string | null;
  warnings: (string | { page?: number; warning?: string })[];
};

type KnowledgeFolder = {
  id: string;
  label: string;
  status: string;
  file_count: number;
  indexed_count: number;
  failed_count: number;
  pending_count: number;
  files: KnowledgeFile[];
};

const supported = /\.(pdf|docx|txt|md)$/i;
const pause = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));
const formatWarning = (warning: KnowledgeFile['warnings'][number]) => {
  if (typeof warning === 'string') return warning;
  const text = warning.warning || JSON.stringify(warning);
  return warning.page ? `Page ${warning.page}: ${text}` : text;
};

export default function AdminStoragePage() {
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const [storageReady, setStorageReady] = useState<boolean | null>(null);
  const [bucket, setBucket] = useState('');
  const [items, setItems] = useState<UploadState[]>([]);
  const [knowledgeFolders, setKnowledgeFolders] = useState<KnowledgeFolder[]>([]);
  const [knowledgeError, setKnowledgeError] = useState('');
  const [knowledgeLoading, setKnowledgeLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [deletingFiles, setDeletingFiles] = useState<string[]>([]);
  const filePicker = useRef<HTMLInputElement>(null);
  const folderPicker = useRef<HTMLInputElement>(null);

  const refreshKnowledgeBase = useCallback(async () => {
    setKnowledgeLoading(true);
    try {
      const response = await api.get<{ folders: KnowledgeFolder[] }>('/admin/storage/knowledge-base');
      setKnowledgeFolders(response.folders ?? []);
      setKnowledgeError('');
    } catch (error) {
      setKnowledgeError(error instanceof Error ? error.message : 'Knowledge base status is unavailable.');
    } finally {
      setKnowledgeLoading(false);
    }
  }, []);

  useEffect(() => {
    void api
      .get<{ role?: string }>('/auth/me')
      .then(async (user) => {
        const allowed = user.role === 'admin';
        setIsAdmin(allowed);
        if (allowed) {
          try {
            const status = await api.get<{ ready: boolean; bucket?: string }>('/admin/storage/status');
            setStorageReady(status.ready);
            setBucket(status.bucket || '');
          } catch {
            setStorageReady(false);
          }
        }
      })
      .catch(() => setIsAdmin(false));
    folderPicker.current?.setAttribute('webkitdirectory', '');
    folderPicker.current?.setAttribute('directory', '');
  }, []);

  useEffect(() => {
    if (!isAdmin || !storageReady) return;
    void refreshKnowledgeBase();
    const timer = window.setInterval(() => void refreshKnowledgeBase(), 3000);
    return () => window.clearInterval(timer);
  }, [isAdmin, refreshKnowledgeBase, storageReady]);

  const update = (key: string, values: Partial<UploadState>) => {
    setItems((current) => current.map((item) => (item.key === key ? { ...item, ...values } : item)));
  };

  const deleteUpload = async (item: UploadState) => {
    if (!item.documentId || item.status === 'deleted') return;
    if (!window.confirm(`Delete ${item.name} from storage and remove its search index?`)) return;
    try {
      await documentsApi.remove(item.documentId);
      update(item.key, { status: 'deleted', message: 'Deleted from storage and search index.' });
    } catch (error) {
      update(item.key, {
        message: `Delete failed: ${error instanceof Error ? error.message : 'Unable to delete this file.'}`,
      });
    }
  };

  const deleteKnowledgeFile = async (folder: KnowledgeFolder, file: KnowledgeFile) => {
    const key = `${folder.id}/${file.filename}`;
    if (!window.confirm(`Delete ${file.filename} from ${folder.label} and remove its indexed copy?`)) return;
    setDeletingFiles((current) => [...current, key]);
    try {
      await documentsApi.deleteKnowledgeFile(folder.id, file.filename);
      await refreshKnowledgeBase();
    } catch (error) {
      setKnowledgeError(error instanceof Error ? error.message : `Could not delete ${file.filename}.`);
    } finally {
      setDeletingFiles((current) => current.filter((item) => item !== key));
    }
  };

  const uploadFiles = async (chosen: File[]) => {
    if (running || !chosen.length) return;
    const batch = chosen.map((file, index) => ({
      file,
      key: `${Date.now()}-${index}-${file.name}`,
      name: (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name,
    }));
    setItems((current) => [
      ...batch.map(({ key, name, file }) => ({
        key,
        name,
        status: (supported.test(file.name) ? 'queued' : 'failed') as UploadState['status'],
        progress: 0,
        message: supported.test(file.name) ? undefined : 'Unsupported file type. Use PDF, DOCX, TXT, or MD.',
      })),
      ...current,
    ]);
    setRunning(true);
    for (const { file, key } of batch) {
      if (!supported.test(file.name)) continue;
      let documentId: string;
      try {
        update(key, { status: 'uploading', message: 'Checking text and creating embeddings…' });
        const response = await documentsApi.upload(
          file,
          (progress) => update(key, { progress }),
          undefined,
          '/admin/storage/upload',
        );
        documentId = response.document_id;
        update(key, { documentId });
      } catch (error) {
        update(key, {
          status: 'failed',
          message: `Upload failed: ${error instanceof Error ? error.message : 'Check your connection and retry.'}`,
        });
        continue;
      }
      update(key, { status: 'indexing', progress: 100, message: 'Embeddings ready. Writing search index…' });
      try {
        let terminal = false;
        for (let attempt = 0; attempt < 300; attempt += 1) {
          const job = await documentsApi.job(documentId);
          if (job.status === 'ready') {
            let indexConfidence: number | null = null;
            try {
              indexConfidence = (await documentsApi.get(documentId)).index_confidence ?? null;
            } catch {
              // The job is ready even if the optional confidence detail request fails.
            }
            update(key, {
              status: 'ready',
              indexConfidence,
              message: job.warnings?.length
                ? `Indexed with warnings: ${job.warnings.join('; ')}`
                : 'Uploaded and indexed.',
            });
            terminal = true;
            break;
          }
          if (job.status === 'failed' || job.status === 'error') {
            update(key, {
              status: 'failed',
              message: `Indexing failed: ${job.error || 'The document could not be indexed.'}`,
            });
            terminal = true;
            break;
          }
          update(key, { message: `Indexing… ${job.progress ?? 0}%` });
          await pause(1000);
        }
        if (!terminal)
          update(key, {
            status: 'failed',
            message: 'Indexing timed out. Check the document status and retry.',
          });
      } catch (error) {
        update(key, {
          status: 'failed',
          message: `Index status unavailable: ${error instanceof Error ? error.message : 'The stored file could not be checked.'}`,
        });
      }
    }
    setRunning(false);
    if (filePicker.current) filePicker.current.value = '';
    if (folderPicker.current) folderPicker.current.value = '';
  };

  if (isAdmin === null)
    return (
      <main className="storage-admin">
        <p role="status">Checking administrator access…</p>
      </main>
    );
  if (!isAdmin)
    return (
      <main className="storage-admin">
        <section className="storage-admin-denied">
          <AlertCircle />
          <h1>Administrator access required</h1>
          <p>This storage uploader is available to administrators only.</p>
        </section>
      </main>
    );

  const completed = items.filter((item) => item.status === 'ready').length;
  const failed = items.filter((item) => item.status === 'failed').length;
  const active = items.filter((item) => item.status === 'uploading' || item.status === 'indexing').length;

  return (
    <main className="storage-admin">
      <header className="storage-admin-heading">
        <span className="storage-admin-icon">
          <Database size={21} />
        </span>
        <div>
          <p>ADMINISTRATION / STORAGE</p>
          <h1>Supabase Storage</h1>
          <span>Upload documents and follow storage and indexing progress live.</span>
        </div>
      </header>
      <section className="storage-admin-card">
        <div className="storage-admin-card-heading">
          <div>
            <h2>Add files or a folder</h2>
            <p>
              Documents are sent through the workspace ingestion service and saved to its configured Supabase
              Storage bucket.
            </p>
          </div>
          <HardDriveUpload size={22} />
        </div>
        {storageReady === false && (
          <p className="storage-config-error" role="alert">
            Supabase Storage is not configured for this workspace. Set OBJECT_STORAGE=supabase and configure
            its Supabase URL, service role key, and bucket.
          </p>
        )}
        {storageReady && (
          <p className="storage-bucket-note">
            Configured bucket: <strong>{bucket}</strong>
          </p>
        )}
        {storageReady === null ? (
          <p role="status">Checking Supabase Storage…</p>
        ) : (
          <div className="storage-admin-actions">
            <input
              ref={filePicker}
              type="file"
              multiple
              accept=".pdf,.docx,.txt,.md"
              aria-label="Choose files"
              disabled={running}
              onChange={(event) => void uploadFiles(Array.from(event.target.files ?? []))}
            />
            <input
              ref={folderPicker}
              type="file"
              multiple
              aria-label="Choose a folder"
              disabled={running}
              onChange={(event) => void uploadFiles(Array.from(event.target.files ?? []))}
            />
            <button
              type="button"
              disabled={running || !storageReady}
              onClick={() => filePicker.current?.click()}
            >
              <Upload size={16} /> Choose files
            </button>
            <button
              type="button"
              className="storage-folder-button"
              disabled={running || !storageReady}
              onClick={() => folderPicker.current?.click()}
            >
              <FolderUp size={16} /> Choose folder
            </button>
            {running && (
              <span className="storage-running">
                <LoaderCircle size={15} /> Processing queue
              </span>
            )}
          </div>
        )}
        <p className="storage-admin-hint">
          Supported types: PDF, DOCX, TXT, MD. Each document is uploaded and indexed in sequence.
        </p>
      </section>
      <section className="storage-admin-card storage-kb-card" aria-live="polite">
        <div className="storage-results-heading">
          <div className="storage-kb-title">
            <BookOpen size={19} />
            <div>
              <h2>Admin controlled knowledge base</h2>
              <p>Live indexing status for the primary acts, amendments, and arbitration reference folders.</p>
              <p className="storage-confidence-note">
                Confidence estimates text coverage page by page (0–100 words per page earns progressively more
                confidence), adjusted for OCR and extraction warnings. It is a processing quality estimate.
              </p>
            </div>
          </div>
          <span className="storage-kb-refresh">
            <RefreshCw className={knowledgeLoading ? 'storage-spinner' : ''} size={14} />
            {knowledgeLoading ? 'Refreshing' : 'Live · updates every 3 seconds'}
          </span>
        </div>
        {knowledgeError ? (
          <p className="storage-config-error" role="alert">
            {knowledgeError}
          </p>
        ) : knowledgeFolders.length ? (
          <div className="storage-kb-folders">
            {knowledgeFolders.map((folder) => (
              <details className="storage-kb-folder" key={folder.id} open>
                <summary>
                  <strong>{folder.label}</strong>
                  <span className={`storage-kb-status ${folder.status}`}>
                    {folder.indexed_count}/{folder.file_count} indexed
                    {folder.pending_count ? ` · ${folder.pending_count} pending` : ''}
                    {folder.failed_count ? ` · ${folder.failed_count} failed` : ''}
                  </span>
                </summary>
                <ul>
                  {folder.files.map((file) => (
                    <li key={`${folder.id}/${file.filename}`} className={`storage-kb-file ${file.status}`}>
                      <span className="storage-kb-file-icon">
                        {file.status === 'ready' ? (
                          <CheckCircle2 size={16} />
                        ) : file.status === 'failed' ? (
                          <AlertCircle size={16} />
                        ) : (
                          <LoaderCircle className="storage-spinner" size={16} />
                        )}
                      </span>
                      <span className="storage-kb-file-name" title={file.filename}>
                        {file.filename}
                      </span>
                      <span className="storage-kb-file-status">
                        {file.status === 'ready'
                          ? `${file.chunks} chunks · confidence ${file.index_confidence == null ? '—' : `${file.index_confidence}%`}`
                          : file.status === 'not_indexed'
                            ? 'Not indexed'
                            : file.error || `${file.status} · ${file.progress}%`}
                      </span>
                      {file.warnings?.length ? (
                        <small>{file.warnings.map(formatWarning).join('; ')}</small>
                      ) : null}
                      <button
                        type="button"
                        className="storage-delete-button"
                        aria-label={`Delete ${file.filename}`}
                        title="Delete file and its indexed copy"
                        disabled={deletingFiles.includes(`${folder.id}/${file.filename}`)}
                        onClick={() => void deleteKnowledgeFile(folder, file)}
                      >
                        {deletingFiles.includes(`${folder.id}/${file.filename}`) ? (
                          <LoaderCircle className="storage-spinner" size={14} />
                        ) : (
                          <Trash2 size={14} />
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              </details>
            ))}
          </div>
        ) : (
          <p role="status">
            {knowledgeLoading ? 'Loading folder status…' : 'No knowledge base folders were found.'}
          </p>
        )}
      </section>
      <section className="storage-admin-card storage-results" aria-live="polite">
        <div className="storage-results-heading">
          <div>
            <h2>Upload activity</h2>
            <p>
              {completed} ready · {active} in progress · {failed} failed
            </p>
          </div>
        </div>
        {items.length ? (
          <ul>
            {items.map((item) => (
              <li key={item.key} className={`storage-item ${item.status}`}>
                <span className="storage-item-status">
                  {item.status === 'ready' ? (
                    <CheckCircle2 size={18} />
                  ) : item.status === 'failed' ? (
                    <AlertCircle size={18} />
                  ) : item.status === 'queued' ? (
                    <Upload size={17} />
                  ) : item.status === 'deleted' ? (
                    <Trash2 size={16} />
                  ) : (
                    <LoaderCircle className="storage-spinner" size={18} />
                  )}
                </span>
                <div className="storage-item-main">
                  <strong title={item.name}>{item.name}</strong>
                  <span>{item.message ?? 'Waiting to upload'}</span>
                  {item.status === 'ready' && (
                    <span className="storage-upload-confidence">
                      Index confidence {item.indexConfidence == null ? '—' : `${item.indexConfidence}%`}
                    </span>
                  )}
                  {item.status === 'uploading' && (
                    <progress max={100} value={item.progress} aria-label={`Uploading ${item.name}`} />
                  )}
                </div>
                <small>{item.status === 'uploading' ? `${item.progress}%` : item.status}</small>
                {item.documentId && item.status !== 'deleted' && (
                  <button
                    type="button"
                    className="storage-upload-delete"
                    aria-label={`Delete ${item.name}`}
                    title="Delete file and its indexed copy"
                    disabled={item.status === 'uploading' || item.status === 'indexing'}
                    onClick={() => void deleteUpload(item)}
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <div className="storage-empty">
            <FolderUp size={25} />
            <p>No files in this session yet.</p>
          </div>
        )}
      </section>
    </main>
  );
}
