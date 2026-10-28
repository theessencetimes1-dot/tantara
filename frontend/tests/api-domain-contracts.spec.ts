import { expect, test } from '@playwright/test';
import { requirePlaywrightApi } from './api-readiness';

const base = `${process.env.TANTARA_API_ORIGIN || 'http://127.0.0.1:8010'}/api/v1`;
test.beforeAll(async () => requirePlaywrightApi());

test('calendar, task and client API contracts cover auth, validation, empty and pagination edges', async ({
  request,
}) => {
  const login = await request.post(`${base}/auth/login`, {
    data: {
      email: process.env.TANTARA_E2E_EMAIL || 'advocate@tantara.local',
      password: process.env.TANTARA_E2E_PASSWORD || 'tantara-local',
    },
  });
  expect(login.ok(), `Seeded API login failed at ${base}/auth/login`).toBeTruthy();
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

test('cross-user domain reads hide foreign records and read-only roles cannot create cases or bundles', async ({
  request,
}) => {
  const loginAs = async (email: string) => {
    const response = await request.post(`${base}/auth/login`, {
      data: { email, password: process.env.TANTARA_E2E_PASSWORD || 'tantara-local' },
    });
    expect(response.ok(), `${email} can authenticate against the seeded API`).toBeTruthy();
    return { Authorization: `Bearer ${(await response.json()).access_token as string}` };
  };
  const advocate = await loginAs('advocate@tantara.local');
  const researcher = await loginAs('researcher@tantara.local');
  const staff = await loginAs('staff@tantara.local');
  const resources = [
    { path: 'cases', title: 'Junior Demo Matter' },
    { path: 'bundles', title: 'Junior Demo Bundle' },
    { path: 'drafts', title: 'Junior Research Note' },
    { path: 'clients', title: 'Junior Demo Client' },
    { path: 'tasks', title: 'Junior demo research task' },
    { path: 'documents', title: 'Junior Demo Evidence' },
  ];
  const itemFor = (payload: unknown, title: string) => {
    const rows = Array.isArray(payload)
      ? payload
      : payload && typeof payload === 'object' && 'items' in payload && Array.isArray(payload.items)
        ? payload.items
        : [];
    return rows.find((row) => {
      if (!row || typeof row !== 'object') return false;
      const record = row as Record<string, unknown>;
      return record.title === title || record.name === title;
    }) as Record<string, unknown> | undefined;
  };

  for (const resource of resources) {
    const seeded = await request.get(`${base}/${resource.path}?q=${encodeURIComponent(resource.title)}`, {
      headers: researcher,
    });
    expect(seeded.ok(), `researcher can list their seeded ${resource.path}`).toBeTruthy();
    const juniorRecord = itemFor(await seeded.json(), resource.title);
    expect(juniorRecord?.id, `researcher seed includes ${resource.title}`).toBeTruthy();
    const ownRead = await request.get(`${base}/${resource.path}/${juniorRecord!.id}`, {
      headers: researcher,
    });
    expect(ownRead.status(), `researcher can read their ${resource.path} record`).toBe(200);

    const advocateRead = await request.get(`${base}/${resource.path}/${juniorRecord!.id}`, {
      headers: advocate,
    });
    expect(advocateRead.status(), `advocate cannot read researcher ${resource.path}`).toBe(404);
    expect(await advocateRead.text()).not.toContain(resource.title);

    const advocateList = await request.get(`${base}/${resource.path}?page_size=100`, {
      headers: advocate,
    });
    expect(advocateList.ok()).toBeTruthy();
    const advocateRows = await advocateList.json();
    const firstAdvocateRow = Array.isArray(advocateRows) ? advocateRows[0] : advocateRows.items?.[0];
    expect(firstAdvocateRow?.id, `advocate seed includes an owned ${resource.path} record`).toBeTruthy();
    const researcherRead = await request.get(`${base}/${resource.path}/${firstAdvocateRow.id}`, {
      headers: researcher,
    });
    expect(researcherRead.status(), `researcher cannot read advocate ${resource.path}`).toBe(404);
  }

  for (const [role, headers] of [
    ['researcher', researcher],
    ['staff', staff],
  ] as const) {
    const caseCreate = await request.post(`${base}/cases`, {
      headers,
      data: { title: `${role} must not create a case` },
    });
    expect(caseCreate.status(), `${role} cannot create a case`).toBe(403);
    const bundleCreate = await request.post(`${base}/bundles`, {
      headers,
      data: { name: `${role} must not create a bundle` },
    });
    expect(bundleCreate.status(), `${role} cannot create a bundle`).toBe(403);
  }
});
