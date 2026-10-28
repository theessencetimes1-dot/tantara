import { api, apiBase, authToken, ApiError } from '@/lib/api/client';

export type Row = Record<string, any>;
export const draftsApi = {
  templates: () => api.get<{ items?: Row[] }>('/draft-templates'),
  list: () => api.get<{ items?: Row[] }>('/drafts?page=1&page_size=21'),
  cases: () => api.get<{ items?: Row[] }>('/cases?page=1&page_size=100'),
  institutions: () => api.get<{ items?: any[] } | any[]>('/meta/institutions'),
  documents: (caseId: string) =>
    api.get<{ items?: Row[] }>(`/documents?case_id=${encodeURIComponent(caseId)}&page=1&page_size=100`),
  generate: async (body: Row) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 115_000);
    try {
      const headers = new Headers({ 'Content-Type': 'application/json' });
      const token = authToken();
      if (token) headers.set('Authorization', `Bearer ${token}`);
      const response = await fetch(`${apiBase}/drafts/generate`, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!response.ok) {
        let payload: any = {};
        try {
          payload = await response.json();
        } catch {
          /* Empty error response */
        }
        throw new ApiError(
          response.status,
          payload.error?.code ?? 'request_failed',
          payload.error?.message ?? response.statusText,
        );
      }
      return (await response.json()) as Row;
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError')
        throw new Error(
          'Draft generation timed out after 115 seconds. Retry when the local model is available.',
        );
      throw error;
    } finally {
      clearTimeout(timer);
    }
  },
  get: (id: string) => api.get<Row>(`/drafts/${id}`),
  update: (id: string, body: Row) => api.patch<Row>(`/drafts/${id}`, body),
  save: (id: string, body: Row) => api.post<Row>(`/drafts/${id}/versions`, body),
  updateVersion: (id: string, body: Row) => api.post<Row>(`/drafts/${id}/versions`, body),
  versions: (id: string) => api.get<{ items?: Row[] }>(`/drafts/${id}/versions`),
  restore: (id: string, versionId: string) =>
    api.post<Row>(`/drafts/${id}/versions/${versionId}/restore`, {}),
  restoreLegacy: (id: string, body: Row) => api.post<Row>(`/drafts/${id}/versions`, body),
  regenerateSection: (id: string, body: Row) => api.post<Row>(`/drafts/${id}/regenerate-section`, body),
  export: async (id: string, format: 'pdf' | 'docx') => {
    const token = authToken();
    const response = await fetch(`${apiBase}/drafts/${id}/export?format=${format}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok) throw new ApiError(response.status, 'export_failed', response.statusText);
    return response.blob();
  },
};
