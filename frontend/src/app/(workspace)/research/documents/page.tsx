'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, FileText, Upload } from 'lucide-react';
import { researchApi } from '@/features/research/api';
import { documentPageUrl } from '@/features/research/document-url';
import '../research.css';

type Doc = { id: string; title?: string; filename?: string; status?: string; page_count?: number };
export default function ResearchDocuments() {
  const [documents, setDocuments] = useState<Doc[]>([]);
  const [unavailable, setUnavailable] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState('');
  const uploadInput = useRef<HTMLInputElement>(null);
  const refreshDocuments = useCallback(async () => {
    try {
      const response = await researchApi.documents();
      setDocuments(response.items ?? []);
      setUnavailable(false);
    } catch {
      setUnavailable(true);
    }
  }, []);
  useEffect(() => {
    void refreshDocuments();
  }, [refreshDocuments]);
  const upload = async (file?: File) => {
    if (!file) return;
    setUploading(true);
    setUploadMessage('Uploading and indexing the document…');
    try {
      const title = file.name.replace(/\.[^.]+$/, '').trim() || file.name;
      const response = await researchApi.upload(file, title);
      const id = response.document_id ?? response.id;
      if (id) {
        for (let attempt = 0; attempt < 60; attempt += 1) {
          const job = await researchApi.ingestJob(id);
          if (job.status === 'ready') break;
          if (job.status === 'failed' || job.status === 'error') {
            throw new Error('The document could not be indexed. Try another file.');
          }
          await new Promise((resolve) => window.setTimeout(resolve, 1000));
        }
      }
      await refreshDocuments();
      setUploadMessage('Document received. Its latest indexing status is shown in the library.');
    } catch (error) {
      setUploadMessage(error instanceof Error ? error.message : 'The document could not be uploaded.');
    } finally {
      setUploading(false);
      if (uploadInput.current) uploadInput.current.value = '';
    }
  };
  return (
    <div className="research-docs">
      <Link href="/research" className="research-back">
        <ArrowLeft size={15} /> Back to Research Desk
      </Link>
      <h1>Research library</h1>
      <p>Documents available for grounded research.</p>
      <div className="research-upload">
        <input
          ref={uploadInput}
          type="file"
          accept=".pdf,.docx,.txt,.md"
          aria-label="Choose a document to upload"
          disabled={uploading}
          onChange={(event) => void upload(event.target.files?.[0])}
        />
        <button type="button" disabled={uploading} onClick={() => uploadInput.current?.click()}>
          <Upload size={15} /> {uploading ? 'Uploading…' : 'Upload a document'}
        </button>
        {uploadMessage && <p role="status">{uploadMessage}</p>}
      </div>
      <section className="research-docs-card">
        <h2>
          <FileText size={17} /> Workspace documents
        </h2>
        {unavailable ? (
          <p role="status">The document library is currently unavailable.</p>
        ) : documents.length ? (
          <div className="research-docs-list">
            {documents.map((doc) => (
              <Link key={doc.id} href={documentPageUrl(doc.id, 1)}>
                <strong>{doc.title ?? doc.filename ?? 'Untitled document'}</strong>
                <span>
                  {' '}
                  · {doc.status ?? '—'} · {doc.page_count ?? '—'} pages
                </span>
              </Link>
            ))}
          </div>
        ) : (
          <p>
            No documents are available yet. Add a document from the Documents workspace to use it as research
            evidence.
          </p>
        )}
      </section>
    </div>
  );
}
