/** Checked-in fallback OpenAPI snapshot for local generation when the API is offline. */
export const openApiSnapshot = {
  openapi: '3.0.3',
  info: { title: 'TANTARA API', version: '1.0.0' },
  servers: [{ url: '/api/v1' }],
  paths: {
    '/auth/login': { post: { summary: 'Create local session' } },
    '/auth/me': { get: { summary: 'Current user' } },
    '/dashboard/summary': { get: { summary: 'Dashboard metrics' } },
    '/dashboard/activity': { get: { summary: 'Recent activity' } },
    '/dashboard/upcoming': { get: { summary: 'Upcoming hearings and deadlines' } },
    '/ai/ask': { post: { summary: 'Grounded arbitration research' } },
    '/ai/status': { get: { summary: 'Provider status' } },
    '/settings/profile': { get: {}, patch: {} },
    '/settings/workspace': { get: {}, patch: {} },
    '/settings/ai': { get: {}, patch: {} },
    '/settings/embeddings': { get: {} },
    '/settings/database': { get: {} },
    '/settings/data/import': { get: {}, post: {} },
    '/settings/appearance': { get: {}, patch: {} },
    '/settings/security': { get: {} },
    '/settings/password': { post: {} },
  },
} as const;
