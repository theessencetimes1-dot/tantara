export function documentHref(documentId: string, pageNumber?: number): string {
  const basePath = `/documents/${encodeURIComponent(documentId)}`;
  if (!pageNumber || !Number.isInteger(pageNumber) || pageNumber < 1) return basePath;
  return `${basePath}?page=${pageNumber}`;
}
