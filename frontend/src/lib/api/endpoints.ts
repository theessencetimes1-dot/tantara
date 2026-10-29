import { api } from './client';
import type { Activity, Case, Summary, Upcoming, User } from './types';
export type List<T> = { items: T[]; total: number; page: number; page_size: number; pages: number };
export type AskResponse = {
  status: 'ok' | 'no_evidence' | 'model_unavailable' | 'embedding_unavailable';
  raw_status?: string;
  answer_basis?: string;
  answer: string;
  citations: Array<{
    citation_ref: string;
    document_id: string;
    document_title: string;
    chunk_id: string;
    page_number: number;
    excerpt: string;
    retrieval_score: number;
  }>;
  follow_ups: string[];
  disclaimer?: string;
  research_session_id?: string;
  message_id?: string;
};
type RawAskResponse = Omit<AskResponse, 'status'> & { status: string };
export function normalizeAskResponse(response: RawAskResponse): AskResponse {
  const insufficient =
    response.status === 'insufficient_evidence' || response.answer_basis === 'insufficient_evidence';
  return {
    ...response,
    status: insufficient ? 'no_evidence' : (response.status as AskResponse['status']),
    raw_status: response.status,
  };
}
export const endpoints = {
  login: (body: { email: string; password: string }) =>
    api.post<{ access_token: string; token_type: string; user: User }>('/auth/login', body),
  me: () => api.get<User>('/auth/me'),
  meta: {
    institutions: () => api.get<{ items: string[] } | string[]>('/meta/institutions'),
    caseStatuses: () => api.get<unknown>('/meta/case-statuses'),
    disputeCategories: () => api.get<unknown>('/meta/dispute-categories'),
    documentTypes: () => api.get<unknown>('/meta/document-types'),
    jurisdictions: () =>
      api.get<{ items: Array<{ id: string; name: string } | string> }>('/meta/jurisdictions'),
  },
  summary: () => api.get<Summary>('/dashboard/summary'),
  activity: () => api.get<Activity[]>('/dashboard/activity'),
  upcoming: () => api.get<Upcoming[]>('/dashboard/upcoming?days=30'),
  cases: (query = '') => api.get<List<Case>>(`/cases${query ? `?${query}` : ''}`),
  case: (id: string) => api.get<Case>(`/cases/${id}`),
  createCase: (body: unknown) => api.post<Case>('/cases', body),
  updateCase: (id: string, body: unknown) => api.patch<Case>(`/cases/${id}`, body),
  deleteCase: (id: string) => api.del<void>(`/cases/${id}`),
  clients: {
    list: (query = '') => api.get<List<unknown>>(`/clients${query}`),
    create: (body: unknown) => api.post<unknown>('/clients', body),
    update: (id: string, body: unknown) => api.patch<unknown>(`/clients/${id}`, body),
    remove: (id: string) => api.del<void>(`/clients/${id}`),
  },
  tasks: {
    list: (query = '') => api.get<List<unknown>>(`/tasks${query}`),
    create: (body: unknown) => api.post<unknown>('/tasks', body),
    update: (id: string, body: unknown) => api.patch<unknown>(`/tasks/${id}`, body),
    remove: (id: string) => api.del<void>(`/tasks/${id}`),
  },
  hearings: {
    list: (query = '') => api.get<List<unknown>>(`/hearings${query}`),
    create: (body: unknown) => api.post<unknown>('/hearings', body),
    update: (id: string, body: unknown) => api.patch<unknown>(`/hearings/${id}`, body),
    remove: (id: string) => api.del<void>(`/hearings/${id}`),
  },
  documents: {
    list: (query = '') => api.get<List<unknown>>(`/documents${query}`),
    get: (id: string) => api.get<unknown>(`/documents/${id}`),
    upload: (form: FormData) =>
      api.post<{ document_id: string; job_id: string; status: string; duplicate: boolean }>(
        '/documents/upload',
        form,
      ),
    update: (id: string, body: unknown) => api.patch<unknown>(`/documents/${id}`, body),
    remove: (id: string) => api.del<void>(`/documents/${id}`),
    job: (id: string) => api.get<unknown>(`/documents/${id}/job`),
    retry: (id: string) => api.post<unknown>(`/documents/${id}/retry`),
    aiRead: (id: string) => api.post<unknown>(`/documents/${id}/ai-read`),
    extraction: (id: string) => api.patch<unknown>(`/documents/${id}/extraction`, {}),
    pages: (id: string) => api.get<unknown>(`/documents/${id}/pages`),
    text: (id: string) => api.get<unknown>(`/documents/${id}/text`),
  },
  searchDocuments: (query: string) =>
    api.get<{
      items: Array<{
        document_id: string;
        chunk_id: string;
        page_number: number;
        snippet: string;
        score: number;
      }>;
    }>(`/search/documents?query=${encodeURIComponent(query)}`),
  ask: async (body: {
    question: string;
    top_k?: number;
    case_id?: string;
    collection_id?: string;
    jurisdiction?: string;
    document_types?: string[];
  }): Promise<AskResponse> => {
    const response = await api.post<RawAskResponse>('/ai/ask', body);
    return normalizeAskResponse(response);
  },
  sessions: () => api.get<List<{ id: string; title: string; updated_at?: string }>>('/ai/sessions'),
  session: (id: string) => api.get<unknown>(`/ai/sessions/${id}`),
  createSession: (body: unknown = {}) => api.post<unknown>('/ai/sessions', body),
  deleteSession: (id: string) => api.del<void>(`/ai/sessions/${id}`),
  saveResearch: (body: unknown) => api.post<unknown>('/ai/saved', body),
  savedResearch: () => api.get<List<unknown>>('/ai/saved'),
  aiStatus: () => api.get<Record<string, unknown>>('/ai/status'),
  draftTemplates: () => api.get<List<unknown>>('/draft-templates'),
  drafts: (query = '') => api.get<List<unknown>>(`/drafts${query}`),
  createDraft: (body: unknown) => api.post<unknown>('/drafts', body),
  generateDraft: (body: unknown) => api.post<unknown>('/drafts/generate', body),
  bundles: (query = '') => api.get<List<unknown>>(`/bundles${query}`),
  createBundle: (body: unknown) => api.post<unknown>('/bundles', body),
  strategy: (caseId: string) => api.get<unknown>(`/cases/${caseId}/strategy`),
  generateStrategy: (caseId: string) => api.post<unknown>(`/cases/${caseId}/strategy/generate`),
  community: {
    posts: (query = '') => api.get<List<unknown>>(`/community/posts${query}`),
    createPost: (body: unknown) => api.post<unknown>('/community/posts', body),
  },
  settings: (section: string) =>
    api.get<Record<string, unknown>>(
      section === 'local-ai'
        ? '/settings/ai'
        : section === 'data-import'
          ? '/settings/data/import'
          : `/settings/${section}`,
    ),
  updateSettings: (section: string, body: unknown) =>
    api.patch<Record<string, unknown>>(
      section === 'local-ai' ? '/settings/ai' : `/settings/${section}`,
      body,
    ),
};
