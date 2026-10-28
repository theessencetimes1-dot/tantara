'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowUpRight, FileText, Search, Sparkles } from 'lucide-react';
import { api } from '@/lib/api/client';
import '@/features/documents/documents.css';
import '@/features/search/search.css';
import { documentHref } from '@/features/documents/links';
import { collectionsApi } from '@/features/documents/api';

type SearchHit = {
  document_id: string;
  document_title?: string;
  title?: string;
  page_number: number;
  text?: string;
  snippet?: string;
  retrieval_score?: number;
  document_type?: string;
};
type SearchResponse = { status?: string; items: SearchHit[]; total: number };

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [submitted, setSubmitted] = useState('');
  const [collectionId, setCollectionId] = useState('');
  const collections = useQuery({ queryKey: ['collections'], queryFn: collectionsApi.list });
  const hits = useQuery({
    queryKey: ['document-search', submitted, collectionId],
    enabled: Boolean(submitted),
    queryFn: () => {
      const params = new URLSearchParams({ query: submitted });
      if (collectionId) params.set('collection_id', collectionId);
      return api.get<SearchResponse>(`/search/documents?${params}`);
    },
  });
  return (
    <div className="documents-page search-page">
      <header className="documents-heading">
        <div>
          <p className="documents-eyebrow">Research desk</p>
          <h1>Document Search</h1>
          <p>Find passages across your arbitration materials.</p>
        </div>
      </header>
      <form
        className="search-query card"
        onSubmit={(event) => {
          event.preventDefault();
          setSubmitted(query.trim());
        }}
      >
        <Search size={19} />
        <input
          aria-label="Search documents"
          placeholder="Search agreements, provisions, parties, or dates…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <label className="search-collection-filter">
          <span>Collection</span>
          <select
            aria-label="Search collection"
            value={collectionId}
            onChange={(event) => setCollectionId(event.target.value)}
          >
            <option value="">All collections</option>
            {collections.data?.items.map((collection) => (
              <option key={collection.id} value={collection.id}>
                {collection.name}
              </option>
            ))}
          </select>
        </label>
        <button className="documents-button documents-button-primary" type="submit">
          Search
        </button>
      </form>
      {submitted && (
        <section className="search-results">
          <div className="search-result-heading">
            <h2>Results for “{submitted}”</h2>
            {hits.data && <span>{hits.data.total} passages</span>}
          </div>
          {hits.isLoading ? (
            <div className="documents-loading" role="status">
              Searching your documents…
            </div>
          ) : hits.isError ? (
            <div className="documents-empty">
              <h3>Search is unavailable</h3>
              <p>Try again when the document service is online.</p>
              <button className="documents-button" onClick={() => void hits.refetch()}>
                Retry search
              </button>
            </div>
          ) : hits.data?.items.length ? (
            <>
              {hits.data.status === 'lexical_only' && (
                <p className="search-mode">
                  <FileText size={15} /> Lexical results are available; hybrid semantic retrieval is currently
                  unavailable.
                </p>
              )}
              <p className="search-score-note">
                Relevance is a fusion rank score used to order passages, not a confidence value. OCR
                confidence is shown separately for scanned-page text.
              </p>
              {hits.data.items.map((hit, index) => {
                const relevance = hit.retrieval_score;
                return (
                  <article className="search-hit card" key={`${hit.document_id}-${hit.page_number}-${index}`}>
                    <div className="search-hit-icon">
                      <FileText size={18} />
                    </div>
                    <div className="search-hit-main">
                      <div className="search-hit-title">
                        <Link href={documentHref(hit.document_id, hit.page_number)}>
                          {hit.document_title || hit.title || 'Untitled document'}
                        </Link>
                        <span>Page {hit.page_number}</span>
                      </div>
                      <p>{hit.snippet || hit.text || 'No excerpt available.'}</p>
                      <div className="search-hit-foot">
                        <span>{hit.document_type || 'Document'}</span>
                        {relevance != null && <span>Relevance {Number(relevance).toFixed(3)}</span>}
                        <Link href={documentHref(hit.document_id, hit.page_number)}>
                          Open at page {hit.page_number} <ArrowUpRight size={13} />
                        </Link>
                      </div>
                    </div>
                  </article>
                );
              })}
            </>
          ) : (
            <div className="documents-empty">
              <Sparkles size={28} />
              <h3>No matching passages</h3>
              <p>Try different words or a shorter phrase.</p>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
