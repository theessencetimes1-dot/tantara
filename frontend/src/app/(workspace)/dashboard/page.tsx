'use client';
import { useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  ArrowRight,
  CalendarDays,
  Clock,
  FileText,
  Folder,
  Plus,
  RefreshCw,
  Sparkles,
  Scale,
  CheckCircle2,
} from 'lucide-react';
import { api } from '@/lib/api/client';
import { endpoints } from '@/lib/api/endpoints';
import { WORKSPACE_TIME_ZONE, workspaceDateTimeDisplay } from '@/lib/datetime';
import { keys } from '@/lib/api/keys';
import type { Summary, Activity, Upcoming, Case } from '@/lib/api/types';
import { MattersCard } from '@/features/dashboard/matters';
import { calendarEventLabel } from '@/features/calendar/event-label';
import { collectionsApi } from '@/features/documents/api';
function Offline({ retry }: { retry: () => void }) {
  return (
    <div className="offline" role="status">
      <strong>Backend not reachable</strong>
      <div style={{ fontSize: 13 }}>
        <details>
          <summary>Start command</summary>
          <code>cd backend &amp;&amp; .venv/bin/python -m uvicorn app.main:app</code>
        </details>
      </div>
      <button className="primary" onClick={retry}>
        <RefreshCw size={15} /> Retry
      </button>
    </div>
  );
}
export default function Dashboard() {
  const summary = useQuery({ queryKey: keys.summary, queryFn: endpoints.summary }),
    activity = useQuery({ queryKey: keys.activity, queryFn: endpoints.activity }),
    upcoming = useQuery({ queryKey: keys.upcoming, queryFn: endpoints.upcoming });
  const cases = useQuery({ queryKey: keys.cases(''), queryFn: () => endpoints.cases() });
  const [question, setQuestion] = useState(''),
    [answer, setAnswer] = useState<Awaited<ReturnType<typeof endpoints.ask>> | null>(null),
    [askBusy, setAskBusy] = useState(false),
    [scope, setScope] = useState(''),
    [collection, setCollection] = useState(''),
    [jurisdiction, setJurisdiction] = useState('');
  const collections = useQuery({ queryKey: ['collections'], queryFn: collectionsApi.list });
  const jurisdictions = useQuery({
    queryKey: ['meta', 'jurisdictions'],
    queryFn: endpoints.meta.jurisdictions,
  });
  const sessions = useQuery({ queryKey: ['ai', 'sessions'], queryFn: endpoints.sessions });
  const reduceMotion = useReducedMotion();
  const offline = summary.isError || activity.isError || upcoming.isError;
  const refresh = () => {
    void summary.refetch();
    void activity.refetch();
    void upcoming.refetch();
  };
  const ask = async (q = question) => {
    if (!q.trim()) return;
    setQuestion(q);
    setAskBusy(true);
    try {
      const r = await endpoints.ask({
        question: q,
        case_id: scope || undefined,
        collection_id: collection || undefined,
        jurisdiction: jurisdiction || undefined,
      });
      setAnswer(r);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Unable to complete research');
    } finally {
      setAskBusy(false);
    }
  };
  const m = summary.data;
  const cards = [
    ['Active Cases', m?.active_cases, Folder, '#4338ca', '#eef0ff'],
    ['Arbitrations Pending', m?.pending_arbitrations, Clock, '#e11d48', '#fff0f3'],
    ['Hearings This Week', m?.hearings_this_week, CalendarDays, '#4338ca', '#eef0ff'],
    ['Documents Added', m?.documents_processed, FileText, '#d97706', '#fff7e5'],
    ['Drafts in Progress', m?.drafts_in_progress, FileText, '#4338ca', '#eef0ff'],
    ['Tasks Due', m?.tasks_due, CheckCircle2, '#08916a', '#e7f7ee'],
  ] as const;
  return (
    <div>
      <div
        style={{
          display: 'flex',
          alignItems: 'start',
          justifyContent: 'space-between',
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <div>
          <h1 className="title">
            {m?.greeting || 'Good day'}, {m?.first_name || 'there'}
          </h1>
          <p className="subheading">
            {m?.today
              ? (() => {
                  const [year, month, day] = m.today.split('-').map(Number);
                  const d = new Date(Date.UTC(year, month - 1, day, 12));
                  return Number.isNaN(d.valueOf())
                    ? m.today
                    : d.toLocaleDateString('en-GB', {
                        timeZone: WORKSPACE_TIME_ZONE,
                        weekday: 'long',
                        day: 'numeric',
                        month: 'long',
                        year: 'numeric',
                      });
                })()
              : 'Your arbitration workspace at a glance.'}
          </p>
        </div>
        {m?.is_demo && <span className="badge-demo">Sample workspace data</span>}
      </div>
      {cases.data?.items?.length ? (
        <div className="recent-chips" aria-label="Recent case work">
          {cases.data.items.slice(0, 3).map((c) => (
            <Link key={c.id} href={`/cases/${c.id}`}>
              {c.title}
            </Link>
          ))}
        </div>
      ) : null}
      <div className="dashboard-main">
        <div className="dashboard-primary">
          {offline && <Offline retry={refresh} />}
          <div className="grid metric-grid" aria-label="Dashboard metrics">
            {cards.slice(0, 4).map(([label, value, Icon, color, bg]) => (
              <motion.article
                className="card metric"
                key={label}
                initial={reduceMotion ? false : { opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.18 }}
              >
                <div className="metric-icon" style={{ color, background: bg }}>
                  <Icon size={18} />
                </div>
                <strong>{summary.isLoading || summary.isError || value == null ? '—' : value}</strong>
                <span>{label}</span>
              </motion.article>
            ))}
          </div>
          <section className="ask-panel">
            <h2>
              <Sparkles size={17} style={{ verticalAlign: 'middle', marginRight: 7 }} />
              Ask TANTARA <span style={{ fontWeight: 400, opacity: 0.8 }}>(Arbitration Law)</span>
            </h2>
            <form
              className="ask-form"
              onSubmit={(e) => {
                e.preventDefault();
                void ask();
              }}
            >
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ask about arbitration law, cases, strategy, or a draft…"
                aria-label="Ask an arbitration law question"
              />
              <button disabled={askBusy} aria-label="Submit question">
                <ArrowRight size={18} />
              </button>
            </form>
            <div className="suggestions">
              {[
                'Procedure under Arbitration Act',
                'Recent arbitral awards',
                'Draft statement of claim',
                'Relief options',
              ].map((x) => (
                <button key={x} onClick={() => void ask(x)}>
                  {x}
                </button>
              ))}
            </div>
            <details className="ask-scope">
              <summary>Research scope</summary>
              <div className="form-row">
                <select aria-label="Scope to case" value={scope} onChange={(e) => setScope(e.target.value)}>
                  <option value="">All cases</option>
                  {cases.data?.items?.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.title}
                    </option>
                  ))}
                </select>
                <select
                  aria-label="Jurisdiction"
                  value={jurisdiction}
                  onChange={(e) => setJurisdiction(e.target.value)}
                >
                  <option value="">Any jurisdiction</option>
                  {jurisdictions.data?.items?.map((x: any, i: number) => (
                    <option key={i} value={typeof x === 'string' ? x : x.name}>
                      {typeof x === 'string' ? x : x.name}
                    </option>
                  ))}
                </select>
                <select
                  aria-label="Knowledge collection"
                  value={collection}
                  onChange={(e) => setCollection(e.target.value)}
                  aria-describedby="collection-help"
                >
                  <option value="">All collections</option>
                  {collections.data?.items.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name} ({item.document_count})
                    </option>
                  ))}
                </select>
              </div>
              <small id="collection-help">
                {collections.isError
                  ? 'Collection list unavailable; retry from Documents.'
                  : 'Scope Ask TANTARA to a knowledge collection.'}
              </small>
            </details>
            {answer && (
              <div className="result" style={{ background: '#ffffff18', padding: 12, borderRadius: 8 }}>
                <strong>
                  {answer.status === 'no_evidence'
                    ? 'Insufficient evidence'
                    : answer.status === 'model_unavailable'
                      ? 'Model unavailable'
                      : answer.status === 'embedding_unavailable'
                        ? 'Embeddings unavailable'
                        : 'Answer'}
                </strong>
                <p>{answer.answer}</p>
                {answer.citations?.map((c) => (
                  <Link
                    key={c.citation_ref}
                    href={`/documents/${c.document_id}?page=${c.page_number}`}
                    style={{
                      display: 'block',
                      padding: '8px 0',
                      borderTop: '1px solid #ffffff30',
                      fontSize: 11,
                    }}
                  >
                    “{c.excerpt}” — {c.document_title}, p. {c.page_number}
                  </Link>
                ))}
                {answer.disclaimer && <small>{answer.disclaimer}</small>}
              </div>
            )}
            {askBusy && (
              <p style={{ fontSize: 12 }} role="status">
                Searching your workspace…
              </p>
            )}
          </section>
          <section className="card surface recent-questions-card">
            <h2 className="section-title">Recent questions</h2>
            {sessions.isLoading ? (
              <p className="muted" role="status">
                Loading research history…
              </p>
            ) : sessions.isError ? (
              <p className="muted">Research sessions are unavailable.</p>
            ) : sessions.data?.items?.length ? (
              sessions.data.items.slice(0, 3).map((x) => <p key={x.id}>{x.title}</p>)
            ) : (
              <p className="muted">No previous questions in this workspace.</p>
            )}
          </section>
          <section className="card surface">
            <h2 className="section-title">Recent activity</h2>
            {activity.isLoading ? (
              <p className="muted" role="status">
                Loading activity…
              </p>
            ) : activity.isError ? (
              <p className="muted">Activity is unavailable.</p>
            ) : activity.data?.length ? (
              activity.data.slice(0, 5).map((x: Activity) => (
                <div className="activity-row" key={x.id} data-activity-id={x.id} data-object-id={x.object_id}>
                  <span className="small-icon">
                    <Scale size={16} />
                  </span>
                  <span>
                    {x.title}
                    <small style={{ display: 'block', color: '#64748b', marginTop: 3 }}>
                      {x.actor || 'Workspace'} · {workspaceDateTimeDisplay(x.at)}
                    </small>
                  </span>
                </div>
              ))
            ) : (
              <div className="empty">
                <img src="/brand/empty-state.svg" alt="" />
                Activity will appear here as you work.
              </div>
            )}
          </section>
        </div>
        <aside className="dashboard-aside">
          <section className="matters-slot" data-slot="dashboard-matters">
            <MattersCard />
          </section>
          <section className="card surface">
            <h2 className="section-title">
              Upcoming hearings &amp; deadlines <CalendarDays size={16} color="#4f46e5" />
            </h2>
            {upcoming.isLoading ? (
              <p className="muted" role="status">
                Loading calendar…
              </p>
            ) : upcoming.isError ? (
              <p className="muted">Calendar is unavailable.</p>
            ) : upcoming.data?.length ? (
              <div>
                {upcoming.data.slice(0, 5).map((x: Upcoming) => (
                  <div className="upcoming-row" key={x.id}>
                    <span className="pill">{x.due_in_days === 0 ? 'Today' : `${x.due_in_days}d`}</span>
                    <div>
                      <strong>{x.title}</strong>
                      <small style={{ display: 'block', color: '#64748b', marginTop: 3 }}>
                        {calendarEventLabel(x)}
                        {x.case_title ? ` · ${x.case_title}` : ''}
                      </small>
                    </div>
                    <span className="right muted">
                      {new Date(x.at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty">
                <img src="/brand/empty-state.svg" alt="" />
                <div>No upcoming hearings or deadlines.</div>
              </div>
            )}
          </section>
        </aside>
      </div>
      <section className="card secondary-summary" aria-label="Other dashboard totals">
        {cards.slice(4).map(([label, value, Icon, color]) => (
          <div className="secondary-summary-item" key={label}>
            <Icon size={16} color={color} />
            <strong>{summary.isLoading || summary.isError || value == null ? '—' : value}</strong>
            <span>{label}</span>
          </div>
        ))}
      </section>
    </div>
  );
}
