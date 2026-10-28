import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { expect, test, type APIRequestContext } from '@playwright/test';

const apiOrigin = process.env.TANTARA_API_ORIGIN ?? 'http://127.0.0.1:8010';
const apiV1 = `${apiOrigin}/api/v1`;

async function signIn(request: APIRequestContext) {
  const response = await request.post(`${apiV1}/auth/login`, {
    data: { email: 'advocate@tantara.local', password: 'tantara-local' },
  });
  expect(response.status()).toBe(200);
  return (await response.json()).access_token as string;
}

test('case form omits blank optional fields and displays server date validation inline', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const token = await signIn(request);
  const headers = { Authorization: `Bearer ${token}` };
  let createdCaseId = '';
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);

  try {
    const title = `Minimal case ${Date.now()}`;
    await page.goto('/cases/new');
    await expect(page.getByRole('heading', { name: 'New case' })).toBeVisible();
    await page.getByLabel('Case title').fill(title);
    const createRequest = page.waitForRequest(
      (candidate) => new URL(candidate.url()).pathname === '/api/v1/cases' && candidate.method() === 'POST',
    );
    const createResponse = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === '/api/v1/cases' && response.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Save case' }).click();
    const response = await createResponse;
    const created = await response.json();
    expect(response.status(), JSON.stringify(created)).toBe(201);
    const payload = createRequest.then((candidate) => candidate.postDataJSON());
    const submitted = await payload;
    expect(submitted.title).toBe(title);
    expect(submitted.status).toBe('active');
    expect(submitted.claim_currency).toBe('INR');
    for (const field of [
      'reference_number',
      'claimant',
      'respondent',
      'client_id',
      'forum',
      'seat',
      'governing_law',
      'dispute_category',
      'claim_amount',
      'description',
      'notice_date',
      'next_hearing_at',
      'filed_at',
      'limitation_date',
    ])
      expect(submitted, `${field} should be omitted when blank`).not.toHaveProperty(field);

    createdCaseId = created.id as string;
    await expect(page).toHaveURL(new RegExp(`/cases/${createdCaseId}$`));
    await expect(page.getByRole('heading', { name: title, level: 1 })).toBeVisible();
    const detailResponse = await request.get(`${apiV1}/cases/${createdCaseId}`, { headers });
    expect(detailResponse.status()).toBe(200);
    expect((await detailResponse.json()).title).toBe(title);

    await page.goto('/cases/new');
    await page.waitForLoadState('networkidle');
    await page.getByLabel('Case title').fill(`Invalid date case ${Date.now()}`);
    const filedAt = page.getByLabel('Filed at');
    await filedAt.fill('2999-12-31');
    await expect(filedAt).toHaveValue('2999-12-31');
    const submitInvalid = page.waitForResponse(
      (candidate) =>
        new URL(candidate.url()).pathname === '/api/v1/cases' && candidate.request().method() === 'POST',
    );
    const invalidRequest = page.waitForRequest(
      (candidate) => new URL(candidate.url()).pathname === '/api/v1/cases' && candidate.method() === 'POST',
    );
    await page.getByRole('button', { name: 'Save case' }).click();
    const rejected = await submitInvalid;
    const submittedInvalid = await invalidRequest.then((candidate) => candidate.postDataJSON());
    expect(rejected.status(), JSON.stringify(submittedInvalid)).toBe(422);
    const invalidPayload = await rejected.json();
    const dateIssue = (invalidPayload.error.details as Array<{ loc: unknown[]; msg: string }>).find(
      (issue) => issue.loc.includes('notice_date') || issue.loc.includes('filed_at'),
    );
    expect(dateIssue).toBeTruthy();
    const field = dateIssue!.loc.includes('filed_at')
      ? page.getByLabel('Filed at')
      : page.getByLabel('Notice date');
    await expect(field.locator('xpath=..').locator('.matter-error-text[role="alert"]')).toContainText(
      dateIssue!.msg,
    );
    await expect(page).toHaveURL('/cases/new');
    await expect(page.getByRole('button', { name: 'Account menu' })).toContainText('advocate@tantara.local');
    expect(await page.evaluate(() => localStorage.getItem('tantara_token'))).toBe(token);
    expect(await page.evaluate(() => window.innerWidth)).toBe(1440);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1440);
    await mkdir(path.resolve(process.cwd(), '../docs/screenshots'), { recursive: true });
    await page.screenshot({ path: '../docs/screenshots/case-form-validation-1440.png' });
  } finally {
    if (createdCaseId) await request.delete(`${apiV1}/cases/${createdCaseId}`, { headers });
  }
});
