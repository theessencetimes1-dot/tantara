import { api } from '@/lib/api/client';
export type AutofillField = {
  key: string;
  label: string;
  value: string;
  provenance: string;
  source_document?: string;
  document_id?: string;
  page_number?: number;
  confidence?: number;
  status?: string;
};
export const autofillApi = {
  cases: () => api.get<{ items?: Array<Record<string, any>> }>('/cases?page=1&page_size=100'),
  documents: (id: string) =>
    api.get<{ items?: Array<Record<string, any>> }>(
      `/documents?case_id=${encodeURIComponent(id)}&page=1&page_size=100`,
    ),
  drafts: () => api.get<{ items?: Array<Record<string, any>> }>('/drafts?page=1&page_size=100'),
  draft: (id: string) => api.get<Record<string, any>>(`/drafts/${id}`),
  saveDraftVersion: (id: string, body: any) => api.post<any>(`/drafts/${id}/versions`, body),
  get: (id: string) =>
    api.get<{
      items?: AutofillField[];
      fields?: AutofillField[];
      source_documents?: Array<Record<string, any>>;
      status?: string;
      model?: unknown;
    }>(`/cases/${id}/autofill`),
  preview: (id: string, keys: string[]) => api.post<any>(`/cases/${id}/autofill/preview`, { keys }),
  apply: (id: string, body: any) => api.post<any>(`/cases/${id}/autofill/apply`, body),
};
