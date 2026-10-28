'use client';

import { workspaceDateTimeDisplay } from '@/lib/datetime';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { ArrowUpRight, Check, ClipboardList, Save, Sparkles } from 'lucide-react';
import {
  strategyApi,
  strategyTabs,
  type StrategyCase,
  type StrategyCitation,
  type StrategyData,
  type StrategyTab,
  type StrategyWrite,
} from './api';
import './strategy.css';

type Entry = { text: string; citations: StrategyCitation[] };
const fields: Record<StrategyTab, keyof StrategyWrite> = {
  'Case Theory': 'case_theory',
  'Key Issues': 'key_issues',
  'Legal Arguments': 'legal_arguments',
  'Anticipated Counterarguments': 'counterarguments',
  'Evidence Gaps': 'evidence_gaps',
  'Strategy Plan': 'strategy_plan',
};

export function StrategyPanel({ caseId: routeCaseId }: { caseId?: string }) {
  const tabId = useId();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [cases, setCases] = useState<StrategyCase[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState(routeCaseId || params.get('case_id') || '');
  const [caseInfo, setCaseInfo] = useState<StrategyCase>();
  const [data, setData] = useState<StrategyData>();
  const [loadingCase, setLoadingCase] = useState(Boolean(routeCaseId || params.get('case_id')));
  const loadSequence = useRef(0);
  const [aiReachable, setAiReachable] = useState<boolean>();
  const [tab, setTab] = useState<StrategyTab>(
    strategyTabs.find((item) => item === params.get('tab')) ?? strategyTabs[0],
  );
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [taskTitle, setTaskTitle] = useState('');
  const [error, setError] = useState('');
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [savedNotice, setSavedNotice] = useState('');
  const requestedCaseId = routeCaseId || params.get('case_id') || '';

  useEffect(() => {
    strategyApi
      .cases()
      .then((result) => {
        setCases(result.items);
        if (!requestedCaseId && result.items[0]) setSelectedCaseId(result.items[0].id);
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Cases are unavailable.'));
  }, [requestedCaseId]);

  const loadCase = useCallback(async (id: string) => {
    if (!id) return;
    const sequence = ++loadSequence.current;
    setLoadingCase(true);
    setError('');
    setData(undefined);
    try {
      const [overview, strategy] = await Promise.all([strategyApi.case(id), strategyApi.get(id)]);
      setCaseInfo(overview);
      setData(strategy);
      setSavedAt(strategy.updated_at);
      setDirty(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Strategy data could not be loaded.');
    } finally {
      if (sequence === loadSequence.current) setLoadingCase(false);
    }
    try {
      const settings = await strategyApi.aiSettings();
      setAiReachable(settings.runtime_status?.reachable);
    } catch {
      setAiReachable(undefined);
    }
  }, []);

  useEffect(() => {
    void loadCase(selectedCaseId);
  }, [selectedCaseId, loadCase]);
  useEffect(() => {
    const next = strategyTabs.find((item) => item === params.get('tab'));
    if (next) setTab(next);
  }, [params]);
  useEffect(() => {
    if (!dirty) return;
    const guard = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, [dirty]);

  const chooseCase = (nextId: string) => {
    if (!nextId || nextId === selectedCaseId) return;
    if (dirty && !window.confirm('Discard unsaved strategy notes and change case?')) return;
    setSelectedCaseId(nextId);
    setTab(strategyTabs[0]);
    const query = new URLSearchParams();
    query.set('case_id', nextId);
    query.set('tab', strategyTabs[0]);
    if (pathname.startsWith('/cases/'))
      router.push(`/cases/${nextId}/strategy?tab=${encodeURIComponent(strategyTabs[0])}`);
    else router.replace(`/strategy?${query}`);
  };

  const selectTab = (next: StrategyTab) => {
    setTab(next);
    const query = new URLSearchParams(params.toString());
    query.set('tab', next);
    router.replace(`${pathname}?${query}`, { scroll: false });
  };

  const entriesFor = (section: StrategyTab, current: StrategyData | undefined = data): Entry[] => {
    if (!current) return [];
    const field = fields[section];
    const claims = current.assertion_citations ?? [];
    const citations = (index: number) =>
      claims.find((claim) => claim.field === field && claim.index === index)?.citations ?? [];
    if (section === 'Legal Arguments') {
      return current.legal_arguments.map((argument) => ({
        text: argument.statement,
        citations: argument.support ?? [],
      }));
    }
    if (section === 'Case Theory')
      return current.case_theory ? [{ text: current.case_theory, citations: citations(0) }] : [];
    if (section === 'Strategy Plan')
      return current.strategy_plan ? [{ text: current.strategy_plan, citations: citations(0) }] : [];
    const values =
      section === 'Key Issues'
        ? current.key_issues
        : section === 'Anticipated Counterarguments'
          ? current.counterarguments
          : current.evidence_gaps;
    return values.map((text, index) => ({ text, citations: citations(index) }));
  };

  const generated = !!data?.generated_at || !!data?.updated_at;
  const sourceMode = generated && data?.status !== 'model_generated' && data?.status !== 'no_evidence';
  const modelUnavailable =
    generated &&
    data?.status !== 'no_evidence' &&
    (data?.status === 'model_unavailable' || aiReachable === false);
  const entries = entriesFor(tab);
  const sourceExcerptCount = data?.legal_arguments.length ?? 0;
  const absentSectionCount = data
    ? strategyTabs.filter((section) => entriesFor(section).length === 0).length
    : 0;

  const editEntry = (index: number, value: string) => {
    if (!data) return;
    const next: StrategyData = { ...data };
    if (tab === 'Case Theory') next.case_theory = value;
    else if (tab === 'Strategy Plan') next.strategy_plan = value;
    else if (tab === 'Legal Arguments')
      next.legal_arguments = next.legal_arguments.map((entry, at) =>
        at === index ? { ...entry, statement: value } : entry,
      );
    else if (tab === 'Key Issues')
      next.key_issues = next.key_issues.map((entry, at) => (at === index ? value : entry));
    else if (tab === 'Anticipated Counterarguments')
      next.counterarguments = next.counterarguments.map((entry, at) => (at === index ? value : entry));
    else next.evidence_gaps = next.evidence_gaps.map((entry, at) => (at === index ? value : entry));
    setData(next);
    setDirty(true);
    setSavedNotice('');
  };

  const generate = async () => {
    if (!selectedCaseId) return;
    setBusy(true);
    setError('');
    try {
      const result = await strategyApi.generate(selectedCaseId);
      setData(result);
      setSavedAt(result.updated_at);
      setDirty(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Strategy generation failed.');
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    if (!data || !selectedCaseId || !dirty) return;
    setBusy(true);
    setError('');
    const payload: StrategyWrite = {
      case_theory: data.case_theory,
      key_issues: data.key_issues,
      legal_arguments: data.legal_arguments,
      counterarguments: data.counterarguments,
      evidence_gaps: data.evidence_gaps,
      strategy_plan: data.strategy_plan,
    };
    try {
      const result = await strategyApi.save(selectedCaseId, payload);
      setData(result);
      setSavedAt(result.updated_at);
      setDirty(false);
      setSavedNotice('Strategy notes saved.');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Strategy notes could not be saved.');
    } finally {
      setBusy(false);
    }
  };

  const createTask = async () => {
    if (!selectedCaseId) return;
    setBusy(true);
    setError('');
    try {
      const title = 'Review AI Strategy Advisor evidence gaps';
      await strategyApi.createTask({
        title,
        case_id: selectedCaseId,
        notes: `Review evidence gaps for ${caseInfo?.title ?? 'this case'} and verify any source excerpts before relying on them.`,
      });
      setTaskTitle(title);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Research task could not be created.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="strategy-page">
      <header className="strategy-head">
        <div>
          <span className="strategy-kicker">CASE WORKSPACE · STRATEGY</span>
          <h1>AI Strategy Advisor</h1>
          <p>Evidence-led analysis for your case team.</p>
        </div>
        <button
          className="strategy-generate"
          onClick={() => void generate()}
          disabled={busy || loadingCase || !selectedCaseId}
        >
          <Sparkles size={16} />
          {busy ? 'Working…' : 'Generate'}
        </button>
      </header>
      {error && (
        <div className="strategy-alert" role="alert">
          {error}
          <button onClick={() => setError('')}>Dismiss</button>
        </div>
      )}
      {!!data?.validation_warnings?.length && (
        <div className="strategy-alert" role="status">
          {data.validation_warnings.length} model claim(s) were omitted because their citations did not
          resolve to retrieved sources. Review the source excerpts before relying on this strategy.
        </div>
      )}

      <section className="strategy-case-context" aria-label="Strategy case context">
        <div className="strategy-case-picker">
          <label htmlFor="strategy-case">Select case for analysis</label>
          <select
            id="strategy-case"
            value={selectedCaseId}
            onChange={(event) => chooseCase(event.target.value)}
          >
            {cases.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </select>
        </div>
        {caseInfo ? (
          <div className="strategy-case-overview">
            <strong>{caseInfo.title}</strong>
            <span>
              {[
                caseInfo.reference_number,
                caseInfo.forum,
                caseInfo.seat,
                caseInfo.claimant && caseInfo.respondent
                  ? `${caseInfo.claimant} v. ${caseInfo.respondent}`
                  : undefined,
              ]
                .filter(Boolean)
                .join(' · ')}
            </span>
          </div>
        ) : (
          <div className="strategy-case-overview" role="status">
            Select a case to see its overview.
          </div>
        )}
      </section>

      <div className="strategy-evidence-bar" aria-live="polite">
        {!generated ? (
          <>
            <strong>—</strong>
            <span>Not analysed</span>
            <p>Generate a case strategy to see evidence and source excerpts.</p>
          </>
        ) : sourceMode ? (
          <>
            <div>
              <strong>{sourceExcerptCount}</strong>
              <span>Source excerpts</span>
            </div>
            <i />
            <div>
              <strong>{absentSectionCount}</strong>
              <span>Sections not generated</span>
            </div>
            <p>These excerpts were assembled without a language model.</p>
          </>
        ) : (
          <>
            <div>
              <strong>{data?.assertion_citations.length ?? 0}</strong>
              <span>Cited assertions</span>
            </div>
            <i />
            <div>
              <strong>{data?.citations.length ?? 0}</strong>
              <span>Retrieved sources</span>
            </div>
            <p>Counts are from the generated response and its citations.</p>
          </>
        )}
      </div>

      <nav
        className="strategy-tabs"
        aria-label="Strategy sections"
        role="tablist"
        onKeyDown={(event) => {
          if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
          event.preventDefault();
          const currentIndex = strategyTabs.indexOf(tab);
          const direction = event.key === 'ArrowRight' ? 1 : -1;
          const nextIndex = (currentIndex + direction + strategyTabs.length) % strategyTabs.length;
          const nextTab = strategyTabs[nextIndex];
          selectTab(nextTab);
          event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')[nextIndex]?.focus();
        }}
      >
        {strategyTabs.map((label) => (
          <button
            key={label}
            role="tab"
            id={`${tabId}-tab-${strategyTabs.indexOf(label)}`}
            aria-controls={`${tabId}-tabpanel`}
            className={tab === label ? 'active' : ''}
            aria-selected={tab === label}
            tabIndex={tab === label ? 0 : -1}
            onClick={() => selectTab(label)}
          >
            {label}
          </button>
        ))}
      </nav>

      <section
        className="strategy-content"
        role="tabpanel"
        id={`${tabId}-tabpanel`}
        aria-labelledby={`${tabId}-tab-${strategyTabs.indexOf(tab)}`}
        tabIndex={0}
      >
        <div className="strategy-content-head">
          <div>
            <span className="strategy-kicker">
              {String(strategyTabs.indexOf(tab) + 1).padStart(2, '0')} / 06
            </span>
            <h2>{tab}</h2>
          </div>
          <button onClick={() => void save()} disabled={!dirty || busy} className="strategy-save">
            <Save size={15} />
            {busy ? 'Saving…' : 'Save notes'}
          </button>
        </div>
        {savedNotice && (
          <p className="strategy-saved-notice" role="status">
            {savedNotice}
          </p>
        )}
        {data?.status === 'no_evidence' ? (
          <div className="strategy-empty strategy-empty-action">
            <strong>No indexed evidence is available for this case.</strong>
            <p>Add and index case documents, then generate this strategy again.</p>
            <Link href={`/cases/${selectedCaseId}`}>Open case files</Link>
          </div>
        ) : modelUnavailable ? (
          <div className="strategy-unavailable">
            <strong>Model unavailable · source excerpts assembled without a language model</strong>
            <p>
              {data?.generation_note ||
                'The configured model is unavailable. The following are retrieved source excerpts, not model analysis.'}
            </p>
          </div>
        ) : sourceMode ? (
          <div className="strategy-source-mode">
            <strong>Source excerpts assembled without a language model</strong>
            <p>{data?.generation_note}</p>
          </div>
        ) : generated && data?.status === 'model_generated' ? (
          <div className="strategy-mode-label">
            Model-generated, with citations checked against retrieved case chunks.
          </div>
        ) : null}
        {entries.length ? (
          entries.map((entry, index) => (
            <article className="strategy-block" key={`${tab}-${index}`}>
              <div className="strategy-block-title">
                <h3>
                  {tab === 'Legal Arguments'
                    ? `Argument ${index + 1}`
                    : tab === 'Case Theory'
                      ? 'Case theory'
                      : tab === 'Strategy Plan'
                        ? 'Plan'
                        : `${tab.replace(/s$/, '')} ${index + 1}`}
                </h3>
                {sourceMode ? (
                  <span className="strategy-source-tag">Source excerpt</span>
                ) : data?.status === 'model_generated' && entry.citations.length ? (
                  <span className="strategy-supported">
                    <Check size={12} /> Supported by cited evidence
                  </span>
                ) : (
                  <span className="strategy-hypothesis">Hypothesis — needs verification</span>
                )}
              </div>
              <textarea
                aria-label={`${tab} note ${index + 1}`}
                value={entry.text}
                onChange={(event) => editEntry(index, event.target.value)}
                rows={Math.max(3, Math.min(8, Math.ceil(entry.text.length / 100)))}
              />
              {entry.citations.length > 0 && (
                <div className="strategy-citations">
                  {entry.citations.map((citation) => (
                    <Citation key={`${citation.chunk_id}-${citation.page_number}`} citation={citation} />
                  ))}
                </div>
              )}
            </article>
          ))
        ) : data?.status === 'no_evidence' ? null : (
          <div className="strategy-empty strategy-empty-compact">
            <strong>
              {generated
                ? 'No content returned for this section.'
                : 'Generate a strategy to populate this section.'}
            </strong>
            <p>
              {generated
                ? 'This section is absent in the backend response.'
                : 'No analysis is inferred before generation.'}
            </p>
            {generated && <button onClick={() => selectTab('Evidence Gaps')}>Review evidence gaps</button>}
          </div>
        )}

        <footer className="strategy-footer">
          <span>
            {dirty
              ? 'Unsaved changes'
              : savedAt
                ? `Version saved ${workspaceDateTimeDisplay(savedAt)}`
                : 'No saved version'}
          </span>
          <button
            className="strategy-link-button"
            onClick={() => void createTask()}
            disabled={busy || !selectedCaseId}
          >
            <ClipboardList size={14} />
            Create research task
          </button>
          <Link
            className="strategy-link-button"
            href={`/research?case_id=${encodeURIComponent(selectedCaseId)}&question=${encodeURIComponent(`Follow up on strategy evidence for ${caseInfo?.title ?? 'this case'}`)}`}
          >
            <ArrowUpRight size={14} />
            Create follow-up question
          </Link>
        </footer>
        {taskTitle && (
          <p className="strategy-task-created" role="status">
            Task created: {taskTitle}
          </p>
        )}
      </section>
      <p className="strategy-disclaimer">
        This analysis provides no outcome guarantees. Verify every authority, citation, and proposition before
        relying on it.
      </p>
    </div>
  );
}

function Citation({ citation }: { citation: StrategyCitation }) {
  return (
    <a
      className="strategy-citation"
      href={`/documents/${citation.document_id}?page=${citation.page_number}`}
      title={`Evidence chunk ${citation.chunk_id}`}
    >
      <span>{citation.document_title}</span>
      <span>p. {citation.page_number}</span>
      <ArrowUpRight size={11} />
    </a>
  );
}
