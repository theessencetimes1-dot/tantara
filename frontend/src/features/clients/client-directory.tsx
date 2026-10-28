'use client';
import Link from 'next/link';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { clientsApi } from './api';
import { displayClientStatus } from './status';
import * as Dialog from '@radix-ui/react-dialog';
import '../cases/styles.css';
export function ClientDirectory() {
  const [q, S] = useState(''),
    [modal, M] = useState(false),
    [name, N] = useState(''),
    [email, E] = useState('');
  const list = useQuery({
    queryKey: ['clients', q],
    queryFn: () => clientsApi.list(`?q=${encodeURIComponent(q)}&page_size=50`),
  });
  return (
    <section className="matter-wrap">
      <div className="matter-head">
        <div>
          <h1 className="matter-title">Clients</h1>
          <p className="subheading">Client directory</p>
        </div>
        <button className="matter-action" onClick={() => M(true)}>
          ＋ New Client
        </button>
      </div>
      <div className="matter-card">
        <div className="matter-tools">
          <input
            aria-label="Search clients"
            placeholder="Search clients…"
            value={q}
            onChange={(e) => S(e.target.value)}
          />
        </div>
        {list.isLoading ? (
          <>
            <div className="matter-table-scroll" role="region" aria-label="Clients table" tabIndex={0}>
              <table className="matter-table">
                <thead>
                  <tr>
                    <th>Client</th>
                    <th>Email</th>
                    <th>Cases</th>
                    <th>Status</th>
                  </tr>
                </thead>
              </table>
            </div>
            <p className="matter-skeleton" />
          </>
        ) : list.isError ? (
          <div className="matter-error client-error">
            <p>Clients are unavailable.</p>
            <button className="matter-action" onClick={() => void list.refetch()}>
              Retry
            </button>
          </div>
        ) : list.data?.items.length ? (
          <div
            className="matter-table-scroll"
            role="region"
            aria-label="Clients table; scroll horizontally to view all columns"
            tabIndex={0}
          >
            <table className="matter-table">
              <thead>
                <tr>
                  <th>Client</th>
                  <th>Email</th>
                  <th>Cases</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <Link href={`/clients/${c.id}`}>{c.name}</Link>
                    </td>
                    <td>{c.email || '—'}</td>
                    <td>{String(c.case_count ?? '—')}</td>
                    <td>
                      {c.status || <span title="Status unavailable">{displayClientStatus(c.status)}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="matter-empty">{q ? 'No matching clients' : 'No clients yet'}</div>
        )}
      </div>
      <Dialog.Root open={modal} onOpenChange={M}>
        <Dialog.Portal>
          <Dialog.Overlay className="matter-dialog-overlay" />
          <Dialog.Content className="matter-dialog" aria-describedby="client-dialog-description">
            <Dialog.Title>New client</Dialog.Title>
            <Dialog.Description id="client-dialog-description">
              Add a client to your workspace.
            </Dialog.Description>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                try {
                  await clientsApi.create({ name, email });
                  M(false);
                  N('');
                  E('');
                  await list.refetch();
                } catch (err) {
                  alert(err instanceof Error ? err.message : 'Unable to save client');
                }
              }}
            >
              <label>
                Name
                <input aria-label="Client name" required value={name} onChange={(e) => N(e.target.value)} />
              </label>
              <label>
                Email
                <input
                  type="email"
                  aria-label="Client email"
                  value={email}
                  onChange={(e) => E(e.target.value)}
                />
              </label>
              <button className="matter-action">Save client</button>
              <button type="button" onClick={() => M(false)}>
                Cancel
              </button>
            </form>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </section>
  );
}
