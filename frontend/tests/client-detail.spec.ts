import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { expect, test, type APIRequestContext } from '@playwright/test';
import type { Client } from '../src/features/clients/api';

const apiOrigin = process.env.TANTARA_API_ORIGIN ?? 'http://127.0.0.1:8010';
const apiV1 = `${apiOrigin}/api/v1`;

async function signIn(request: APIRequestContext) {
  const response = await request.post(`${apiV1}/auth/login`, {
    data: { email: 'advocate@tantara.local', password: 'tantara-local' },
  });
  expect(response.status()).toBe(200);
  return (await response.json()).access_token as string;
}

test('client profile uses case detail width, real contact fields, and linked cases', async ({
  page,
  request,
}) => {
  const token = await signIn(request);
  const headers = { Authorization: `Bearer ${token}` };
  const clientsResponse = await request.get(`${apiV1}/clients?page=1&page_size=100`, { headers });
  expect(clientsResponse.ok()).toBeTruthy();
  const clients = (await clientsResponse.json()).items as Array<{ id: string; name: string }>;

  let client: Client | undefined;
  let linkedCases: Array<{ id: string; title: string; reference_number?: string; status?: string }> = [];
  for (const row of clients) {
    const [detailResponse, casesResponse] = await Promise.all([
      request.get(`${apiV1}/clients/${row.id}`, { headers }),
      request.get(`${apiV1}/clients/${row.id}/cases`, { headers }),
    ]);
    expect(detailResponse.ok()).toBeTruthy();
    expect(casesResponse.ok()).toBeTruthy();
    const cases = (await casesResponse.json()).items as typeof linkedCases;
    if (cases.length) {
      client = (await detailResponse.json()) as Client;
      linkedCases = cases;
      break;
    }
  }
  expect(client, 'a seeded client with linked cases is available').toBeTruthy();
  expect(linkedCases.length).toBeGreaterThan(0);

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);

  await page.goto(`/cases/${linkedCases[0].id}`);
  const caseWrap = page.locator('.matter-wrap');
  await expect(caseWrap).toBeVisible();
  const caseMaxWidth = await caseWrap.evaluate((element) => getComputedStyle(element).maxWidth);

  await page.goto(`/clients/${client!.id}`);
  const clientWrap = page.locator('.matter-wrap');
  await expect(clientWrap).toBeVisible();
  await expect(page.getByRole('button', { name: 'Account menu' })).toContainText('advocate@tantara.local');
  const clientMaxWidth = await clientWrap.evaluate((element) => getComputedStyle(element).maxWidth);
  expect(clientMaxWidth).toBe(caseMaxWidth);
  expect(clientMaxWidth).toBe('1200px');

  await expect(page.getByRole('heading', { name: client!.name, level: 1 })).toBeVisible();
  const expectedFields = {
    organization: client!.organization || 'No organization on record',
    email: client!.email || 'No email on record',
    phone: client!.phone || 'No phone on record',
    address: client!.address || 'No address on record',
    notes: client!.notes || 'No client notes recorded.',
  };
  for (const [field, value] of Object.entries(expectedFields))
    await expect(page.locator(`[data-field="${field}"] dd`)).toHaveText(value);
  await expect(page.locator('.client-detail-head .status-pill')).toHaveText(
    client!.status || 'No status recorded',
  );

  for (const linkedCase of linkedCases) {
    const card = page.locator('.client-case-card').filter({ hasText: linkedCase.title });
    await expect(card).toBeVisible();
    await expect(card.getByRole('link', { name: linkedCase.title })).toHaveAttribute(
      'href',
      `/cases/${linkedCase.id}`,
    );
    await expect(card.getByRole('link', { name: 'Open case' })).toHaveAttribute(
      'href',
      `/cases/${linkedCase.id}`,
    );
  }

  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1440);
  await mkdir(path.resolve(process.cwd(), '../docs/screenshots'), { recursive: true });
  await page.screenshot({ path: '../docs/screenshots/client-detail-1440.png' });
});
