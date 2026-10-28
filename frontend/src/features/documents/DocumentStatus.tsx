export function DocumentStatus({ status }: { status?: string }) {
  const label = status ? status.charAt(0).toUpperCase() + status.slice(1) : '—';
  return (
    <span
      className={`document-status ${status || 'unknown'}`}
      aria-label={`Document processing status: ${label}`}
    >
      {label}
    </span>
  );
}
