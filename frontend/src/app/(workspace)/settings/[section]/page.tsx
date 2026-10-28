'use client';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { endpoints } from '@/lib/api/endpoints';
import { api, authToken } from '@/lib/api/client';
import { keys } from '@/lib/api/keys';
import { CorpusImportPanel } from '@/features/settings-data/CorpusImportPanel';
import {
  User,
  Building2,
  Brain,
  Database,
  Download,
  Upload,
  Palette,
  Shield,
  RefreshCw,
  Activity,
  Settings2,
} from 'lucide-react';
const sections = [
  ['profile', 'Profile', User],
  ['workspace', 'Workspace', Building2],
  ['local-ai', 'Local AI', Brain],
  ['embeddings', 'Embeddings', Activity],
  ['database', 'Database', Database],
  ['data-import', 'Data Import', Upload],
  ['appearance', 'Appearance', Palette],
  ['security', 'Security', Shield],
] as const;
const labels: Record<string, string> = {
  profile: 'Profile',
  workspace: 'Workspace',
  'local-ai': 'Local AI',
  embeddings: 'Embeddings',
  database: 'Database',
  'data-import': 'Data Import',
  appearance: 'Appearance',
  security: 'Security',
};
const schemas: Record<string, z.ZodObject<any>> = {
  profile: z.object({ name: z.string().min(2), email: z.string().email(), title: z.string().optional() }),
  workspace: z.object({
    name: z.string().min(2),
    default_jurisdiction: z.string().optional(),
    default_seat: z.string().optional(),
    currency: z.string().optional(),
  }),
  'local-ai': z.object({
    base_url: z.string().url(),
    model: z.string().min(1),
    temperature: z.coerce.number().min(0).max(2),
    top_k: z.coerce.number().int().min(1).max(50),
  }),
  appearance: z.object({
    theme: z.enum(['light', 'dark', 'system']),
    density: z.enum(['comfortable', 'compact']),
    font: z.enum(['inter', 'serif']),
  }),
  security: z.object({ current_password: z.string().min(1), new_password: z.string().min(8) }),
};
const fields: Record<string, string[]> = {
  profile: ['name', 'email', 'title'],
  workspace: ['name', 'default_jurisdiction', 'default_seat', 'currency'],
  'local-ai': ['base_url', 'model', 'temperature', 'top_k'],
  appearance: ['theme', 'density', 'font'],
  security: ['current_password', 'new_password'],
};
function SettingsForm({ section, data }: { section: string; data: Record<string, unknown> }) {
  const schema = schemas[section] ?? z.object({});
  const list = fields[section] ?? [];
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    defaultValues: Object.fromEntries(
      list.map((k) => [
        k,
        data[k] ?? (k === 'theme' ? 'system' : k === 'density' ? 'comfortable' : k === 'font' ? 'inter' : ''),
      ]),
    ),
  });
  const [saving, setSaving] = useState(false);
  const fieldLabel = (k: string) =>
    section === 'local-ai'
      ? ({ base_url: 'Base URL', model: 'Model', temperature: 'Temperature', top_k: 'Top-k' }[k] ?? k)
      : k.replaceAll('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  const submit = handleSubmit(async (values) => {
    setSaving(true);
    try {
      if (section === 'security') {
        await api.post('/settings/password', values);
        toast.success('Password changed');
      } else {
        await endpoints.updateSettings(section, values);
        if (section === 'appearance') {
          const v = values as Record<string, string>;
          localStorage.setItem('tantara_theme', v.theme);
          localStorage.setItem('tantara_density', v.density);
          localStorage.setItem('tantara_font', v.font);
          document.documentElement.dataset.theme = v.theme;
          document.documentElement.dataset.density = v.density;
          document.documentElement.dataset.font = v.font;
        }
        toast.success(`${labels[section]} saved`);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Unable to save settings');
    } finally {
      setSaving(false);
    }
  });
  return (
    <form onSubmit={submit}>
      {list.map((k) => {
        const helpId = section === 'local-ai' ? `${k}-help` : undefined;
        const errorId = errors[k] ? `${k}-error` : undefined;
        const describedBy = [helpId, errorId].filter(Boolean).join(' ') || undefined;
        return (
          <div className="field" key={k}>
            <label htmlFor={k}>{fieldLabel(k)}</label>
            {['theme', 'density', 'font'].includes(k) ? (
              <select
                id={k}
                aria-invalid={Boolean(errors[k])}
                aria-describedby={describedBy}
                {...register(k)}
              >
                {(k === 'theme'
                  ? ['light', 'dark', 'system']
                  : k === 'density'
                    ? ['comfortable', 'compact']
                    : ['inter', 'serif']
                ).map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </select>
            ) : (
              <input
                id={k}
                type={
                  k.includes('password')
                    ? 'password'
                    : k === 'email'
                      ? 'email'
                      : k === 'temperature' || k === 'top_k'
                        ? 'number'
                        : 'text'
                }
                step={k === 'temperature' ? '.1' : undefined}
                aria-invalid={Boolean(errors[k])}
                aria-describedby={describedBy}
                {...register(k)}
              />
            )}
            {section === 'local-ai' && (
              <small id={helpId} className="muted">
                {k === 'base_url'
                  ? 'OpenAI-compatible local API endpoint.'
                  : k === 'temperature'
                    ? 'Sampling temperature from 0 to 2.'
                    : k === 'top_k'
                      ? 'Maximum retrieved context chunks.'
                      : 'Model identifier served by the configured endpoint.'}
              </small>
            )}
            {errors[k] && (
              <small id={errorId} style={{ color: '#be123c' }}>
                Please enter a valid {fieldLabel(k).toLowerCase()}.
              </small>
            )}
          </div>
        );
      })}
      <div className="settings-actions">
        <button className="primary" disabled={saving}>
          {saving ? 'Saving…' : 'Save changes'}
        </button>
      </div>
    </form>
  );
}
export default function SettingsSection() {
  const { section = 'profile' } = useParams<{ section: string }>();
  const title = labels[section] ?? 'Settings';
  const query = useQuery({
    queryKey: keys.settings(section),
    queryFn: () => endpoints.settings(section),
    enabled: !!labels[section] && section !== 'data-import',
  });
  const status = useQuery({
    queryKey: ['ai', 'status'],
    queryFn: endpoints.aiStatus,
    enabled: section === 'local-ai',
  });
  const [testing, setTesting] = useState(false);
  const activeNavLink = useRef<HTMLAnchorElement>(null);
  const [special, setSpecial] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {
    if (window.matchMedia('(max-width: 760px)').matches) {
      activeNavLink.current?.scrollIntoView({
        block: 'nearest',
        inline: 'center',
        behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
      });
    }
  }, [section]);
  const test = async () => {
    setTesting(true);
    try {
      const [config, r] = await Promise.all([
        api.get<Record<string, unknown>>('/settings/ai'),
        api.get<Record<string, unknown>>('/ai/status'),
      ]);
      const combined = { configuration: config, ...r };
      setSpecial(combined);
      toast.success('AI status received');
    } catch (e) {
      setSpecial({ reachable: false, status: 'unreachable' });
      toast.error(e instanceof Error ? e.message : 'Connection failed');
    } finally {
      setTesting(false);
    }
  };
  const backup = async () => {
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL ? process.env.NEXT_PUBLIC_API_BASE_URL.replace(/\/$/, '') + '/api/v1' : '/api/v1'}/settings/database/backup`,
        { headers: authToken() ? { Authorization: `Bearer ${authToken()}` } : {} },
      );
      if (!res.ok) throw new Error('Backup endpoint unavailable');
      const blob = await res.blob(),
        url = URL.createObjectURL(blob),
        a = document.createElement('a');
      a.href = url;
      a.download = 'tantara-backup.db';
      a.click();
      URL.revokeObjectURL(url);
      toast.success('Database backup downloaded');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Unable to download backup');
    }
  };
  if (!labels[section])
    return (
      <div className="card settings-card">
        <h1 className="title">Settings page unavailable</h1>
        <p className="muted">Choose one of the settings sections.</p>
      </div>
    );
  return (
    <div>
      <div style={{ marginBottom: 18 }}>
        <h1 className="title">Settings</h1>
        <p className="subheading">Manage your workspace preferences and local services.</p>
      </div>
      <div className="settings-layout">
        <nav className="card settings-nav" aria-label="Settings navigation">
          {sections.map(([key, label, Icon]) => (
            <Link
              key={key}
              href={`/settings/${key}`}
              ref={section === key ? activeNavLink : undefined}
              aria-current={section === key ? 'location' : undefined}
            >
              <Icon size={16} />
              {label}
            </Link>
          ))}
        </nav>
        <section className="card settings-card">
          <h2 style={{ fontSize: 18, margin: '0 0 4px' }}>{title}</h2>
          <p className="muted" style={{ fontSize: 12, marginTop: 5 }}>
            {(query.data?.description as string) ||
              `Configure ${title.toLowerCase()} for this local workspace.`}
          </p>
          {query.isLoading ? (
            <p className="muted" role="status">
              Loading settings…
            </p>
          ) : query.isError ? (
            <div className="offline">
              <strong>Backend not reachable</strong>
              <details>
                <summary>Start command</summary>
                <code>cd backend &amp;&amp; .venv/bin/python -m uvicorn app.main:app</code>
              </details>
              <button className="primary" onClick={() => void query.refetch()}>
                <RefreshCw size={14} /> Retry
              </button>
            </div>
          ) : fields[section] && section === 'workspace' ? (
            <>
              <SettingsForm section={section} data={query.data ?? {}} />
              <InstitutionChoices />
            </>
          ) : section === 'local-ai' ? (
            <SpecialSettings
              section={section}
              data={query.data ?? {}}
              onBackup={backup}
              onTest={test}
              testing={testing}
              status={special ?? status.data ?? null}
            />
          ) : fields[section] ? (
            <SettingsForm section={section} data={query.data ?? {}} />
          ) : (
            <SpecialSettings
              section={section}
              data={query.data ?? {}}
              onBackup={backup}
              onTest={test}
              testing={testing}
              status={special ?? status.data ?? null}
            />
          )}
        </section>
      </div>
    </div>
  );
}
function connectionSummary(status: Record<string, unknown> | null) {
  if (!status) return 'Connection has not been tested · Embeddings status unavailable';
  const llm = status.llm && typeof status.llm === 'object' ? (status.llm as Record<string, unknown>) : status;
  const embeddings =
    status.embeddings && typeof status.embeddings === 'object'
      ? (status.embeddings as Record<string, unknown>)
      : {};
  const reachable = llm.reachable ?? status.reachable;
  const health =
    reachable === true
      ? 'Reachable'
      : reachable === false || status.status === 'unreachable'
        ? 'Not reachable'
        : 'Reachability unknown';
  const model = typeof llm.model === 'string' ? ` · ${llm.model}` : '';
  const latency = typeof llm.latency_ms === 'number' ? ` · ${llm.latency_ms} ms` : '';
  const provider = typeof embeddings.provider === 'string' ? embeddings.provider : 'unknown backend';
  const ready =
    embeddings.ready === true ? 'ready' : embeddings.ready === false ? 'not ready' : 'status unknown';
  return `${health}${model}${latency} · Embeddings: ${provider}, ${ready}`;
}
function redactDiagnostics(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redactDiagnostics);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        key,
        /(key|secret|token|password|credential)/i.test(key) ? '[redacted]' : redactDiagnostics(item),
      ]),
    );
  }
  return value;
}
function SpecialSettings({
  section,
  data,
  onBackup,
  onTest,
  testing,
  status,
}: {
  section: string;
  data: Record<string, unknown>;
  onBackup: () => void;
  onTest: () => void;
  testing: boolean;
  status: Record<string, unknown> | null;
}) {
  const [busy, setBusy] = useState(false);
  const trigger = async (path: string) => {
    setBusy(true);
    try {
      const r = await api.post(path);
      toast.success('Request completed');
      return r;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Request failed');
    } finally {
      setBusy(false);
    }
  };
  if (section === 'local-ai')
    return (
      <div>
        <SettingsForm section="local-ai" data={data} />
        <div className="connection-block">
          <p className="connection-summary" role="status">
            {connectionSummary(status)}
          </p>
          <div className="connection-row">
            <button className="secondary-button" onClick={onTest} disabled={testing}>
              {testing ? 'Testing…' : 'Test connection'}
            </button>
            <span className="muted" style={{ fontSize: 12 }}>
              Tests saved configuration.
            </span>
          </div>
          <details className="technical-details">
            <summary>Technical details</summary>
            <pre>
              {JSON.stringify(redactDiagnostics(status ?? { message: 'No status response yet.' }), null, 2)}
            </pre>
          </details>
        </div>
      </div>
    );
  if (section === 'database')
    return (
      <div>
        <dl className="data-list">
          {Object.entries(data).map(([k, v]) => (
            <div key={k}>
              <dt>{k.replaceAll('_', ' ')}</dt>
              <dd>{typeof v === 'object' ? JSON.stringify(v) : String(v ?? '—')}</dd>
            </div>
          ))}
        </dl>
        <button className="primary" onClick={onBackup}>
          <Download size={15} /> Download database backup
        </button>
      </div>
    );
  if (section === 'embeddings')
    return (
      <div>
        <dl className="data-list">
          {Object.entries(data).map(([k, v]) => (
            <div key={k}>
              <dt>{k.replaceAll('_', ' ')}</dt>
              <dd>{String(v ?? '—')}</dd>
            </div>
          ))}
        </dl>
        <p className="muted">Rebuilding embeddings may temporarily reduce search availability.</p>
        <button
          className="primary"
          disabled
          title="The current API contract does not define an embeddings rebuild operation"
        >
          Rebuild unavailable in current API
        </button>
      </div>
    );
  if (section === 'data-import') return <CorpusImportPanel />;
  if (section === 'security')
    return (
      <div>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            setBusy(true);
            try {
              await api.post('/settings/password', {
                current_password: f.get('current_password'),
                new_password: f.get('new_password'),
              });
              toast.success('Password changed');
              e.currentTarget.reset();
            } catch (err) {
              toast.error(err instanceof Error ? err.message : 'Unable to change password');
            } finally {
              setBusy(false);
            }
          }}
        >
          <div className="field">
            <label htmlFor="current_password">Current password</label>
            <input
              id="current_password"
              name="current_password"
              type="password"
              required
              autoComplete="current-password"
            />
          </div>
          <div className="field">
            <label htmlFor="new_password">New password</label>
            <input
              id="new_password"
              name="new_password"
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
            />
          </div>
          <button className="primary" disabled={busy}>
            {busy ? 'Saving…' : 'Change password'}
          </button>
        </form>
        <p style={{ fontSize: 12, color: '#92400e', background: '#fff7e5', padding: 12, borderRadius: 8 }}>
          Local workspace access is intended for localhost only. Keep this service off public networks.
        </p>
        <dl className="data-list">
          {Object.entries(data).map(([k, v]) => (
            <div key={k}>
              <dt>{k.replaceAll('_', ' ')}</dt>
              <dd>{typeof v === 'object' ? JSON.stringify(v) : String(v ?? '—')}</dd>
            </div>
          ))}
        </dl>
      </div>
    );
  if (section === 'workspace') return null;
  return <SettingsForm section={section} data={data} />;
}

function InstitutionChoices() {
  const q = useQuery({
    queryKey: ['meta', 'institutions'],
    queryFn: () => api.get<{ items?: string[] } | string[]>('/meta/institutions'),
  });
  const items = Array.isArray(q.data) ? q.data : q.data?.items;
  return (
    <div style={{ marginTop: 24, borderTop: '1px solid #eef1f5', paddingTop: 16 }}>
      <h3 style={{ fontSize: 14 }}>Arbitration institutions</h3>
      {q.isLoading ? (
        <p className="muted" role="status">
          Loading institutions…
        </p>
      ) : q.isError ? (
        <p className="muted">Institution list unavailable.</p>
      ) : items?.length ? (
        <div className="institution-list">
          {items.map((x) => (
            <span key={x}>{x}</span>
          ))}
        </div>
      ) : (
        <p className="muted">No institutions configured.</p>
      )}
      <small className="muted">
        The current API exposes institution choices as read-only; add/remove operations await a write
        endpoint.
      </small>
    </div>
  );
}
