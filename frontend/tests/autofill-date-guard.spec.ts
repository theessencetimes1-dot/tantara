import { expect, test } from '@playwright/test';
import { normalizeAutofillField } from '../src/features/autofill/normalize';

test('a statute year is never written into a date field', () => {
  const year = normalizeAutofillField({
    key: 'contract_date',
    value: '1996',
    provenance: 'ai_suggested',
    confidence: 0.31,
  });
  expect(year.value).toBe('');
  expect(year.status).toBe('needs_review');
  const impossible = normalizeAutofillField({ key: 'notice_date', value: '2025-02-30', confidence: 0.95 });
  expect(impossible.value).toBe('');
  expect(impossible.status).toBe('needs_review');
  const realDate = normalizeAutofillField({ key: 'contract_date', value: '2025-02-28', confidence: 0.95 });
  expect(realDate.value).toBe('2025-02-28');
});
