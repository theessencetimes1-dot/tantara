import { expect, test } from '@playwright/test';

const base = `${process.env.TANTARA_API_ORIGIN || 'http://127.0.0.1:8010'}/api/v1`;

test('calendar, task and client API contracts cover auth, validation, empty and pagination edges', async ({
  request,
}) => {
  const login = await request.post(`${base}/auth/login`, {
    data: {
      email: process.env.TANTARA_E2E_EMAIL || 'advocate@tantara.local',
      password: process.env.TANTARA_E2E_PASSWORD || 'tantara-local',
    },
  });
  test.skip(!login.ok(), 'TANTARA seeded API is not available');
  const token = (await login.json()).access_token as string;
  const headers = { Authorization: `Bearer ${token}` };
  const suffix = Date.now();
  let clientId = '';
  let taskId = '';
  try {
    const calendar = await request.get(`${base}/calendar?from=2026-10-01&to=2026-11-01`, { headers });
    expect(calendar.ok()).toBeTruthy();
    expect(Array.isArray(await calendar.json())).toBeTruthy();

    const invalidCalendar = await request.get(`${base}/calendar?from=not-a-date&to=2026-11-01`, { headers });
    expect(invalidCalendar.status()).toBeGreaterThanOrEqual(400);

    const clients = await request.get(`${base}/clients?page_size=5`, {
      headers,
    });
    expect(clients.ok()).toBeTruthy();
    const emptyClients = await request.get(`${base}/clients?q=no-such-api-client-${suffix}`, { headers });
    expect((await emptyClients.json()).items).toHaveLength(0);

    const invalidClient = await request.post(`${base}/clients`, {
      headers,
      data: {},
    });
    expect(invalidClient.status()).toBe(422);
    const clientResponse = await request.post(`${base}/clients`, {
      headers,
      data: { name: `API contract client ${suffix}` },
    });
    expect(clientResponse.ok()).toBeTruthy();
    const client = await clientResponse.json();
    clientId = client.id;
    const linkedCases = await request.get(`${base}/clients/${clientId}/cases`, {
      headers,
    });
    expect(linkedCases.ok()).toBeTruthy();
    expect((await linkedCases.json()).items).toHaveLength(0);

    const tasks = await request.get(`${base}/tasks?page_size=5`, { headers });
    expect(tasks.ok()).toBeTruthy();
    const farFuturePage = await request.get(`${base}/tasks?page=999999&page_size=20`, { headers });
    expect(farFuturePage.ok()).toBeTruthy();
    expect((await farFuturePage.json()).items).toHaveLength(0);
    const invalidTask = await request.post(`${base}/tasks`, {
      headers,
      data: {},
    });
    expect(invalidTask.status()).toBe(422);
    const taskResponse = await request.post(`${base}/tasks`, {
      headers,
      data: { title: `API contract task ${suffix}`, status: 'todo' },
    });
    expect(taskResponse.ok()).toBeTruthy();
    const task = await taskResponse.json();
    taskId = task.id;
    const taskGet = await request.get(`${base}/tasks/${taskId}`, { headers });
    expect(taskGet.ok()).toBeTruthy();
    expect((await taskGet.json()).id).toBe(taskId);
    const taskPatch = await request.patch(`${base}/tasks/${taskId}`, {
      headers,
      data: { priority: 'high' },
    });
    expect(taskPatch.ok()).toBeTruthy();
    expect((await taskPatch.json()).priority).toBe('high');

    for (const path of [
      '/calendar?from=2026-10-01&to=2026-11-01',
      '/tasks',
      '/clients',
      `/clients/${clientId}/cases`,
      `/tasks/${taskId}`,
    ]) {
      const anonymous = await request.get(`${base}${path}`);
      expect(anonymous.status(), `${path} requires authentication`).toBe(401);
    }
    for (const [path, method, data] of [
      ['/clients', 'POST', { name: 'Anonymous' }],
      ['/tasks', 'POST', { title: 'Anonymous' }],
      [`/tasks/${taskId}`, 'PATCH', { status: 'done' }],
    ] as const) {
      const anonymous = await request.fetch(`${base}${path}`, {
        method,
        data,
      });
      expect(anonymous.status(), `${method} ${path} requires authentication`).toBe(401);
    }
  } finally {
    if (taskId) await request.delete(`${base}/tasks/${taskId}`, { headers });
    if (clientId) await request.delete(`${base}/clients/${clientId}`, { headers });
  }
});

test.skip('cross-user client, task and calendar reads reject access with 403 or 404', async () => {
  // API-GOTCHAS.md records that this backend seed currently creates one user only.
  // Enable this contract when the backend seed provisions a second authenticated user.
});
