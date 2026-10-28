import type { AutofillField } from './api';

const labels: Record<string, string> = {
  title: 'Case Title',
  reference_number: 'Case Number',
  claimant: 'Claimant',
  respondent: 'Respondent',
  forum: 'Arbitral Tribunal / Institution',
  seat: 'Seat',
  governing_law: 'Governing Law',
  contract_date: 'Contract Date',
  contract_dates: 'Contract Dates',
  arbitration_agreement_details: 'Arbitration Clause',
  key_events: 'Key Events',
  legal_representatives: 'Legal Representatives',
};
export const dateKey = (key: string) =>
  key.toLowerCase().includes('date') || key.toLowerCase().endsWith('_at');
export const validDate = (value: string) => {
  const date = value.slice(0, 10);
  return (
    /^\d{4}-\d{2}-\d{2}$/.test(date) &&
    !Number.isNaN(Date.parse(value)) &&
    new Date(`${date}T00:00:00Z`).toISOString().slice(0, 10) === date
  );
};

export function normalizeAutofillField(field: any): AutofillField {
  const key = String(field.key ?? 'unknown');
  const nested = field.value && typeof field.value === 'object' ? field.value : null;
  const raw = String(nested?.value ?? field.value ?? '');
  const badYear = dateKey(key) && /^\d{4}$/.test(raw);
  const badDate = dateKey(key) && !!raw && !validDate(raw);
  const confidence = field.confidence === undefined ? undefined : Number(field.confidence);
  return {
    key,
    label: labels[key] ?? field.label ?? key.replaceAll('_', ' ').replace(/\b\w/g, (x) => x.toUpperCase()),
    value: badDate ? '' : raw,
    provenance: String(field.provenance ?? 'ai_suggested'),
    source_document: field.source ?? field.source_document,
    document_id: field.document_id,
    page_number: field.page_number ?? nested?.page_number,
    confidence,
    status:
      badYear || badDate || (confidence !== undefined && confidence < 0.7) ? 'needs_review' : field.status,
  };
}
