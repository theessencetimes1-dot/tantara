import { api } from '@/lib/api/client';
import { collectionsApi } from '@/features/documents/api';

export type ResearchSource = {
  citation_ref?: string;
  citation_number?: number;
  document_id: string;
  document_title: string;
  chunk_id: string;
  page_number: number;
  excerpt: string;
  retrieval_score?: number;
};

export type ResearchAnswer = {
  status: 'ok' | 'answered' | 'no_evidence' | 'model_unavailable' | 'embedding_unavailable' | 'error';
  raw_status?: string;
  answer?: string;
  citations?: ResearchSource[];
  sources?: ResearchSource[];
  follow_ups?: string[];
  disclaimer?: string;
  model?: Record<string, unknown> | null;
  answer_kind?: string;
  generation_kind?: string;
  answer_basis?: 'cited_excerpts' | 'case_record' | 'insufficient_evidence' | string;
  supports?: Array<{
    chunk_id: string;
    document_id: string;
    page_number: number;
    quote: string;
  }>;
  context_fields?: Array<{ field: string; value: string; source: string }>;
  conflicts?: Array<{
    field: string;
    case_value: string;
    excerpt_chunk_id: string;
    page_number: number;
  }>;
  insufficient_evidence?: boolean;
  research_session_id?: string;
  message_id?: string;
  meta?: Record<string, unknown>;
};

export type ResearchSession = {
  id: string;
  title: string;
  case_id?: string;
  collection_id?: string;
  jurisdiction?: string;
  updated_at?: string;
  created_at?: string;
  messages?: Array<{
    id: string;
    role: 'user' | 'assistant';
    content: string;
    status?: string;
    raw_status?: string;
    citations?: ResearchSource[];
  }>;
};

export function normalizeResearchAnswer<T extends Omit<ResearchAnswer, 'status'> & { status: string }>(
  response: T,
): ResearchAnswer {
  if (response.status === 'model_unavailable') {
    return { ...response, raw_status: response.raw_status ?? response.status, status: 'model_unavailable' };
  }
  const insufficient =
    response.status === 'no_evidence' ||
    response.status === 'insufficient_evidence' ||
    response.answer_basis === 'insufficient_evidence' ||
    response.insufficient_evidence === true;
  return {
    ...response,
    raw_status: response.raw_status ?? response.status,
    status: insufficient ? 'no_evidence' : (response.status as ResearchAnswer['status']),
  };
}

export const researchApi = {
  sessions: () => api.get<{ items: ResearchSession[] }>('/ai/sessions?page_size=100'),
  session: (id: string) => api.get<ResearchSession>(`/ai/sessions/${encodeURIComponent(id)}`),
  createSession: (title: string) => api.post<ResearchSession>('/ai/sessions', { title }),
  saved: () =>
    api.get<{ items: Array<{ id: string; item_id: string; item_type: string }> }>('/ai/saved?page_size=100'),
  cases: () =>
    api.get<{ items: Array<{ id: string; title: string; jurisdiction?: string }> }>('/cases?page_size=100'),
  collections: () => collectionsApi.list(),
  documents: () =>
    api.get<{
      items: Array<{
        id: string;
        title?: string;
        filename?: string;
        status?: string;
        page_count?: number;
        case_id?: string;
        jurisdiction?: string;
        collection_id?: string;
      }>;
    }>('/documents?page_size=100'),
  document: (id: string) =>
    api.get<{ id: string; title?: string; filename?: string }>(`/documents/${encodeURIComponent(id)}`),
  ask: (
    body: {
      question: string;
      session_id?: string;
      case_id?: string;
      collection_id?: string;
      collection_ids?: string[];
      jurisdiction?: string;
    },
    signal: AbortSignal,
  ) =>
    api
      .post<Omit<ResearchAnswer, 'status'> & { status: string }>('/ai/ask', body, signal)
      .then(normalizeResearchAnswer),
  aiStatus: () => api.get<Record<string, unknown>>('/ai/status'),
  lexical: (question: string, signal: AbortSignal) =>
    api.get<{
      items?: Array<{
        document_id: string;
        document_title: string;
        chunk_id: string;
        page_number: number;
        snippet: string;
        retrieval_score: number;
      }>;
    }>(`/search/documents?query=${encodeURIComponent(question)}&page_size=8`, signal),
  save: (id: string) => api.post('/ai/saved', { item_type: 'message', item_id: id }),
  upload: (file: File, title: string) => {
    const form = new FormData();
    form.append('file', file);
    form.append('title', title);
    return api.post<{ document_id?: string; id?: string; status?: string }>('/ingest/file', form);
  },
  ingestJob: (id: string) =>
    api.get<{ status?: string; document_id?: string }>(`/documents/${encodeURIComponent(id)}/job`),
};
