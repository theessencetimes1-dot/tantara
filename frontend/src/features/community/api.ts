import { api, apiBase, authToken } from '@/lib/api/client';

export type CommunityPost = {
  id: string;
  title: string;
  body: string;
  tags?: string[];
  author?: { id?: string; name?: string; display_name?: string; role?: string; email?: string };
  author_id?: string;
  author_name?: string;
  author_role?: string;
  case_id?: string | null;
  case_title?: string | null;
  created_at?: string;
  saved?: boolean;
  is_saved?: boolean;
  is_demo?: boolean;
  kind?: 'discussion' | 'question';
  visibility?: 'private' | 'workspace';
  case_ref?: string | null;
};
export type CommunityReply = {
  id: string;
  body: string;
  author?: { id?: string; name?: string; display_name?: string; role?: string };
  author_id?: string;
  author_name?: string;
  created_at?: string;
  is_demo?: boolean;
};
export type Page<T> = { items: T[]; total: number; page: number; page_size: number; pages: number };
export type CaseItem = { id: string; title: string };
export type Identity = { id?: string; name?: string; email?: string; role?: string };

export class CommunityValidationError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string,
    public details: Array<{ loc?: Array<string | number>; msg?: string }> = [],
  ) {
    super(message);
  }
}

async function createPost(input: {
  title: string;
  body: string;
  tags: string[];
  kind: 'discussion' | 'question';
  visibility: 'private' | 'workspace';
  case_ref?: string;
}) {
  const token = authToken();
  const response = await fetch(`${apiBase}/community/posts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(input),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = payload.error ?? {};
    if (response.status === 401 && typeof window !== 'undefined') window.location.assign('/');
    throw new CommunityValidationError(
      error.message ?? response.statusText,
      response.status,
      error.code ?? 'request_failed',
      error.details ?? [],
    );
  }
  return payload as CommunityPost;
}

export const communityApi = {
  list: (page: number, q: string, tag: string, saved?: boolean) => {
    const params = new URLSearchParams({ page: String(page), page_size: '100', sort: '-created_at' });
    if (q.trim()) params.set('q', q.trim());
    if (tag) params.set('tag', tag);
    if (saved !== undefined) params.set('saved', String(saved));
    return api.get<Page<CommunityPost> & { tags?: string[] }>(`/community/posts?${params}`);
  },
  post: (id: string) => api.get<CommunityPost>(`/community/posts/${id}`),
  replies: (id: string) =>
    api.get<CommunityReply[] | { items: CommunityReply[] }>(`/community/posts/${id}/replies`),
  create: createPost,
  reply: (id: string, body: string) => api.post<CommunityReply>(`/community/posts/${id}/replies`, { body }),
  save: (id: string) => api.post<{ saved: boolean }>(`/community/posts/${id}/save`),
  cases: () => api.get<Page<CaseItem>>('/cases?page_size=100'),
  me: () => api.get<Identity>('/auth/me'),
};

export function errorMessage(error: unknown) {
  if (error && typeof error === 'object' && 'message' in error) return String(error.message);
  return 'The request could not be completed.';
}
