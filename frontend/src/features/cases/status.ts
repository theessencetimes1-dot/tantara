export function matterStatusClass(status?: string) {
  const value = (status || '').toLowerCase();
  return ['active', 'pending', 'closed'].includes(value) ? value : 'unknown';
}
export function matterStatusLabel(status?: string) {
  if (!status) return '—';
  return status.charAt(0).toUpperCase() + status.slice(1);
}
