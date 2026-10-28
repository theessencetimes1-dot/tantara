'use client';
import Link from 'next/link';
import { useParams, usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { ApiError } from '@/lib/api/client';
import { workspaceDateTimeInput, workspaceDateTimeIso } from '@/lib/datetime';
import { casesApi } from '@/features/cases/api';
import { RefreshCw } from 'lucide-react';
import { StrategyPanel } from '@/features/cases/components/strategy';
import '@/features/cases/styles.css';

const tabs = [
  'Overview',
  'Timeline',
  'Parties',
  'Documents',
  'Research',
  'Drafts',
  'Hearings',
  'Tasks',
  'Notes',
  'Strategy',
  'Activity log',
];
type RecordValue = Record<string, unknown>;
function listFrom(value: unknown): RecordValue[] {
  if (Array.isArray(value)) return value as RecordValue[];
  if (
    value &&
    typeof value === 'object' &&
    'items' in value &&
    Array.isArray((value as { items: unknown }).items)
  )
    return (value as { items: RecordValue[] }).items;
  return [];
}
function Records({
  title,
  rows,
  fields,
  onEdit,
  onRemove,
}: {
  title: string;
  rows: RecordValue[];
  fields: Array<[string, string]>;
  onEdit?: (row: RecordValue) => void;
  onRemove?: (row: RecordValue) => void;
}) {
  return (
    <section>
      <h2>{title}</h2>
      {rows.length ? (
        <div className="case-record-list">
          {rows.map((row, index) => (
            <article key={String(row.id || index)}>
              <strong>{String(row.title || row.name || row.event_type || row.action || title)}</strong>
              <dl>
                {fields.map(([key, label]) => (
                  <div key={key}>
                    <dt>{label}</dt>
                    <dd>{row[key] == null || row[key] === '' ? '—' : String(row[key])}</dd>
                  </div>
                ))}
              </dl>
              {(onEdit || onRemove) && (
                <div className="case-record-actions">
                  {onEdit && (
                    <button type="button" onClick={() => onEdit(row)}>
                      Edit
                    </button>
                  )}
                  {onRemove && (
                    <button type="button" onClick={() => onRemove(row)}>
                      Delete
                    </button>
                  )}
                </div>
              )}
            </article>
          ))}
        </div>
      ) : (
        <p className="matter-empty case-inline-empty">No {title.toLowerCase()} recorded for this case.</p>
      )}
    </section>
  );
}
export default function CaseDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const [editor, setEditor] = useState('');
  const [editorTitle, setEditorTitle] = useState('');
  const [editorDate, setEditorDate] = useState('');
  const [editorBody, setEditorBody] = useState('');
  const [editorRole, setEditorRole] = useState('counsel');
  const [saving, setSaving] = useState(false);
  const [recordId, setRecordId] = useState('');
  const requestedTab = params.get('tab');
  const [selectedTab, setSelectedTab] = useState(
    requestedTab && tabs.includes(requestedTab) ? requestedTab : 'Overview',
  );
  useEffect(() => {
    setSelectedTab(requestedTab && tabs.includes(requestedTab) ? requestedTab : 'Overview');
  }, [requestedTab]);
  const tab = selectedTab;
  const selectTab = (nextTab: string) => {
    setSelectedTab(nextTab);
    const query = new URLSearchParams(params.toString());
    query.set('tab', nextTab);
    router.replace(`${pathname}?${query}`, { scroll: false });
  };
  const c = useQuery({
    queryKey: ['case', id],
    queryFn: () => casesApi.get(id),
  });
  const overview = useQuery({
    queryKey: ['case-overview', id],
    queryFn: () => casesApi.overview(id),
    enabled: !c.isLoading && !c.isError,
  });
  const keyed: Record<string, () => Promise<unknown>> = {
    Timeline: () => casesApi.events(id),
    Hearings: () => casesApi.hearings(id),
    Tasks: () => casesApi.tasks(id),
    Notes: () => casesApi.notes(id),
    Documents: () => casesApi.documents(id),
    Drafts: () => casesApi.drafts(id),
  };
  const payload = useQuery({
    queryKey: ['case-tab', id, tab],
    queryFn: keyed[tab] || (() => Promise.resolve(null)),
    enabled: !!keyed[tab] && !!c.data,
  });
  if (c.isLoading)
    return (
      <section className="matter-wrap">
        <div className="matter-card matter-skeleton" aria-label="Loading case" />
      </section>
    );
  if (c.isError) {
    const missing = c.error instanceof ApiError && c.error.status === 404;
    return (
      <section className="matter-wrap">
        <div className="matter-card matter-not-found">
          <h1>{missing ? 'Case not found' : 'Case is unavailable'}</h1>
          <p>
            {missing
              ? 'This case may have been removed or you may not have access.'
              : 'The case could not be loaded. Check the workspace connection and retry.'}
          </p>
          <button className="matter-action" onClick={() => void c.refetch()}>
            <RefreshCw size={14} /> Retry
          </button>
          <Link href="/cases">Back to cases</Link>
        </div>
      </section>
    );
  }
  const item = c.data!;
  const over = (overview.data || {}) as RecordValue;
  const people = listFrom(over.participants);
  const facts = [...Object.entries(item), ...Object.entries(over)].reduce<Record<string, unknown>>(
    (a, [k, v]) => ((a[k] = v), a),
    {},
  );
  const setTab = (name: string) =>
    router.replace(`/cases/${id}?tab=${encodeURIComponent(name)}`, {
      scroll: false,
    });
  const rows = listFrom(payload.data);
  const createRecord = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    try {
      if (editor === 'Timeline') {
        const value = {
          type: editorTitle,
          occurred_at: workspaceDateTimeIso(editorDate),
          detail: editorBody,
        };
        if (recordId) await casesApi.updateEvent(id, recordId, value);
        else await casesApi.addEvent(id, value);
      }
      if (editor === 'Hearings') {
        const value = {
          case_id: id,
          title: editorTitle,
          at: workspaceDateTimeIso(editorDate),
          notes: editorBody,
        };
        if (recordId) await casesApi.updateHearing(recordId, value);
        else await casesApi.addHearing(value);
      }
      if (editor === 'Notes') {
        const value = {
          case_id: id,
          title: editorTitle,
          body: editorBody,
        };
        if (recordId) await casesApi.updateNote(recordId, value);
        else await casesApi.addNote(value);
      }
      if (editor === 'Parties') {
        const value = {
          name: editorTitle,
          party_role: editorRole,
          organization: editorBody || null,
        };
        if (recordId) await casesApi.updateParticipant(id, recordId, value);
        else await casesApi.addParticipant(id, value);
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['case-tab', id, editor] }),
        queryClient.invalidateQueries({ queryKey: ['case-overview', id] }),
        queryClient.invalidateQueries({ queryKey: ['case', id] }),
      ]);
      setEditor('');
      setRecordId('');
      setEditorTitle('');
      setEditorDate('');
      setEditorBody('');
    } catch (error) {
      window.alert(error instanceof Error ? error.message : 'Unable to save record');
    } finally {
      setSaving(false);
    }
  };
  const editRecord = (section: string, row: RecordValue) => {
    setRecordId(String(row.id || ''));
    setEditor(section);
    setEditorTitle(String(row.title || row.type || row.name || ''));
    setEditorDate(workspaceDateTimeInput(String(row.at || row.occurred_at || '')));
    setEditorBody(String(row.body || row.detail || row.notes || row.organization || ''));
    setEditorRole(String(row.party_role || 'counsel'));
  };
  const deleteRecord = async (section: string, row: RecordValue) => {
    if (!window.confirm(`Delete “${String(row.title || row.name || section)}”?`)) return;
    try {
      if (section === 'Timeline') await casesApi.removeEvent(id, String(row.id));
      if (section === 'Hearings') await casesApi.removeHearing(String(row.id));
      if (section === 'Parties') await casesApi.removeParticipant(id, String(row.id));
      if (section === 'Notes') await casesApi.removeNote(String(row.id));
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['case-tab', id, section] }),
        queryClient.invalidateQueries({ queryKey: ['case-overview', id] }),
      ]);
    } catch (error) {
      window.alert(error instanceof Error ? error.message : 'Unable to delete record');
    }
  };
  return (
    <section className="matter-wrap case-detail">
      <p className="subheading">
        <Link href="/cases">Cases</Link> / Case workspace
      </p>
      <header className="matter-head case-detail-header">
        <div>
          <h1 className="matter-title">{item.title}</h1>
          <p className="subheading">
            {item.reference_number || 'No reference'} · {item.status || 'Status unavailable'} ·{' '}
            {item.forum || item.institution || 'Institution unavailable'}
          </p>
        </div>
        <Link className="matter-action" href={`/cases/${id}/edit`}>
          Edit case
        </Link>
      </header>
      <nav
        className="matter-tabs case-detail-tabs"
        aria-label="Case sections"
        role="tablist"
        onKeyDown={(event) => {
          if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
          event.preventDefault();
          const currentIndex = tabs.indexOf(tab);
          const direction = event.key === 'ArrowRight' ? 1 : -1;
          const nextIndex = (currentIndex + direction + tabs.length) % tabs.length;
          const nextTab = tabs[nextIndex];
          selectTab(nextTab);
          event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')[nextIndex]?.focus();
        }}
      >
        {tabs.map((name) => (
          <button
            type="button"
            key={name}
            role="tab"
            id={`case-${id}-tab-${name.toLowerCase().replaceAll(/[^a-z0-9]+/g, '-')}`}
            aria-controls={`case-${id}-tabpanel`}
            className={tab === name ? 'active' : ''}
            aria-selected={tab === name}
            tabIndex={tab === name ? 0 : -1}
            onClick={() => selectTab(name)}
          >
            {name}
          </button>
        ))}
      </nav>
      <section
        className="matter-card case-detail-panel"
        role="tabpanel"
        id={`case-${id}-tabpanel`}
        aria-labelledby={`case-${id}-tab-${tab.toLowerCase().replaceAll(/[^a-z0-9]+/g, '-')}`}
        tabIndex={0}
      >
        {tab === 'Overview' ? (
          <div className="grid dashboard-columns">
            <div>
              <h2>Case overview</h2>
              <dl className="data-list">
                {[
                  ['Case title', facts.title],
                  ['Reference number', facts.reference_number],
                  ['Claimant', facts.claimant],
                  ['Respondent', facts.respondent],
                  ['Institution', facts.forum || facts.institution],
                  ['Seat', facts.seat],
                  ['Governing law', facts.governing_law],
                  ['Status', facts.status],
                  [
                    'Claim amount',
                    facts.claim_amount !== undefined
                      ? new Intl.NumberFormat('en-IN', {
                          style: 'currency',
                          currency: String(facts.claim_currency || 'INR'),
                          maximumFractionDigits: 2,
                        }).format(Number(facts.claim_amount))
                      : undefined,
                  ],
                  ['Arbitration agreement', facts.arbitration_agreement_details],
                  ['Description', facts.description],
                  [
                    'Next hearing',
                    facts.next_hearing_at
                      ? new Date(String(facts.next_hearing_at)).toLocaleDateString('en-IN', {
                          day: '2-digit',
                          month: 'short',
                          year: 'numeric',
                        })
                      : undefined,
                  ],
                ].map(([label, value]) => (
                  <div key={String(label)}>
                    <dt>{String(label)}</dt>
                    <dd>{value == null || value === '' ? '—' : String(value)}</dd>
                  </div>
                ))}
              </dl>
              {people.length > 0 && (
                <Records
                  title="Parties"
                  rows={people}
                  fields={[
                    ['party_role', 'Role'],
                    ['email', 'Email'],
                  ]}
                />
              )}
            </div>
            <div>
              <h2>Quick actions</h2>
              <p>
                <Link href={`/calendar?case_id=${encodeURIComponent(id)}`}>Open calendar for this case</Link>
              </p>
              <p>
                <Link href={`/tasks?case_id=${encodeURIComponent(id)}`}>Open tasks for this case</Link>
              </p>
              <p>
                Documents: {String(over.documents_count ?? '—')} · Drafts: {String(over.drafts_count ?? '—')}
              </p>
            </div>
          </div>
        ) : tab === 'Strategy' ? (
          <StrategyPanel id={id} />
        ) : tab === 'Timeline' ? (
          <Records
            title="Timeline events"
            rows={rows}
            fields={[
              ['type', 'Type'],
              ['detail', 'Details'],
              ['occurred_at', 'Date'],
            ]}
            onEdit={(row) => editRecord('Timeline', row)}
            onRemove={(row) => void deleteRecord('Timeline', row)}
          />
        ) : tab === 'Hearings' ? (
          <Records
            title="Hearings"
            rows={rows}
            fields={[
              ['at', 'Date and time'],
              ['forum', 'Institution'],
              ['venue', 'Location'],
              ['status', 'Status'],
            ]}
            onEdit={(row) => editRecord('Hearings', row)}
            onRemove={(row) => void deleteRecord('Hearings', row)}
          />
        ) : tab === 'Tasks' ? (
          <Records
            title="Tasks"
            rows={rows}
            fields={[
              ['due_at', 'Due'],
              ['status', 'Status'],
              ['priority', 'Priority'],
            ]}
          />
        ) : tab === 'Parties' ? (
          <Records
            title="Parties and participants"
            rows={people}
            fields={[
              ['party_role', 'Role'],
              ['email', 'Email'],
              ['organization', 'Organization'],
            ]}
            onEdit={(row) => editRecord('Parties', row)}
            onRemove={(row) => void deleteRecord('Parties', row)}
          />
        ) : tab === 'Documents' ? (
          <Records
            title="Documents"
            rows={rows}
            fields={[
              ['document_type', 'Type'],
              ['created_at', 'Added'],
            ]}
          />
        ) : tab === 'Drafts' ? (
          <Records
            title="Drafts"
            rows={rows}
            fields={[
              ['document_type', 'Type'],
              ['status', 'Status'],
              ['updated_at', 'Updated'],
            ]}
          />
        ) : tab === 'Notes' ? (
          <Records
            title="Notes"
            rows={rows}
            fields={[
              ['body', 'Note'],
              ['kind', 'Type'],
              ['created_at', 'Added'],
            ]}
            onEdit={(row) => editRecord('Notes', row)}
            onRemove={(row) => void deleteRecord('Notes', row)}
          />
        ) : tab === 'Activity log' ? (
          <div className="matter-unavailable">
            <h2>Activity log</h2>
            <p>The API does not expose an audit or case activity listing endpoint.</p>
          </div>
        ) : (
          <div className="matter-unavailable">
            <h2>{tab}</h2>
            <p>
              {tab === 'Research'
                ? 'The API does not expose case-linked saved research records.'
                : 'The case resource is not available.'}
            </p>
          </div>
        )}
        {['Timeline', 'Hearings', 'Parties', 'Notes'].includes(tab) && (
          <div className="case-record-editor-wrap">
            {editor !== tab ? (
              <button className="matter-action" onClick={() => setEditor(tab)}>
                {tab === 'Timeline'
                  ? 'Add event'
                  : tab === 'Hearings'
                    ? 'Add hearing'
                    : tab === 'Parties'
                      ? 'Add participant'
                      : 'Add note'}
              </button>
            ) : (
              <form className="case-record-editor" onSubmit={createRecord}>
                <h3>
                  {tab === 'Timeline'
                    ? 'New timeline event'
                    : tab === 'Hearings'
                      ? 'New hearing'
                      : tab === 'Parties'
                        ? 'New participant'
                        : 'New note'}
                </h3>
                <label>
                  {tab === 'Parties' ? 'Name' : 'Title'}
                  <input
                    required
                    value={editorTitle}
                    onChange={(event) => setEditorTitle(event.target.value)}
                  />
                </label>
                {tab === 'Parties' && (
                  <label>
                    Role
                    <select value={editorRole} onChange={(event) => setEditorRole(event.target.value)}>
                      {['claimant', 'respondent', 'arbitrator', 'counsel', 'witness'].map((role) => (
                        <option key={role} value={role}>
                          {role}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {(tab === 'Timeline' || tab === 'Hearings') && (
                  <label>
                    Date and time
                    <input
                      required
                      type="datetime-local"
                      value={editorDate}
                      onChange={(event) => setEditorDate(event.target.value)}
                    />
                  </label>
                )}
                <label>
                  {tab === 'Parties' ? 'Organization' : tab === 'Notes' ? 'Note' : 'Details'}
                  <textarea value={editorBody} onChange={(event) => setEditorBody(event.target.value)} />
                </label>
                <div className="matter-dialog-actions">
                  <button type="button" onClick={() => setEditor('')}>
                    Cancel
                  </button>
                  <button className="matter-action" disabled={saving}>
                    {saving ? 'Saving…' : 'Save'}
                  </button>
                </div>
              </form>
            )}
          </div>
        )}
        {tab !== 'Overview' &&
          tab !== 'Strategy' &&
          tab !== 'Notes' &&
          tab !== 'Activity log' &&
          !['Documents', 'Drafts', 'Research'].includes(tab) &&
          payload.isError && (
            <div className="matter-error">
              {tab} could not be loaded. <button onClick={() => void payload.refetch()}>Retry</button>
            </div>
          )}
      </section>
    </section>
  );
}
