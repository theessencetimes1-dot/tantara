import { api } from '@/lib/api/client';
export type Client = {
  id: string;
  name: string;
  organization?: string;
  email?: string;
  phone?: string;
  address?: string;
  status?: string;
  notes?: string;
  [key: string]: unknown;
};
export const clientsApi = {
  list: (q = '') => api.get<{ items: Client[]; total: number }>(`/clients${q}`),
  get: (id: string) => api.get<Client>(`/clients/${id}`),
  cases: (id: string) =>
    api.get<{
      items: Array<{
        id: string;
        title: string;
        reference_number?: string;
        status?: string;
      }>;
    }>(`/clients/${id}/cases`),
  create: (v: unknown) => api.post<Client>('/clients', v),
  update: (id: string, v: unknown) => api.patch<Client>(`/clients/${id}`, v),
  remove: (id: string) => api.del<void>(`/clients/${id}`),
};
