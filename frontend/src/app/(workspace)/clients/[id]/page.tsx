'use client';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { clientsApi } from '@/features/clients/api';
import '@/features/cases/styles.css';

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
  const client = c.data;
  return (
    <section className="matter-wrap client-detail" aria-label="Client profile">
      <header className="matter-head client-detail-head">
        <div>
          <p className="subheading">
            <Link href="/clients">Clients</Link> / Client profile
          </p>
          <h1 className="matter-title">{client?.name || 'Client name unavailable'}</h1>
        </div>
        <span className={`status-pill ${client?.status || ''}`}>
          {client?.status || 'No status recorded'}
        </span>
      </header>
      <section className="matter-card client-profile-card" aria-labelledby="client-details-heading">
        <h2 id="client-details-heading">Client details</h2>
        <dl className="client-profile-data">
          <div data-field="organization">
            <dt>Organization</dt>
            <dd>{client?.organization || 'No organization on record'}</dd>
          </div>
          <div data-field="email">
            <dt>Email</dt>
            <dd>{client?.email || 'No email on record'}</dd>
          </div>
          <div data-field="phone">
            <dt>Phone</dt>
            <dd>{client?.phone || 'No phone on record'}</dd>
          </div>
          <div data-field="address">
            <dt>Address</dt>
            <dd>{client?.address || 'No address on record'}</dd>
          </div>
          <div data-field="notes">
            <dt>Notes</dt>
            <dd>{String(client?.notes || 'No client notes recorded.')}</dd>
          </div>
        </dl>
      </section>
      <section className="client-linked-cases" aria-labelledby="client-cases-heading">
        <h2 id="client-cases-heading">Linked cases</h2>
        {cases.isError ? (
          <p>Linked cases are unavailable.</p>
        ) : cases.isLoading ? (
          <p>Loading linked cases…</p>
        ) : cases.data?.items?.length ? (
          <div className="client-case-list">
            {cases.data.items.map((item) => (
              <article className="matter-card client-case-card" key={item.id}>
                <div>
                  <h3>
                    <Link href={`/cases/${item.id}`}>{item.title}</Link>
                  </h3>
                  <p>
                    {item.reference_number || 'No reference number'} · {item.status || 'Status unavailable'}
                  </p>
                </div>
                <Link className="matter-action" href={`/cases/${item.id}`}>
                  Open case
                </Link>
              </article>
            ))}
          </div>
        ) : (
          <p className="matter-empty">No cases are linked to this client.</p>
        )}
      </section>
    </section>
  );
}
