'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ApiError } from '@/lib/api/client';
import { endpoints } from '@/lib/api/endpoints';
import { clientsApi, type Client } from '@/features/clients/api';
import { casesApi, Matter } from '../api';
import '../styles.css';
const schema = z.object({
  title: z.string().min(1, 'Enter a case title'),
  reference_number: z.string().optional(),
  claimant: z.string().optional(),
  respondent: z.string().optional(),
  client_id: z.string().optional(),
  forum: z.string().optional(),
  seat: z.string().optional(),
  governing_law: z.string().optional(),
  arbitration_agreement_details: z.string().optional(),
  dispute_category: z.string().optional(),
  claim_amount: z.number().optional(),
  claim_currency: z.string().default('INR'),
  status: z.string().default('active'),
  description: z.string().optional(),
  notice_date: z.string().optional(),
  next_hearing_at: z.string().optional(),
  filed_at: z.string().optional(),
  limitation_date: z.string().optional(),
});
type Values = z.infer<typeof schema>;

const optionalTextFields = [
  'reference_number',
  'claimant',
  'respondent',
  'client_id',
  'forum',
  'seat',
  'governing_law',
  'arbitration_agreement_details',
  'dispute_category',
  'description',
  'notice_date',
  'next_hearing_at',
  'filed_at',
  'limitation_date',
] as const satisfies readonly (keyof Values)[];

function normalizeCasePayload(values: Values): Partial<Values> {
  const payload: Partial<Values> = { ...values };
  for (const field of optionalTextFields) {
    const value = payload[field];
    if (typeof value !== 'string') continue;
    const trimmed = value.trim();
    if (trimmed) payload[field] = trimmed;
    else delete payload[field];
  }
  for (const [field, value] of Object.entries(payload))
    if (value === undefined) delete payload[field as keyof Values];
  return payload;
}

const caseFields = new Set<keyof Values>([
  'title',
  ...optionalTextFields,
  'claim_amount',
  'claim_currency',
  'status',
]);

type ValidationDetail = { loc?: Array<string | number>; msg?: string };
export function CaseForm({ caseId }: { caseId?: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const clients = useQuery({
    queryKey: ['clients', 'select'],
    queryFn: () => endpoints.clients.list('?page_size=100'),
  });
  const institutions = useQuery({
    queryKey: ['meta', 'institutions'],
    queryFn: endpoints.meta.institutions,
  });
  const existing = useQuery({
    queryKey: ['case', caseId],
    queryFn: () => casesApi.get(caseId!),
    enabled: !!caseId,
  });
  const [serverError, setServerError] = useState('');
  const [clientName, setClientName] = useState('');
  const [showAddClient, setShowAddClient] = useState(false);
  const [addingClient, setAddingClient] = useState(false);
  const [clientNotice, setClientNotice] = useState('');
  const {
    register,
    handleSubmit,
    reset,
    setError,
    setValue,
    watch,
    clearErrors,
    formState: { errors, isDirty, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { claim_currency: 'INR', status: 'active' },
  });
  const selectedClientId = watch('client_id');
  const addClient = async (name = clientName) => {
    const cleanName = name.trim();
    if (!cleanName) return;
    setAddingClient(true);
    setClientNotice('');
    try {
      const created = (await clientsApi.create({ name: cleanName })) as Client;
      queryClient.setQueryData(['clients', 'select'], (current: unknown) => {
        const list = current as { items?: Client[] } | undefined;
        const items = list?.items ?? [];
        return {
          ...(list ?? {}),
          items: items.some((client) => client.id === created.id) ? items : [...items, created],
        };
      });
      setValue('client_id', created.id, { shouldDirty: true, shouldValidate: true });
      setClientName('');
      setShowAddClient(false);
      setClientNotice(`${created.name} added and selected`);
      await clients.refetch();
    } catch (error) {
      setServerError(error instanceof Error ? error.message : 'Unable to add client');
    } finally {
      setAddingClient(false);
    }
  };
  useEffect(() => {
    if (existing.data) reset(existing.data as unknown as Values);
  }, [existing.data, reset]);
  useEffect(() => {
    const guard = (e: BeforeUnloadEvent) => {
      if (isDirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, [isDirty]);
  const submit = async (v: Values) => {
    setServerError('');
    clearErrors();
    try {
      const payload = normalizeCasePayload(v);
      const result = caseId ? await casesApi.update(caseId, payload) : await casesApi.create(payload);
      queryClient.setQueryData(['case', result.id], result);
      toast.success(caseId ? 'Case updated' : 'Case created');
      router.push(`/cases/${result.id}`);
    } catch (e) {
      const details =
        e instanceof ApiError && Array.isArray(e.details) ? (e.details as ValidationDetail[]) : [];
      let mapped = false;
      for (const detail of details) {
        const field = [...(detail.loc ?? [])]
          .reverse()
          .find(
            (part): part is keyof Values => typeof part === 'string' && caseFields.has(part as keyof Values),
          );
        if (!field) continue;
        setError(field, { type: 'server', message: detail.msg || 'Value is invalid' });
        mapped = true;
      }
      if (!mapped) setServerError(e instanceof Error ? e.message : 'Unable to save case');
    }
  };
  const input = (label: keyof Values, title: string, type = 'text', wide = false) => (
    <label className={wide ? 'wide' : ''} key={label}>
      {title}
      <input
        type={type}
        {...register(
          label,
          label === 'claim_amount'
            ? { setValueAs: (value) => (value === '' ? undefined : Number(value)) }
            : undefined,
        )}
      />
      {errors[label] && (
        <small className="matter-error-text" role="alert">
          {String(errors[label]?.message)}
        </small>
      )}
    </label>
  );
  return (
    <section className="matter-wrap">
      <div className="matter-head">
        <div>
          <h1 className="matter-title">{caseId ? 'Edit case' : 'New case'}</h1>
          <p className="subheading">Case information and arbitration details</p>
        </div>
        <Link href="/cases">Cancel</Link>
      </div>
      {existing.isError ? (
        <p className="matter-error">Could not load case information.</p>
      ) : (
        <form className="matter-card matter-form" onSubmit={handleSubmit(submit)}>
          {serverError && (
            <p className="matter-error-text wide" role="alert">
              {serverError}
            </p>
          )}
          {input('title', 'Case title')}
          {input('reference_number', 'Reference number')}
          {input('claimant', 'Claimant')}
          {input('respondent', 'Respondent')}
          <label>
            Client
            <select
              aria-label="Client"
              {...register('client_id')}
              value={selectedClientId ?? ''}
              onChange={(event) => setValue('client_id', event.target.value, { shouldDirty: true })}
            >
              <option value="">
                {clients.isLoading
                  ? 'Loading clients…'
                  : (clients.data as any)?.items?.length
                    ? 'Select client'
                    : 'No clients yet — add one'}
              </option>
              {((clients.data as any)?.items || []).map((c: Client) => (
                <option key={c.id} value={c.id}>
                  {c.name || String(c.title || '')}
                </option>
              ))}
              {selectedClientId &&
                !(clients.data as any)?.items?.some((client: Client) => client.id === selectedClientId) &&
                existing.data && (
                  <option value={selectedClientId}>
                    {(existing.data as any).client_name || 'Current client'}
                  </option>
                )}
            </select>
            <div className="client-picker-create">
              <button
                type="button"
                aria-expanded={showAddClient}
                onClick={() => setShowAddClient((open) => !open)}
              >
                ＋ Add client
              </button>
              {showAddClient && (
                <>
                  <input
                    aria-label="New client name"
                    placeholder="Type a client name"
                    value={clientName.trim() ? clientName : ''}
                    onFocus={() => {
                      if (!clientName) setClientName('');
                    }}
                    onChange={(event) => setClientName(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault();
                        void addClient();
                      }
                    }}
                  />
                  {clientName.trim() && (
                    <button type="button" disabled={addingClient} onClick={() => void addClient()}>
                      {addingClient ? 'Adding…' : `Add “${clientName.trim()}”`}
                    </button>
                  )}
                </>
              )}
            </div>
            <span className="sr-only" role="status" aria-live="polite">
              {clientNotice}
            </span>
          </label>
          <label>
            Forum / institution
            <select {...register('forum')}>
              <option value="">Select institution</option>
              {(
                (institutions.data as any)?.items ||
                institutions.data || ['SIAC', 'ICC', 'LCIA', 'DIAC', 'Ad Hoc']
              ).map((v: any) => (
                <option key={typeof v === 'string' ? v : v.name} value={typeof v === 'string' ? v : v.name}>
                  {typeof v === 'string' ? v : v.name}
                </option>
              ))}
            </select>
          </label>
          {input('seat', 'Seat')}
          {input('governing_law', 'Governing law')}
          {input('dispute_category', 'Dispute category')}
          {input('claim_amount', 'Claim amount', 'number')}
          {input('claim_currency', 'Currency')}
          {input('notice_date', 'Notice date', 'date')}
          {input('next_hearing_at', 'Next hearing', 'datetime-local')}
          {input('filed_at', 'Filed at', 'date')}
          {input('limitation_date', 'Limitation date', 'date')}
          <label>
            Status
            <select {...register('status')}>
              <option value="active">Active</option>
              <option value="pending">Pending</option>
              <option value="closed">Closed</option>
            </select>
          </label>
          {input('arbitration_agreement_details', 'Arbitration agreement details')}
          {input('description', 'Description', 'text', true)}
          <div className="wide" style={{ display: 'flex', justifyContent: 'end', gap: 10 }}>
            <button
              type="button"
              onClick={() => {
                if (!isDirty || confirm('Discard unsaved changes?')) router.push('/cases');
              }}
            >
              Cancel
            </button>
            <button className="matter-action" disabled={isSubmitting}>
              {isSubmitting ? 'Saving…' : 'Save case'}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
