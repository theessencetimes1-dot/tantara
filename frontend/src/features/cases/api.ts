import { api } from '@/lib/api/client';
export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  status_counts?: Record<string, number>;
};
export type Matter = {
  id: string;
  title: string;
  reference_number?: string;
  status?: string;
  forum?: string;
  institution?: string;
  next_hearing_at?: string;
  client_id?: string;
  is_demo?: boolean;
  claimant?: string;
  respondent?: string;
  claim_amount?: number;
  claim_currency?: string;
  arbitration_agreement_details?: string;
  seat?: string;
  governing_law?: string;
  description?: string;
  [key: string]: unknown;
};
export const casesApi = {
  list: (query = '') => api.get<Page<Matter>>(`/cases${query}`),
  get: (id: string) => api.get<Matter>(`/cases/${id}`),
  create: (v: unknown) => api.post<Matter>('/cases', v),
  update: (id: string, v: unknown) => api.patch<Matter>(`/cases/${id}`, v),
  remove: (id: string) => api.del<void>(`/cases/${id}`),
  archive: (id: string) => api.post<Matter>(`/cases/${id}/archive`),
  overview: (id: string) => api.get<unknown>(`/cases/${id}/overview`),
  events: (id: string) => api.get<Page<any>>(`/cases/${id}/events`),
  participants: (id: string) => api.get<unknown>(`/cases/${id}/overview`),
  addParticipant: (id: string, body: unknown) => api.post<unknown>(`/cases/${id}/participants`, body),
  updateParticipant: (id: string, pid: string, body: unknown) =>
    api.patch<unknown>(`/cases/${id}/participants/${pid}`, body),
  removeParticipant: (id: string, pid: string) => api.del<void>(`/cases/${id}/participants/${pid}`),
  addEvent: (id: string, body: unknown) => api.post<unknown>(`/cases/${id}/events`, body),
  updateEvent: (id: string, eid: string, body: unknown) =>
    api.patch<unknown>(`/cases/${id}/events/${eid}`, body),
  removeEvent: (id: string, eid: string) => api.del<void>(`/cases/${id}/events/${eid}`),
  addHearing: (body: unknown) => api.post<unknown>('/hearings', body),
  updateHearing: (hid: string, body: unknown) => api.patch<unknown>(`/hearings/${hid}`, body),
  removeHearing: (hid: string) => api.del<void>(`/hearings/${hid}`),
  addNote: (body: unknown) => api.post<unknown>('/notes', body),
  updateNote: (nid: string, body: unknown) => api.patch<unknown>(`/notes/${nid}`, body),
  removeNote: (nid: string) => api.del<void>(`/notes/${nid}`),
  hearings: (id: string) => api.get<Page<any>>(`/hearings?case_id=${encodeURIComponent(id)}`),
  hearingsForList: () =>
    api.get<Page<{ case_id?: string; at?: string }>>('/hearings?page=1&page_size=100&sort=at'),
  tasks: (id: string) => api.get<Page<any>>(`/tasks?case_id=${encodeURIComponent(id)}`),
  notes: (id: string) => api.get<Page<any>>(`/notes?case_id=${encodeURIComponent(id)}`),
  strategy: (id: string) => api.get<unknown>(`/cases/${id}/strategy`),
  documents: (id: string) => api.get<Page<any>>(`/documents?case_id=${encodeURIComponent(id)}&page_size=100`),
  drafts: (id: string) => api.get<Page<any>>(`/drafts?case_id=${encodeURIComponent(id)}&page_size=100`),
};
