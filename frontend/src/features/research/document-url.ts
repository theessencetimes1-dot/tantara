export function documentPageUrl(documentId: string, page: number, chunkId?: string): string {
  const query = new URLSearchParams({ page: String(page) });
  if (chunkId) query.set('chunk', chunkId);
  return `/documents/${encodeURIComponent(documentId)}?${query.toString()}`;
}
