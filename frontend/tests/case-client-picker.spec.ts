import { expect, test, type APIRequestContext } from '@playwright/test';

const api = `${process.env.TANTARA_API_ORIGIN ?? 'http://127.0.0.1:8010'}/api/v1`;

async function login(request: APIRequestContext) {
  const response = await request.post(`${api}/auth/login`, {
    data: { email: 'advocate@tantara.local', password: 'tantara-local' },
  });
  expect(response.ok()).toBeTruthy();
  return (await response.json()).access_token as string;
}

test('new case can create a client inline and submit only the client_id association', async ({
  page,
  request,
}) => {
  const token = await login(request);
  const headers = { Authorization: `Bearer ${token}` };
  let clientId = '';
  let caseId = '';
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);
  try {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/cases/new');
    const clientName = `Picker client ${Date.now()}`;
    await page.getByRole('button', { name: '＋ Add client' }).click();
    await page.getByRole('textbox', { name: 'New client name' }).fill(clientName);
    await page.getByRole('textbox', { name: 'New client name' }).press('Enter');
    await expect(page.getByRole('status')).toContainText(`${clientName} added and selected`);
    await expect(page.getByLabel('Client')).toHaveValue(/.+/);
    await page.getByLabel('Case title').fill(`Picker case ${Date.now()}`);
    const submitted = page.waitForRequest(
      (r) => new URL(r.url()).pathname === '/api/v1/cases' && r.method() === 'POST',
    );
    const createdResponse = page.waitForResponse(
      (r) => new URL(r.url()).pathname === '/api/v1/cases' && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Save case' }).click();
    const response = await createdResponse;
    expect(response.ok()).toBeTruthy();
    const body = await submitted.then((r) => r.postDataJSON());
    const created = await response.json();
    clientId = body.client_id;
    caseId = created.id;
    expect(body.client_id).toBeTruthy();
    expect(body.client_id).toBe(await page.getByLabel('Client').inputValue());
    expect(body).not.toHaveProperty('client_name');
    await expect(page.getByRole('heading', { name: body.title })).toBeVisible();
  } finally {
    if (caseId) await request.delete(`${api}/cases/${caseId}`, { headers });
    if (clientId) await request.delete(`${api}/clients/${clientId}`, { headers });
  }
});
