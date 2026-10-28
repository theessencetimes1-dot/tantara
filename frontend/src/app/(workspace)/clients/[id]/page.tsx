'use client';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { clientsApi } from '@/features/clients/api';
export default function ClientDetails() {
  const { id } = useParams<{ id: string }>();
  const c = useQuery({
    queryKey: ['client', id],
    queryFn: () => clientsApi.get(id),
  });
  const cases = useQuery({
    queryKey: ['client-cases', id],
    queryFn: () => clientsApi.cases(id),
  });
  if (c.isLoading) return <p>Loading client…</p>;
  if (c.isError) return <p className="matter-error">Client information unavailable.</p>;
  return (
    <section className="matter-wrap">
      <Link href="/clients">← Clients</Link>
      <h1 className="matter-title">{c.data?.name}</h1>
      <p>{c.data?.email || 'No email on record'}</p>
      <h2>Linked cases</h2>
      {cases.isError ? (
        <p>Linked cases are unavailable.</p>
      ) : (
        cases.data?.items?.map((x) => (
          <p key={x.id}>
            <Link href={`/cases/${x.id}`}>{x.title}</Link>
          </p>
        ))
      )}
      <h2>Notes</h2>
      <p>{String(c.data?.notes || 'No client notes recorded.')}</p>
    </section>
  );
}
