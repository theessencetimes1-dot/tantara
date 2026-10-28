'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import {
  ArrowRight,
  Bookmark,
  BookOpen,
  Check,
  ChevronDown,
  Copy,
  FileText,
  FolderOpen,
  LoaderCircle,
  Plus,
  RefreshCw,
  Scale,
  Search,
  Sparkles,
  X,
} from 'lucide-react';
import {
  researchApi,
  type ResearchAnswer,
  type ResearchSession,
  type ResearchSource,
} from '@/features/research/api';
import {
  answerStatusLabel,
  citationAccessibleLabel,
  citationLink,
  groupSources,
  normalizeDocumentTitle,
} from '@/features/research/presentation';
import './research.css';

type Choice = { id?: string; name?: string } | string;
const EMPTY_SOURCES: ResearchSource[] = [];
const ACTIVE_SESSION_KEY = 'tantara_research_active_session';
const scoreOf = (s: ResearchSource) => s.retrieval_score ?? s.retreival_score ?? s.score;
const formatHistoryDate = (value?: string) => {
  if (!value || Number.isNaN(new Date(value).getTime())) return 'Date unavailable';
  return new Date(value).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
};

function AnswerText({ text, citations }: { text: string; citations: ResearchSource[] }) {
  const chunks = text.split(
    /(\[[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\](?:\s+p\.\s*\d+)?|\[\d+\])/gi,
  );
  const hasInlineRefs = chunks.some((chunk) => /^\[(?:[0-9a-f]{8}-|\d+\])/i.test(chunk));
  return (
    <div className="answer-text">
      <p className="answer-sentence">
        {chunks.map((chunk, index) => {
          const ref = chunk.match(/^\[([0-9a-f-]{36}|\d+)\](?:\s+p\.\s*(\d+))?$/i);
          if (!ref) return chunk;
          const citationIndex = /^\d+$/.test(ref[1])
            ? Number(ref[1]) - 1
            : citations.findIndex(
                (source) =>
                  source.chunk_id === ref[1] || source.citation_ref?.replace(/[\[\]]/g, '') === ref[1],
              );
          const source = citations[citationIndex];
          return source ? (
            <CitationAnchor
              key={`${source.chunk_id}-${index}`}
              source={source}
              className="answer-citation"
              display={citationAccessibleLabel(source)}
            />
          ) : null;
        })}
      </p>
      {citations.length > 0 && !hasInlineRefs && (
        <div className="answer-citations" aria-label="Sources for this answer">
          <span>Citations returned with this answer</span>
          {citations.map((source) => (
            <CitationAnchor
              key={`${source.document_id}-${source.page_number}-${source.chunk_id}`}
              source={source}
              className="answer-citation"
              display={citationAccessibleLabel(source)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function CitationAnchor({
  source,
  className,
  display,
}: {
  source: ResearchSource;
  className: string;
  display?: string;
}) {
  const citation = citationLink(source);
  return (
    <a
      className={className}
      href={citation.href}
      aria-label={`Open ${citationAccessibleLabel(source)}`}
      data-chunk-id={citation.chunkId}
    >
      {display ?? citation.label}
    </a>
  );
}

function ConflictNotices({
  conflicts,
  sources,
}: {
  conflicts: NonNullable<ResearchAnswer['conflicts']>;
  sources: ResearchSource[];
}) {
  if (conflicts.length === 0) return null;
  return (
    <div className="answer-conflicts" role="alert">
      {conflicts.map((conflict) => {
        const source = sources.find((item) => item.chunk_id === conflict.excerpt_chunk_id);
        return (
          <p key={`${conflict.field}-${conflict.excerpt_chunk_id}`}>
            Conflict for {conflict.field}: the case record says “{conflict.case_value}”; the excerpt on page{' '}
            {conflict.page_number} says {source ? `“${source.excerpt}”` : 'its value is unavailable'}.
            {source && <CitationAnchor source={source} className="page-chip" />}
          </p>
        );
      })}
    </div>
  );
}

function CaseRecordAnswer({ answer }: { answer: ResearchAnswer }) {
  const fields = answer.context_fields ?? [];
  return (
    <div className="case-record-answer">
      {answer.answer && <p>{answer.answer}</p>}
      {fields.map((field) => (
        <p key={field.field}>
          <strong>{field.field.replaceAll('_', ' ')}:</strong> {field.value}{' '}
          <small>from the case record</small>
        </p>
      ))}
      {fields.length === 0 && answer.answer && <small>From the case record</small>}
    </div>
  );
}

function PageLinks({ sources }: { sources: ResearchSource[] }) {
  const seen = new Set<string>();
  return (
    <span className="page-links">
      {sources.map((source) => {
        const key = `${source.document_id}-${source.page_number}-${source.chunk_id}`;
        if (seen.has(key)) return null;
        seen.add(key);
        return <CitationAnchor className="page-chip" key={key} source={source} />;
      })}
    </span>
  );
}

function citedSources(text: string | undefined, sources: ResearchSource[]): ResearchSource[] {
  if (!text) return [];
  return sources.filter((source, index) => {
    const reference = source.citation_ref?.trim();
    if (reference && text.includes(reference)) return true;
    if (text.includes(source.chunk_id)) return true;
    return new RegExp(`\\[${index + 1}\\]`).test(text);
  });
}

function SourceGroups({ groups }: { groups: ReturnType<typeof groupSources> }) {
  return groups.map((group) => {
    const seenQuotes = new Map<string, number>();
    return (
      <details className="source-item" key={group.documentId} open>
        <summary>
          <strong>{group.title}</strong>
          <span>
            {group.pages.length} {group.pages.length === 1 ? 'page' : 'pages'}
          </span>
        </summary>
        <PageLinks sources={group.pages.map((page) => page.sources[0]).filter(Boolean)} />
        {group.pages.map((page) => {
          const best = [...page.sources].sort(
            (a, b) => (scoreOf(b) ?? -Infinity) - (scoreOf(a) ?? -Infinity),
          )[0];
          if (!best) return null;
          const repeatedOn = best.excerpt ? seenQuotes.get(best.excerpt) : undefined;
          if (best.excerpt && repeatedOn == null) seenQuotes.set(best.excerpt, page.page);
          return (
            <div className="source-excerpt" key={page.page}>
              <p>
                <strong>Page {page.page}</strong>{' '}
                {best.excerpt
                  ? repeatedOn == null
                    ? `“${best.excerpt}”`
                    : `Same excerpt as page ${repeatedOn}.`
                  : 'No excerpt was returned for this page.'}
              </p>
              <CitationAnchor
                source={best}
                className="page-chip"
                display={`Open ${citationAccessibleLabel(best)}`}
              />
              <div className="source-relevance">
                Rank {page.rank} · Relevance <b>{page.bestScore == null ? '—' : page.bestScore.toFixed(3)}</b>{' '}
                · relative to this query
              </div>
            </div>
          );
        })}
      </details>
    );
  });
}

async function hydrateSession(session: ResearchSession): Promise<ResearchSession> {
  const citedIds = new Set(
    session.messages?.flatMap(
      (message) => message.citations?.map((citation) => citation.document_id) ?? [],
    ) ?? [],
  );
  const documents = new Map<string, { title?: string; filename?: string }>();
  await Promise.all(
    [...citedIds].map(async (id) => {
      try {
        documents.set(id, await researchApi.document(id));
      } catch {
        // Keep the saved citation and page link even if document metadata is temporarily unavailable.
      }
    }),
  );
  return {
    ...session,
    messages: session.messages?.map((message) => ({
      ...message,
      raw_status: message.raw_status ?? message.status,
      status: message.status === 'insufficient_evidence' ? 'no_evidence' : message.status,
      citations: message.citations?.map((citation) => {
        const document = documents.get(citation.document_id);
        return {
          ...citation,
          document_title: document?.title ?? document?.filename ?? 'Untitled document',
          retrieval_score: citation.retrieval_score ?? citation.retreival_score,
        };
      }),
    })),
  };
}

export default function ResearchPage() {
  const [sessions, setSessions] = useState<ResearchSession[]>([]);
  const [saved, setSaved] = useState<Array<{ id: string; item_id: string; item_type: string }>>([]);
  const [cases, setCases] = useState<Array<{ id: string; title: string; jurisdiction?: string }>>([]);
  const [documents, setDocuments] = useState<
    Array<{ id: string; case_id?: string; jurisdiction?: string; collection_id?: string }>
  >([]);
  const [collections, setCollections] = useState<Array<{ id: string; name: string }>>([]);
  const [collectionsUnavailable, setCollectionsUnavailable] = useState(false);
  const [jurisdictions, setJurisdictions] = useState<Choice[]>([]);
  const [selected, setSelected] = useState<ResearchSession | null>(null);
  const [caseFilter, setCaseFilter] = useState('');
  const [collection, setCollection] = useState('');
  const [jurisdiction, setJurisdiction] = useState('');
  const [draft, setDraft] = useState('');
  const [answer, setAnswer] = useState<ResearchAnswer | null>(null);
  const [lexical, setLexical] = useState<ResearchSource[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [copiedTurnId, setCopiedTurnId] = useState('');
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set());
  const abortRef = useRef<AbortController | null>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);

  const refreshHistory = useCallback(async () => {
    const [history, library, caseData, documentData, collectionData] = await Promise.allSettled([
      researchApi.sessions(),
      researchApi.saved(),
      researchApi.cases(),
      researchApi.documents(),
      researchApi.collections(),
    ]);
    if (history.status === 'fulfilled') setSessions(history.value.items ?? []);
    if (library.status === 'fulfilled') {
      setSaved(library.value.items ?? []);
      setSavedIds(new Set(library.value.items?.map((x) => x.item_id) ?? []));
    }
    if (caseData.status === 'fulfilled') setCases(caseData.value.items ?? []);
    if (documentData.status === 'fulfilled') {
      const items = documentData.value.items ?? [];
      setDocuments(items);
      const jurisdictionNames = [
        ...new Set(items.map((document) => document.jurisdiction).filter(Boolean) as string[]),
      ];
      setJurisdictions(jurisdictionNames);
    }
    if (collectionData.status === 'fulfilled') {
      setCollections(collectionData.value.items ?? []);
      setCollectionsUnavailable(false);
    } else {
      setCollections([]);
      setCollectionsUnavailable(true);
    }
    if (documentData.status === 'fulfilled') {
      const items = documentData.value.items ?? [];
      const jurisdictionNames = [
        ...new Set(items.map((document) => document.jurisdiction).filter(Boolean) as string[]),
      ];
      setJurisdictions(jurisdictionNames);
    }
    if (history.status === 'rejected')
      setError('Research history is unavailable. Check your connection and retry.');
  }, []);

  useEffect(() => {
    void refreshHistory();
    const params = new URLSearchParams(window.location.search);
    const followUp = params.get('question');
    const caseId = params.get('case_id');
    if (followUp) setDraft(followUp);
    if (caseId) setCaseFilter(caseId);
    const activeSessionId = localStorage.getItem(ACTIVE_SESSION_KEY);
    if (activeSessionId) {
      void researchApi
        .session(activeSessionId)
        .then(hydrateSession)
        .then((session) => {
          setSelected(session);
          setCaseFilter(session.case_id ?? '');
          setCollection(session.collection_id ?? '');
          setJurisdiction(session.jurisdiction ?? '');
        })
        .catch(() => localStorage.removeItem(ACTIVE_SESSION_KEY));
    }
    return () => abortRef.current?.abort();
  }, [refreshHistory]);

  const loadSession = async (session: ResearchSession) => {
    setAnswer(null);
    setLexical([]);
    setError('');
    setCaseFilter(session.case_id ?? '');
    setCollection(session.collection_id ?? '');
    setJurisdiction(session.jurisdiction ?? '');
    localStorage.setItem(ACTIVE_SESSION_KEY, session.id);
    try {
      setSelected(await hydrateSession(await researchApi.session(session.id)));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load this research session.');
    }
  };

  const sources = useMemo(() => answer?.sources ?? answer?.citations ?? [], [answer]);
  const ask = async (question = draft) => {
    if (!question.trim() || busy) return;
    setDraft(question);
    setError('');
    setAnswer(null);
    setLexical([]);
    setBusy(true);
    const controller = new AbortController();
    abortRef.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 45000);
    try {
      const result = await researchApi.ask(
        {
          question: question.trim(),
          session_id: selected && (!caseFilter || selected.case_id === caseFilter) ? selected.id : undefined,
          case_id: caseFilter || undefined,
          collection_id: collection || undefined,
          jurisdiction: jurisdiction || undefined,
        },
        controller.signal,
      );
      setAnswer(result);
      if (result.research_session_id) {
        localStorage.setItem(ACTIVE_SESSION_KEY, result.research_session_id);
        try {
          setSelected(await hydrateSession(await researchApi.session(result.research_session_id)));
        } catch {
          /* answer remains visible */
        }
      }
      if (result.status === 'model_unavailable') {
        try {
          const hits = await researchApi.lexical(question.trim(), controller.signal);
          setLexical(
            (hits.items ?? []).map((hit) => ({
              document_id: hit.document_id,
              document_title: hit.document_title,
              chunk_id: hit.chunk_id,
              page_number: hit.page_number,
              excerpt: hit.snippet,
              retrieval_score: hit.score,
            })),
          );
        } catch {
          setLexical([]);
        }
      }
      void refreshHistory();
    } catch (e) {
      if (controller.signal.aborted) setError('Research was cancelled or timed out. Retry when ready.');
      else setError('Research could not complete. Check your connection and retry.');
    } finally {
      window.clearTimeout(timeout);
      setBusy(false);
      abortRef.current = null;
    }
  };

  const startNew = async () => {
    abortRef.current?.abort();
    localStorage.removeItem(ACTIVE_SESSION_KEY);
    setSelected(null);
    setAnswer(null);
    setLexical([]);
    setDraft('');
    setError('');
    textarea.current?.focus();
  };
  const save = async (id?: string) => {
    if (!id) {
      setError('The API did not return a message id to save.');
      return;
    }
    try {
      await researchApi.save(id);
      setSavedIds((old) => new Set(old).add(id));
      void refreshHistory();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save this answer.');
    }
  };
  const copyAnswer = async (id: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedTurnId(id);
      window.setTimeout(() => setCopiedTurnId((current) => (current === id ? '' : current)), 1800);
    } catch {
      setError('Copy is unavailable in this browser. Select the answer text to copy it.');
    }
  };

  const activeMessages = selected?.messages ?? [];
  const latestAssistant = [...activeMessages].reverse().find((message) => message.role === 'assistant');
  const restoredSources = latestAssistant?.citations ?? EMPTY_SOURCES;
  const answerHasInsufficientEvidence = answer?.status === 'no_evidence';
  const selectedSources = useMemo(
    () =>
      answer
        ? answer.status === 'model_unavailable'
          ? lexical
          : answerHasInsufficientEvidence
            ? EMPTY_SOURCES
            : sources
        : restoredSources,
    [answer, answerHasInsufficientEvidence, lexical, restoredSources, sources],
  );
  const groupedSources = useMemo(() => groupSources(selectedSources), [selectedSources]);
  const distinctSourceCount = new Set(selectedSources.map((source) => source.document_id)).size;
  const corpusCount = answer || latestAssistant ? distinctSourceCount : null;
  const answerTextForEvidence = answer?.answer ?? latestAssistant?.content;
  const supportedChunkIds = answer?.supports?.map((support) => support.chunk_id);
  const sourcesForAnswer = answer?.supports
    ? selectedSources.filter((source) => supportedChunkIds?.includes(source.chunk_id))
    : citedSources(answerTextForEvidence, selectedSources);
  const otherRetrievedSources = selectedSources.filter(
    (source) => !sourcesForAnswer.some((supported) => supported.chunk_id === source.chunk_id),
  );
  const supportedGroups = useMemo(() => groupSources(sourcesForAnswer), [sourcesForAnswer]);
  const otherGroups = useMemo(() => groupSources(otherRetrievedSources), [otherRetrievedSources]);
  const modelId = answer?.model?.model;
  const generationKind = answer?.generation_kind ?? answer?.answer_kind;
  const hasModelProvenance = generationKind === 'model_generated' && typeof modelId === 'string';
  const answerIsInsufficient =
    answerHasInsufficientEvidence ||
    answerHasInsufficientEvidence ||
    ((answer?.status === 'ok' || answer?.status === 'answered') &&
      /evidence is insufficient/i.test(answer.answer ?? ''));
  const answerHasLiveStateDetail =
    answer?.raw_status === 'insufficient_evidence' ||
    answer?.raw_status === 'model_unavailable' ||
    answer?.answer_basis === 'insufficient_evidence';
  const answerAlreadyInHistory =
    !answerHasLiveStateDetail &&
    !!answer?.message_id &&
    activeMessages.some((message) => message.id === answer.message_id);
  const hiddenResolvedFailureIds = new Set<string>();
  for (let i = 0; i < activeMessages.length; i += 1) {
    const failed = activeMessages[i];
    if (failed.role !== 'assistant' || failed.status !== 'model_unavailable') continue;
    const failedQuestion = [...activeMessages.slice(0, i)]
      .reverse()
      .find((message) => message.role === 'user');
    const retryQuestion = activeMessages[i + 1];
    const retryAnswer = activeMessages[i + 2];
    if (
      failedQuestion &&
      retryQuestion?.role === 'user' &&
      retryQuestion.content === failedQuestion.content &&
      retryAnswer?.role === 'assistant' &&
      !['model_unavailable', 'no_evidence', 'error'].includes(retryAnswer.status ?? '')
    ) {
      hiddenResolvedFailureIds.add(failed.id);
      hiddenResolvedFailureIds.add(retryQuestion.id);
    }
  }
  const visibleMessages = activeMessages.filter(
    (message) =>
      !hiddenResolvedFailureIds.has(message.id) &&
      !(answerHasLiveStateDetail && message.id === answer?.message_id),
  );
  const filteredSessions = sessions.filter(
    (s) =>
      (!caseFilter || s.case_id === caseFilter) &&
      (!collection || s.collection_id === collection) &&
      (!jurisdiction ||
        s.jurisdiction === jurisdiction ||
        cases.some((caseItem) => caseItem.id === s.case_id && caseItem.jurisdiction === jurisdiction) ||
        documents.some(
          (document) => document.case_id === s.case_id && document.jurisdiction === jurisdiction,
        )),
  );
  useEffect(() => {
    if (!selected?.case_id || selected.jurisdiction) return;
    const sessionJurisdiction = documents.find(
      (document) => document.case_id === selected.case_id,
    )?.jurisdiction;
    if (sessionJurisdiction) setJurisdiction(sessionJurisdiction);
  }, [documents, selected?.case_id, selected?.id, selected?.jurisdiction]);
  const openSaved = async (item: { item_id: string; item_type: string }) => {
    if (item.item_type === 'research_item') {
      const session = sessions.find((candidate) => candidate.id === item.item_id);
      if (session) await loadSession(session);
      return;
    }
    for (const session of sessions) {
      try {
        const full = await researchApi.session(session.id);
        if (full.messages?.some((message) => message.id === item.item_id)) {
          setSelected(await hydrateSession(full));
          localStorage.setItem(ACTIVE_SESSION_KEY, full.id);
          setCaseFilter(full.case_id ?? '');
          setCollection(full.collection_id ?? '');
          setJurisdiction(full.jurisdiction ?? '');
          setAnswer(null);
          setLexical([]);
          return;
        }
      } catch {
        // Keep checking the remaining sessions; the saved item stays in the library.
      }
    }
    setError('The saved answer could not be matched to an available research session.');
  };

  return (
    <main className="research-page">
      <div className="research-heading">
        <div>
          <div className="research-eyebrow">
            <Scale size={15} /> TANTARA / RESEARCH DESK
          </div>
          <h1>Research Desk</h1>
          <p>Grounded legal research across your workspace library.</p>
        </div>
        <button className="research-new" onClick={startNew}>
          <Plus size={17} /> New research
        </button>
      </div>
      <div className="research-filters">
        <label>
          <span>Case</span>
          <span className="sr-only" id="research-case-filter-label">
            Case filter
          </span>
          <select aria-label="Case filter" value={caseFilter} onChange={(e) => setCaseFilter(e.target.value)}>
            <option value="">All cases</option>
            {cases.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
              </option>
            ))}
          </select>
          <ChevronDown size={14} />
        </label>
        <label
          className="collection-filter"
          title={collectionsUnavailable ? 'Collection metadata is unavailable from this backend.' : ''}
        >
          <span>Collection</span>
          <select value={collection} onChange={(e) => setCollection(e.target.value)}>
            <option value="">
              {collectionsUnavailable ? 'Could not load collections' : 'All collections'}
            </option>
            {collections.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <ChevronDown size={14} />
        </label>
        <label>
          <span>Jurisdiction</span>
          <select value={jurisdiction} onChange={(e) => setJurisdiction(e.target.value)}>
            <option value="">All jurisdictions</option>
            {jurisdictions.map((j) => {
              const name = typeof j === 'string' ? j : (j.name ?? j.id ?? '');
              return (
                <option key={name} value={typeof j === 'string' ? j : (j.id ?? name)}>
                  {name}
                </option>
              );
            })}
          </select>
          <ChevronDown size={14} />
        </label>
        <div className="scope-note">
          <Search size={14} /> Scope applies to new questions
        </div>
      </div>
      <div className="research-grid">
        <aside className="research-left">
          <section className="research-card history-card">
            <header>
              <h2>
                <BookOpen size={16} /> Research history
              </h2>
              <button aria-label="Refresh history" onClick={() => void refreshHistory()}>
                <RefreshCw size={14} />
              </button>
            </header>
            {filteredSessions.length ? (
              <div className="history-list">
                {filteredSessions.map((s) => (
                  <button
                    className={`history-item ${selected?.id === s.id ? 'selected' : ''}`}
                    key={s.id}
                    onClick={() => void loadSession(s)}
                  >
                    <span>{s.title}</span>
                    <small>{formatHistoryDate(s.updated_at ?? s.created_at)}</small>
                  </button>
                ))}
              </div>
            ) : (
              <div className="research-empty">
                <FolderOpen size={21} />
                <strong>{sessions.length ? 'No sessions match this scope' : 'No research history'}</strong>
                <span>
                  {sessions.length
                    ? 'Clear or change a filter to see more sessions.'
                    : 'Your saved sessions will appear here.'}
                </span>
                <button onClick={startNew}>
                  Start a research question <ArrowRight size={13} />
                </button>
              </div>
            )}
          </section>
          <section className="research-card saved-card">
            <header>
              <h2>
                <Bookmark size={16} /> Saved searches
              </h2>
              <span>{saved.length}</span>
            </header>
            {saved.length ? (
              saved.slice(0, 5).map((item) => (
                <button className="saved-item" key={item.id} onClick={() => void openSaved(item)}>
                  {item.item_type === 'message' ? 'Saved answer' : 'Saved research'}
                </button>
              ))
            ) : (
              <div className="saved-empty">Save an answer to keep it in your research library.</div>
            )}
            <Link href="/research/documents">
              Browse library <ArrowRight size={13} />
            </Link>
          </section>
        </aside>
        <section className="research-center">
          <div className="research-card conversation-card">
            <header className="conversation-head">
              <div className="ai-mark">
                <Sparkles size={16} />
              </div>
              <div>
                <h2>
                  Ask TANTARA <span>Legal research assistant</span>
                </h2>
                <p>Answers are grounded in retrieved workspace documents.</p>
              </div>
              <span className="secure-tag">
                <Check size={12} /> Source aware
              </span>
            </header>
            <div className="conversation-body" aria-live="polite">
              {visibleMessages.length
                ? visibleMessages.map((m) => {
                    const messageIndex = activeMessages.indexOf(m);
                    const messageStatus = answer?.message_id === m.id ? answer.status : m.status;
                    const messageContent =
                      answer?.message_id === m.id ? (answer.answer ?? m.content) : m.content;
                    return (
                      <article className={`turn ${m.role}`} key={m.id}>
                        <div className="turn-label">
                          {m.role === 'user' ? 'You' : 'TANTARA'}
                          {m.role === 'assistant' && messageStatus && (
                            <span className="status-chip" data-status={messageStatus}>
                              {answerStatusLabel(
                                messageStatus,
                                answer?.message_id === m.id ? answer.answer_kind : undefined,
                                answer?.message_id === m.id ? answer.generation_kind : undefined,
                              )}
                            </span>
                          )}
                        </div>
                        {m.role === 'assistant' && messageStatus === 'model_unavailable' ? (
                          <div className="state-callout unavailable">
                            <strong>Model unavailable</strong>
                            <p>
                              The model is unreachable. Retry to try the answer again; retrieved documents
                              remain available.
                            </p>
                            <button
                              onClick={() =>
                                void ask(
                                  activeMessages
                                    .slice(0, messageIndex)
                                    .reverse()
                                    .find((message) => message.role === 'user')?.content ?? draft,
                                )
                              }
                            >
                              <RefreshCw size={14} /> Retry
                            </button>
                          </div>
                        ) : m.role === 'assistant' && messageStatus === 'no_evidence' ? (
                          <div className="state-callout no-evidence">
                            <strong>No supporting excerpts</strong>
                            {messageContent && <AnswerText text={messageContent} citations={[]} />}
                            <p>
                              No supporting documents were found. Upload a document, widen the research scope,
                              or rephrase your question.
                            </p>
                            <Link href="/research/documents">Upload a document</Link>
                          </div>
                        ) : m.role === 'assistant' && messageStatus === 'embedding_unavailable' ? (
                          <div className="state-callout lexical-state">
                            <strong>Embeddings unavailable</strong>
                            <p>Only lexical results were available; no grounded answer is shown.</p>
                          </div>
                        ) : m.role === 'assistant' ? (
                          <AnswerText
                            text={messageContent}
                            citations={answer?.message_id === m.id ? sources : (m.citations ?? [])}
                          />
                        ) : (
                          <p>{m.content}</p>
                        )}
                        {m.role === 'assistant' && answer?.message_id === m.id && hasModelProvenance && (
                          <small className="answer-provenance" data-generation-kind={generationKind}>
                            Model: {String(modelId)} · {String(generationKind)}
                          </small>
                        )}
                        {m.role === 'assistant' &&
                          !['model_unavailable', 'no_evidence', 'embedding_unavailable', 'error'].includes(
                            m.status ?? '',
                          ) && (
                            <div className="turn-actions">
                              <button onClick={() => void copyAnswer(m.id, m.content)}>
                                <Copy size={13} /> {copiedTurnId === m.id ? 'Copied' : 'Copy'}
                              </button>
                              <button onClick={() => void save(m.id)}>
                                <Bookmark size={13} /> Save
                              </button>
                            </div>
                          )}
                      </article>
                    );
                  })
                : !answer && (
                    <div className="welcome-state">
                      <div className="welcome-spark">
                        <Sparkles size={22} />
                      </div>
                      <h3>What are you researching?</h3>
                      <p>Ask about a legal principle, a clause, or an issue in your documents.</p>
                      <div className="suggestion-row">
                        {['What is the seat of arbitration?', 'Find documents about seat of arbitration'].map(
                          (q) => (
                            <button key={q} onClick={() => void ask(q)}>
                              {q}
                              <ArrowRight size={13} />
                            </button>
                          ),
                        )}
                      </div>
                    </div>
                  )}
              {answer && !answerAlreadyInHistory && (
                <article className="turn assistant">
                  <div className="turn-label">
                    TANTARA{' '}
                    <span className="status-chip" data-status={answer.status}>
                      {answer.answer_basis === 'case_record'
                        ? 'From the case record'
                        : answerStatusLabel(answer.status, answer.answer_kind, answer.generation_kind)}
                    </span>
                  </div>
                  {answer.status === 'model_unavailable' ? (
                    <div className="state-callout unavailable">
                      <strong>Model unavailable</strong>
                      <p>
                        The model is unreachable. Retry to try the answer again; retrieved documents remain
                        available.
                      </p>
                      <button onClick={() => void ask(draft)}>
                        <RefreshCw size={14} /> Retry
                      </button>
                    </div>
                  ) : answerIsInsufficient ? (
                    <div className="state-callout no-evidence model-insufficient">
                      <strong>No supporting excerpts</strong>
                      {answer.answer && <AnswerText text={answer.answer} citations={[]} />}
                      <p>
                        {answerHasInsufficientEvidence
                          ? 'No indexed excerpt directly answers this question. Upload a document, widen the scope, or rephrase the question.'
                          : 'The available excerpts do not support a conclusion. Review them below before deciding how to proceed.'}
                      </p>
                      {answer.status === 'no_evidence' && (
                        <Link href="/research/documents">Upload a document</Link>
                      )}
                    </div>
                  ) : answer.answer_basis === 'case_record' ? (
                    <>
                      <CaseRecordAnswer answer={answer} />
                      <ConflictNotices conflicts={answer.conflicts ?? []} sources={sources} />
                    </>
                  ) : answer.status === 'embedding_unavailable' ? (
                    <div className="state-callout lexical-state">
                      <strong>Embeddings unavailable</strong>
                      <p>
                        Only lexical results were available. Review the retrieved documents below; no grounded
                        answer is available.
                      </p>
                    </div>
                  ) : answer.status === 'error' ? (
                    <div className="state-callout unavailable">
                      <strong>Research request failed</strong>
                      <button onClick={() => void ask(draft)}>
                        <RefreshCw size={14} /> Retry
                      </button>
                    </div>
                  ) : sources.length === 0 || !answer.answer?.trim() ? (
                    <div className="state-callout lexical-state">
                      <strong>No grounded answer text returned</strong>
                      <p>
                        The response had no answer text. Review the retrieved documents below or broaden your
                        search.
                      </p>
                    </div>
                  ) : (
                    <>
                      <AnswerText text={answer.answer || ''} citations={sources} />
                      <ConflictNotices conflicts={answer.conflicts ?? []} sources={sources} />
                      {hasModelProvenance && (
                        <small className="answer-provenance" data-generation-kind={generationKind}>
                          Model: {String(modelId)} · {String(generationKind)}
                        </small>
                      )}
                      {answer.disclaimer && hasModelProvenance && answer.answer_basis !== 'case_record' && (
                        <small className="disclaimer">AI-generated — review before relying on it.</small>
                      )}
                      <div className="turn-actions">
                        <button
                          onClick={() =>
                            answer.message_id && void copyAnswer(answer.message_id, answer.answer ?? '')
                          }
                        >
                          <Copy size={13} /> {copiedTurnId === answer.message_id ? 'Copied' : 'Copy'}
                        </button>
                        <button onClick={() => void save(answer.message_id)}>
                          <Bookmark size={13} />
                          {answer.message_id && savedIds.has(answer.message_id)
                            ? ' Saved'
                            : ' Save to library'}
                        </button>
                        <button onClick={() => void ask(draft)}>
                          <RefreshCw size={13} /> Regenerate
                        </button>
                      </div>
                      {answer.follow_ups?.length ? (
                        <div className="followups">
                          <span>Explore next</span>
                          {answer.follow_ups.map((q) => (
                            <button key={q} onClick={() => void ask(q)}>
                              {q}
                              <ArrowRight size={13} />
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </>
                  )}
                </article>
              )}
              {busy && (
                <div className="thinking" role="status">
                  <LoaderCircle size={17} className="spin" />
                  <span>Searching your library and preparing a grounded response…</span>
                  <button onClick={() => abortRef.current?.abort()}>
                    <X size={14} /> Cancel
                  </button>
                </div>
              )}
              {error && (
                <div className="research-error" role="alert">
                  <span>{error}</span>
                  <button onClick={() => void ask(draft)}>
                    <RefreshCw size={13} /> Retry
                  </button>
                </div>
              )}
            </div>
            <form
              className="composer"
              onSubmit={(e) => {
                e.preventDefault();
                void ask();
              }}
            >
              <textarea
                ref={textarea}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    void ask();
                  }
                }}
                placeholder="Ask a legal research question…"
                aria-label="Research question"
                rows={2}
              />
              <div className="composer-bottom">
                <span>Enter to send · Shift + Enter for a new line</span>
                <button type="submit" disabled={busy || draft.trim().length < 3}>
                  <ArrowRight size={17} />
                  <span>Ask</span>
                </button>
              </div>
            </form>
          </div>
        </section>
        <aside className="research-right">
          <section className="research-card sources-card">
            <header>
              <div>
                <h2>
                  <FileText size={16} /> Retrieved sources
                </h2>
                <p>
                  {corpusCount != null && (
                    <>
                      {corpusCount} {corpusCount === 1 ? 'document' : 'documents'} ·{' '}
                    </>
                  )}
                  {answer && ['ok', 'answered'].includes(answer.status)
                    ? answerIsInsufficient
                      ? 'Retrieved evidence · no conclusion generated'
                      : sourcesForAnswer.length
                        ? 'Answer-linked excerpts and other retrieved material'
                        : 'Retrieved excerpts · answer links unavailable'
                    : answer?.status === 'model_unavailable'
                      ? 'Lexical results · documents only'
                      : 'Available evidence'}
                </p>
              </div>
              {corpusCount != null && <span className="source-count">{corpusCount}</span>}
            </header>
            {answerHasInsufficientEvidence && (
              <div className="source-note">No supporting documents found in this workspace.</div>
            )}
            {selectedSources.length ? (
              <div className="source-list">
                {sourcesForAnswer.length > 0 && (
                  <section className="source-group" aria-label="Sources for this answer">
                    <h3>Sources for this answer</h3>
                    <SourceGroups groups={supportedGroups} />
                  </section>
                )}
                {otherRetrievedSources.length > 0 && (
                  <section className="source-group" aria-label="Other retrieved material">
                    <h3>Other retrieved material</h3>
                    {['ok', 'answered'].includes(answer?.status ?? '') && (
                      <p className="source-reason">
                        The API did not identify these excerpts as support for the answer.
                      </p>
                    )}
                    <SourceGroups groups={answer ? otherGroups : groupedSources} />
                  </section>
                )}
              </div>
            ) : (
              !answerHasInsufficientEvidence && (
                <div className="sources-empty">
                  <Search size={21} />
                  <strong>Sources appear here</strong>
                  <span>Ask a question to retrieve relevant documents and excerpts.</span>
                </div>
              )
            )}
            <div className="source-footnote">
              Citation links request the referenced page in the document viewer.
            </div>
          </section>
        </aside>
      </div>
    </main>
  );
}
