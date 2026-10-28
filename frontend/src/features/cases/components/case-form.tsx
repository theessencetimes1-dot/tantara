'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { endpoints } from '@/lib/api/endpoints';
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
  claim_amount: z.coerce.number().optional(),
  claim_currency: z.string().default('INR'),
  status: z.string().default('active'),
  description: z.string().optional(),
  notice_date: z.string().optional(),
  next_hearing_at: z.string().optional(),
  filed_at: z.string().optional(),
  limitation_date: z.string().optional(),
});
type Values = z.infer<typeof schema>;
export function CaseForm({ caseId }: { caseId?: string }) {
  const router = useRouter();
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
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isDirty, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { claim_currency: 'INR', status: 'active' },
  });
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
    try {
      const result = caseId ? await casesApi.update(caseId, v) : await casesApi.create(v);
      toast.success(caseId ? 'Case updated' : 'Case created');
      router.push(`/cases/${result.id}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Unable to save case');
    }
  };
  const input = (label: keyof Values, title: string, type = 'text', wide = false) => (
    <label className={wide ? 'wide' : ''} key={label}>
      {title}
      <input type={type} {...register(label)} />
      {errors[label] && <small className="matter-error-text">{String(errors[label]?.message)}</small>}
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
          {input('title', 'Case title')}
          {input('reference_number', 'Reference number')}
          {input('claimant', 'Claimant')}
          {input('respondent', 'Respondent')}
          <label>
            Client
            <select {...register('client_id')}>
              <option value="">Select client</option>
              {((clients.data as any)?.items || []).map((c: any) => (
                <option key={c.id} value={c.id}>
                  {c.name || c.title}
                </option>
              ))}
            </select>
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
