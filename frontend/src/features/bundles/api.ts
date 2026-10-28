import { apiBase, authToken } from '@/lib/api/client';

export type BundleItem = {
  document_id: string;
  title: string;
  section: string;
  order: number;
  pages: number;
  page_start: number;
  page_end: number;
};
export type Bundle = {
  id: string;
  name: string;
  case_id?: string;
  status: string;
  created_at: string;
  updated_at?: string;
  case_title?: string | null;
  section_count?: number;
  page_count?: number;
  file_size_bytes?: number | null;
  settings?: Record<string, boolean>;
  downloadable?: boolean;
  download_url?: string | null;
};
export type BundlePreview = {
  sections: Array<{
    title: string;
    items: Array<BundleItem & { start_page: number; end_page: number }>;
  }>;
  total_pages: number;
  warnings: string[];
};
export type CaseOption = { id: string; title: string; reference_number?: string };
export type DocumentOption = {
  id: string;
  title: string;
  page_count: number;
  case_id?: string;
  status?: string;
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = authToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (init.body) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${apiBase}${path}`, { ...init, headers });
  const payload: unknown = response.status === 204 ? undefined : await response.json().catch(() => undefined);
  if (!response.ok) {
    const body = payload as { detail?: unknown; error?: { message?: string } } | undefined;
    const message =
      body?.error?.message ??
      (typeof body?.detail === 'string' ? body.detail : undefined) ??
      response.statusText;
    throw Object.assign(new Error(message), { status: response.status });
  }
  return payload as T;
}

export const bundleApi = {
  cases: () => request<{ items: CaseOption[] }>('/cases?page_size=100'),
  documents: (caseId: string) =>
    request<{ items: DocumentOption[] }>(`/documents?case_id=${encodeURIComponent(caseId)}&page_size=100`),
  list: () => request<{ items: Bundle[]; total: number }>('/bundles?page_size=100'),
  get: (id: string) => request<Bundle>(`/bundles/${encodeURIComponent(id)}`),
  preview: (id: string) => request<BundlePreview>(`/bundles/${encodeURIComponent(id)}/preview`),
  create: (body: { name: string; case_id: string; settings: Record<string, boolean> }) =>
    request<Bundle>('/bundles', { method: 'POST', body: JSON.stringify(body) }),
  updateItems: (
    id: string,
    items: Array<Pick<BundleItem, 'document_id' | 'section' | 'order' | 'page_start' | 'page_end'>>,
  ) =>
    request<{ items: unknown[] }>(`/bundles/${encodeURIComponent(id)}/items`, {
      method: 'PUT',
      body: JSON.stringify({ items }),
    }),
  updateSections: (id: string, sections: Array<{ title: string; order: number }>) =>
    request<{ sections: Array<{ title: string; order: number }> }>(
      `/bundles/${encodeURIComponent(id)}/sections`,
      { method: 'PUT', body: JSON.stringify({ sections }) },
    ),
  updateSettings: (id: string, settings: Record<string, boolean>) =>
    request<Bundle>(`/bundles/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify({ settings }),
    }),
  generate: (id: string) =>
    request<{ job_id: string; status: string; pages: number; download_url: string }>(
      `/bundles/${encodeURIComponent(id)}/generate`,
      { method: 'POST', body: '{}' },
    ),
  downloadUrl: (id: string) => `${apiBase}/bundles/${encodeURIComponent(id)}/download`,
};
