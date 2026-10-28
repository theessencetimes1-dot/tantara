'use client';

import Link from 'next/link';
import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError } from '@/lib/api/client';
import { workspaceDateTimeDisplay } from '@/lib/datetime';
import {
  CaseItem,
  CommunityPost,
  CommunityReply,
  communityApi,
  CommunityValidationError,
  errorMessage,
  Identity,
  Page,
} from './api';

function errorText(error: unknown) {
  if (error instanceof ApiError) return `API error ${error.status} (${error.code}): ${error.message}`;
  if (error instanceof CommunityValidationError)
    return `API error ${error.status} (${error.code}): ${error.message}`;
  if (error instanceof TypeError) return 'Community API is unavailable. Check the connection and retry.';
  return errorMessage(error);
}

function authorName(value: { author?: { name?: string; display_name?: string }; author_name?: string }) {
  return (
    value.author?.display_name || value.author?.name || value.author_name || 'Author not provided by the API'
  );
}

function timestamp(value?: string) {
  if (!value) return 'Timestamp not provided by the API';
  return workspaceDateTimeDisplay(value);
}

function DemoBadge() {
  return (
    <span
      className="community-demo-badge"
      style={{
        borderRadius: 999,
        background: '#fff4d6',
        color: '#7a4b00',
        fontSize: 11,
        fontWeight: 700,
        padding: '4px 9px',
        whiteSpace: 'nowrap',
      }}
    >
      Demo content
    </span>
  );
}

const metaStyle = {
  borderRadius: 999,
  background: '#f1f5f9',
  color: '#475569',
  fontSize: 11,
  padding: '4px 8px',
};
const tagStyle = { ...metaStyle, background: '#eef2ff', color: '#3730a3' };

function Composer({ onCreated }: { onCreated: () => Promise<void> }) {
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [tags, setTags] = useState('');
  const [caseRef, setCaseRef] = useState('');
  const [kind, setKind] = useState<'discussion' | 'question'>('discussion');
  const [visibility, setVisibility] = useState<'private' | 'workspace'>('private');
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    communityApi
      .cases()
      .then((result) => setCases(result.items || []))
      .catch(() => setCases([]));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setFieldErrors({});
    try {
      await communityApi.create({
        title,
        body,
        tags: tags
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
        kind,
        visibility,
        ...(caseRef ? { case_ref: caseRef } : {}),
      });
      setTitle('');
      setBody('');
      setTags('');
      setCaseRef('');
      await onCreated();
    } catch (issue) {
      setError(errorText(issue));
      if (issue instanceof CommunityValidationError) {
        setFieldErrors(
          Object.fromEntries(
            issue.details.map((detail) => [String(detail.loc?.at(-1) ?? ''), detail.msg ?? 'Invalid value.']),
          ),
        );
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      className="card community-composer"
      onSubmit={submit}
      style={{ padding: 20, display: 'grid', gap: 8 }}
    >
      <h2 style={{ margin: '0 0 8px' }}>Start a discussion</h2>
      <div className="field">
        <label htmlFor="community-title">Title</label>
        <input
          id="community-title"
          required
          aria-invalid={Boolean(fieldErrors.title)}
          aria-describedby={fieldErrors.title ? 'community-title-error' : undefined}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
        {fieldErrors.title && (
          <small id="community-title-error" role="alert">
            {fieldErrors.title}
          </small>
        )}
      </div>
      <div className="field">
        <label htmlFor="community-body">Details</label>
        <textarea
          id="community-body"
          required
          aria-invalid={Boolean(fieldErrors.body)}
          aria-describedby={fieldErrors.body ? 'community-body-error' : undefined}
          rows={4}
          value={body}
          onChange={(event) => setBody(event.target.value)}
        />
        {fieldErrors.body && (
          <small id="community-body-error" role="alert">
            {fieldErrors.body}
          </small>
        )}
      </div>
      <div className="field">
        <label htmlFor="community-tags">Tags</label>
        <input id="community-tags" value={tags} onChange={(event) => setTags(event.target.value)} />
        <small>Separate tags with commas.</small>
      </div>
      <div
        className="community-form-row"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 220px), 1fr))',
          gap: 12,
        }}
      >
        <div className="field">
          <label htmlFor="community-kind">Discussion type</label>
          <select
            id="community-kind"
            value={kind}
            onChange={(event) => setKind(event.target.value as 'discussion' | 'question')}
          >
            <option value="discussion">Discussion</option>
            <option value="question">Question</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="community-visibility">Visibility</label>
          <select
            id="community-visibility"
            value={visibility}
            onChange={(event) => setVisibility(event.target.value as 'private' | 'workspace')}
          >
            <option value="private">Private · only you</option>
            <option value="workspace">Workspace · visible to colleagues</option>
          </select>
        </div>
      </div>
      <div className="field">
        <label htmlFor="community-case">Related case (optional)</label>
        <select id="community-case" value={caseRef} onChange={(event) => setCaseRef(event.target.value)}>
          <option value="">No case link</option>
          {cases.map((item) => (
            <option key={item.id} value={item.id}>
              {item.title}
            </option>
          ))}
        </select>
      </div>
      {error && (
        <p role="alert" className="community-error">
          {error}
        </p>
      )}
      <button className="primary community-submit" style={{ width: 'fit-content' }} disabled={busy}>
        {busy ? 'Posting…' : 'Post discussion'}
      </button>
    </form>
  );
}

export function CommunityFeed() {
  const [posts, setPosts] = useState<CommunityPost[]>([]);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [tags, setTags] = useState<string[]>([]);
  const [tag, setTag] = useState('');
  const [query, setQuery] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [caseNames, setCaseNames] = useState<Record<string, string>>({});

  const load = useCallback(async (nextPage: number, q: string, selectedTag: string) => {
    setLoading(true);
    setError('');
    try {
      const result = await communityApi.list(nextPage, q, selectedTag);
      setPosts(result.items || []);
      setPages(result.pages);
      setPage(result.page);
      setTags(Array.from(new Set(result.items.flatMap((post) => post.tags || []))).sort());
    } catch (issue) {
      setError(errorText(issue));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(1, '', '');
  }, [load]);

  useEffect(() => {
    communityApi
      .cases()
      .then((result) => {
        setCaseNames(Object.fromEntries(result.items.map((item) => [item.id, item.title])));
      })
      .catch(() => setCaseNames({}));
  }, []);

  async function refreshFirstPage() {
    await load(1, query, tag);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  return (
    <div
      className="community-page"
      style={{ maxWidth: 980, margin: '0 auto', padding: '28px 20px', display: 'grid', gap: 18 }}
    >
      <header>
        <p
          className="muted community-eyebrow"
          style={{ margin: '0 0 4px', fontSize: 11, fontWeight: 700, letterSpacing: '.08em' }}
        >
          PEER DISCUSSION
        </p>
        <h1 className="title">Community</h1>
        <p className="subheading">Discuss practical questions with your legal community.</p>
      </header>
      <Composer onCreated={refreshFirstPage} />
      <section
        className="community-feed"
        aria-label="Community discussions"
        style={{ display: 'grid', gap: 12 }}
      >
        <div className="community-filters" style={{ display: 'grid', gap: 12 }}>
          <div className="community-search">
            <label htmlFor="community-search">Search discussions</label>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <input
                id="community-search"
                style={{ minWidth: 180, flex: '1 1 240px' }}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') void load(1, query, tag);
                }}
              />
              <button className="secondary-button" onClick={() => void load(1, query, tag)}>
                Search
              </button>
            </div>
          </div>
          <div
            className="community-tag-filters"
            aria-label="Filter by tag"
            style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}
          >
            {tags.map((item) => (
              <button
                type="button"
                key={item}
                aria-pressed={tag === item}
                className={`community-tag-chip${tag === item ? ' selected' : ''}`}
                style={{
                  border: tag === item ? '1px solid #4f46e5' : '1px solid #d7dcef',
                  borderRadius: 999,
                  background: tag === item ? '#eef2ff' : '#fff',
                  color: tag === item ? '#3730a3' : '#475569',
                  padding: '6px 11px',
                  cursor: 'pointer',
                }}
                onClick={() => {
                  const next = tag === item ? '' : item;
                  setTag(next);
                  void load(1, query, next);
                }}
              >
                {item}
              </button>
            ))}
          </div>
        </div>
        {error && (
          <div role="alert" className="offline">
            <p>{error}</p>
            <button className="secondary-button" onClick={() => void load(page, query, tag)}>
              Retry
            </button>
          </div>
        )}
        {loading ? (
          <p role="status" className="muted">
            Loading discussions…
          </p>
        ) : posts.length === 0 ? (
          <div className="card community-empty">
            <h2>{query.trim() || tag ? 'No matching discussions' : 'No discussions yet'}</h2>
            <p className="muted">
              {query.trim() || tag
                ? 'No posts match the current search and tag filters.'
                : 'Start a discussion using the composer above.'}
            </p>
          </div>
        ) : (
          posts.map((post) => (
            <article
              className="card community-post"
              key={post.id}
              style={{ padding: 18, overflowWrap: 'anywhere' }}
            >
              <div
                className="community-byline"
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 8,
                  marginBottom: 10,
                  color: '#64748b',
                  fontSize: 12,
                }}
              >
                <span>
                  {authorName(post)} · {timestamp(post.created_at)}
                </span>
                {post.is_demo && <DemoBadge />}
              </div>
              <h2 style={{ fontSize: 18, margin: '0 0 8px' }}>
                <Link href={`/community/${post.id}`}>{post.title}</Link>
              </h2>
              <p
                className="community-post-body"
                style={{ whiteSpace: 'pre-wrap', lineHeight: 1.55, margin: '0 0 12px' }}
              >
                {post.body}
              </p>
              <div
                className="community-post-meta"
                style={{ display: 'flex', flexWrap: 'wrap', gap: 7, alignItems: 'center' }}
              >
                <span className="community-visibility" style={metaStyle}>
                  {post.visibility === 'workspace' ? 'Workspace' : 'Private'}
                </span>
                {post.kind && (
                  <span style={metaStyle}>{post.kind === 'question' ? 'Question' : 'Discussion'}</span>
                )}
                {post.case_ref && (
                  <span style={metaStyle}>
                    Related case:{' '}
                    {caseNames[post.case_ref] ? (
                      <Link href={`/cases/${post.case_ref}`}>{caseNames[post.case_ref]}</Link>
                    ) : (
                      post.case_ref
                    )}
                  </span>
                )}
                {post.tags?.map((item) => (
                  <span className="community-post-tag" style={tagStyle} key={item}>
                    {item}
                  </span>
                ))}
              </div>
            </article>
          ))
        )}
        {!loading && pages > 1 && (
          <div className="community-pagination">
            <button
              className="secondary-button"
              disabled={page <= 1}
              onClick={() => void load(page - 1, query, tag)}
            >
              Previous
            </button>
            <span>
              Page {page} of {pages}
            </span>
            <button
              className="secondary-button"
              disabled={page >= pages}
              onClick={() => void load(page + 1, query, tag)}
            >
              Next
            </button>
          </div>
        )}
      </section>
    </div>
  );
}

export function CommunityThread({ id }: { id: string }) {
  const [post, setPost] = useState<CommunityPost | null>(null);
  const [replies, setReplies] = useState<CommunityReply[]>([]);
  const [replyTotal, setReplyTotal] = useState<number | null>(null);
  const [me, setMe] = useState<Identity | null>(null);
  const [saved, setSaved] = useState(false);
  const [caseNames, setCaseNames] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [reply, setReply] = useState('');
  const [busy, setBusy] = useState(false);

  const loadThread = useCallback(async () => {
    const [postResult, replyResult, identity, savedPosts, caseResult] = await Promise.all([
      communityApi.post(id),
      communityApi.replies(id),
      communityApi.me(),
      communityApi.list(1, '', '', true),
      communityApi.cases(),
    ]);
    const response = replyResult as Page<CommunityReply>;
    setPost(postResult);
    setReplies(response.items || []);
    setReplyTotal(response.total);
    setMe(identity);
    setSaved(savedPosts.items.some((item) => item.id === id));
    setCaseNames(Object.fromEntries(caseResult.items.map((item) => [item.id, item.title])));
    setError('');
  }, [id]);

  useEffect(() => {
    void loadThread().catch((issue) => setError(errorText(issue)));
  }, [loadThread]);

  const own = useMemo(() => {
    if (!post || !me) return false;
    if (post.author?.id && me.id) return post.author.id === me.id;
    return !!post.author_name && post.author_name === me.name && post.author_role === me.role;
  }, [post, me]);

  async function sendReply(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await communityApi.reply(id, reply);
      setReply('');
      await loadThread();
    } catch (issue) {
      setError(errorText(issue));
    } finally {
      setBusy(false);
    }
  }

  async function toggleSave() {
    setBusy(true);
    setError('');
    try {
      const result = await communityApi.save(id);
      setSaved(result.saved);
    } catch (issue) {
      setError(errorText(issue));
    } finally {
      setBusy(false);
    }
  }

  if (!post && !error)
    return (
      <div className="community-page" style={{ maxWidth: 850, margin: '0 auto', padding: '28px 20px' }}>
        <p role="status">Loading discussion…</p>
      </div>
    );

  return (
    <div
      className="community-thread"
      style={{ maxWidth: 850, margin: '0 auto', padding: '28px 20px', display: 'grid', gap: 16 }}
    >
      <Link className="community-back" href="/community">
        ← Community
      </Link>
      {error && (
        <div role="alert" className="offline">
          <p>{error}</p>
          <button
            className="secondary-button"
            onClick={() => void loadThread().catch((issue) => setError(errorText(issue)))}
          >
            Retry
          </button>
        </div>
      )}
      {post && (
        <article
          className="card community-post community-thread-post"
          style={{ padding: 22, overflowWrap: 'anywhere' }}
        >
          <div
            className="community-byline"
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 8,
              marginBottom: 12,
              color: '#64748b',
              fontSize: 12,
            }}
          >
            <span>
              Posted by {authorName(post)}
              {own ? ' · posted by you' : ''} · {timestamp(post.created_at)}
            </span>
            {post.is_demo && <DemoBadge />}
          </div>
          <h1 style={{ fontSize: 25, lineHeight: 1.25, margin: '0 0 12px' }}>{post.title}</h1>
          <p
            className="community-post-body"
            style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6, margin: '0 0 16px' }}
          >
            {post.body}
          </p>
          <div
            className="community-post-meta"
            style={{ display: 'flex', flexWrap: 'wrap', gap: 7, alignItems: 'center', marginBottom: 16 }}
          >
            <span className="community-visibility" style={metaStyle}>
              {post.visibility === 'workspace' ? 'Workspace' : 'Private'}
            </span>
            {post.kind && (
              <span style={metaStyle}>{post.kind === 'question' ? 'Question' : 'Discussion'}</span>
            )}
            {post.case_ref && (
              <span style={metaStyle}>
                Related case:{' '}
                {caseNames[post.case_ref] ? (
                  <Link href={`/cases/${post.case_ref}`}>{caseNames[post.case_ref]}</Link>
                ) : (
                  post.case_ref
                )}
              </span>
            )}
            {post.tags?.map((item) => (
              <span className="community-post-tag" style={tagStyle} key={item}>
                {item}
              </span>
            ))}
          </div>
          <button
            className="secondary-button community-save"
            style={{ width: 'fit-content' }}
            disabled={busy}
            onClick={() => void toggleSave()}
          >
            {saved ? 'Unsave discussion' : 'Save discussion'}
          </button>
        </article>
      )}
      <section className="community-replies" style={{ display: 'grid', gap: 10 }}>
        <h2 style={{ margin: '4px 0', fontSize: 18 }}>Replies ({replyTotal ?? '—'})</h2>
        {replies.map((item) => (
          <article className="card community-reply" style={{ padding: 16 }} key={item.id}>
            <div
              className="community-byline"
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 8,
                marginBottom: 8,
                color: '#64748b',
                fontSize: 12,
              }}
            >
              <span>
                {authorName(item)} · {timestamp(item.created_at)}
              </span>
              {item.is_demo && <DemoBadge />}
            </div>
            <p style={{ whiteSpace: 'pre-wrap', lineHeight: 1.55, margin: 0 }}>{item.body}</p>
          </article>
        ))}
        {replyTotal === 0 && <p className="muted">No replies yet.</p>}
      </section>
      <form
        className="card community-reply-composer"
        onSubmit={sendReply}
        style={{ padding: 18, display: 'grid', gap: 10 }}
      >
        <div className="field">
          <label htmlFor="community-reply">Add a reply</label>
          <textarea
            id="community-reply"
            required
            rows={4}
            value={reply}
            onChange={(event) => setReply(event.target.value)}
          />
        </div>
        <button className="primary" style={{ width: 'fit-content' }} disabled={busy}>
          {busy ? 'Sending…' : 'Reply'}
        </button>
      </form>
    </div>
  );
}
