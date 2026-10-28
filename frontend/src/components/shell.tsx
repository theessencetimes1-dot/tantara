'use client';

import Link from 'next/link';
import * as Dialog from '@radix-ui/react-dialog';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import {
  Bell,
  BookOpen,
  BriefcaseBusiness,
  CalendarDays,
  ChevronDown,
  Command,
  FileText,
  FolderOpen,
  House,
  Menu,
  Search,
  Settings,
  Users,
  X,
  ArrowRight,
  CheckSquare,
} from 'lucide-react';
import { api, clearToken } from '@/lib/api/client';
import { toast } from 'sonner';
import type { Activity } from '@/lib/api/types';
import '@/features/shell/styles.css';

export const navItems = [
  { href: '/dashboard', label: 'Dashboard', Icon: House },
  { href: '/cases', label: 'My Cases', Icon: FolderOpen },
  { href: '/clients', label: 'Clients', Icon: Users },
  { href: '/tasks', label: 'Tasks', Icon: CheckSquare },
  { href: '/calendar', label: 'Calendar', Icon: CalendarDays },
  { href: '/documents', label: 'Documents', Icon: FileText },
  { href: '/search', label: 'Search', Icon: Search },
  { href: '/research', label: 'Research Desk', Icon: BookOpen },
  { href: '/drafts', label: 'Drafts & Documents', Icon: FileText },
  { href: '/autofill', label: 'Smart Autofill', Icon: CheckSquare },
  { href: '/bundles', label: 'Bundles', Icon: FileText },
  { href: '/strategy', label: 'Strategy', Icon: BriefcaseBusiness },
  {
    href: '/community',
    label: 'Community (Arbitration)',
    Icon: BriefcaseBusiness,
  },
  { href: '/settings/profile', label: 'Settings', Icon: Settings },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [authReady, setAuthReady] = useState(false);
  const [displayName, setDisplayName] = useState('');
  const [displayEmail, setDisplayEmail] = useState('');
  const [displayRole, setDisplayRole] = useState('');
  const [authError, setAuthError] = useState(false);
  const [notifications, setNotifications] = useState(false);
  const [noticeItems, setNoticeItems] = useState<Activity[]>([]);
  const [palette, setPalette] = useState(false);
  const [q, setQ] = useState('');
  const [profile, setProfile] = useState(false);
  const [hits, setHits] = useState<Array<{ title: string; href: string; kind: string }>>([]);
  const [busy, setBusy] = useState(false);
  const [offline, setOffline] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = localStorage.getItem('tantara_theme') || 'light';
    document.documentElement.dataset.density = localStorage.getItem('tantara_density') || 'comfortable';
    document.documentElement.dataset.font = localStorage.getItem('tantara_font') || 'inter';
    const hasToken =
      !!document.cookie.split('; ').find((x) => x.startsWith('tantara_token=')) ||
      !!localStorage.getItem('tantara_token');
    if (!hasToken) {
      setAuthError(true);
      setAuthReady(true);
    } else {
      api
        .get<{ full_name?: string; name?: string; email?: string; role: string }>('/auth/me')
        .then((user) => {
          setDisplayName(user.full_name || user.name || '');
          setDisplayEmail(user.email || '');
          setDisplayRole(user.role || '');
          setAuthReady(true);
        })
        .catch(() => {
          setAuthError(true);
          setAuthReady(true);
        });
    }
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setPalette(true);
        setTimeout(() => input.current?.focus(), 0);
      }
      if (event.key === 'Escape') {
        setPalette(false);
        setOpen(false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const search = async (term: string) => {
    setQ(term);
    if (term.trim().length < 2) {
      setHits([]);
      setOffline(false);
      return;
    }
    setBusy(true);
    setOffline(false);
    try {
      const [cases, docs] = await Promise.allSettled([
        api.get<{ items: Array<{ id: string; title: string }> }>(`/cases?q=${encodeURIComponent(term)}`),
        api.get<{
          items: Array<{ document_id: string; document_title: string }>;
        }>(`/search/documents?query=${encodeURIComponent(term)}&page=1&page_size=5`),
      ]);
      const results: Array<{ title: string; href: string; kind: string }> = [];
      if (cases.status === 'fulfilled')
        cases.value.items?.forEach((item) =>
          results.push({
            title: item.title,
            href: `/cases/${item.id}`,
            kind: 'Case',
          }),
        );
      if (docs.status === 'fulfilled')
        docs.value.items?.forEach((item) =>
          results.push({
            title: item.document_title,
            href: `/documents/${item.document_id}`,
            kind: 'Document',
          }),
        );
      setHits(results.slice(0, 8));
      if (cases.status === 'rejected' && docs.status === 'rejected') setOffline(true);
    } finally {
      setBusy(false);
    }
  };

  const showNotifications = async () => {
    const next = !notifications;
    setNotifications(next);
    if (next) {
      try {
        setNoticeItems(await api.get<Activity[]>('/dashboard/activity'));
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Recent activity unavailable');
      }
    }
  };
  const onKey = (event: React.KeyboardEvent<HTMLElement>) => {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
    const links = Array.from(document.querySelectorAll<HTMLElement>('.nav a'));
    const index = links.indexOf(document.activeElement as HTMLElement);
    event.preventDefault();
    const next =
      event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? links.length - 1
          : event.key === 'ArrowDown'
            ? (index + 1) % links.length
            : (index - 1 + links.length) % links.length;
    links[next]?.focus();
  };
  const initials = displayName
    .trim()
    .split(/\s+/)
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="workspace">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      {open && <button className="sidebar-backdrop" aria-label="Close menu" onClick={() => setOpen(false)} />}
      <aside className={`sidebar ${open ? 'open' : ''}`}>
        <div className="brand">
          <img className="brandmark" src="/brand/t-mark.svg" alt="" />
          <span className="brandword">TANTARA</span>
        </div>
        <nav className="nav" aria-label="Main navigation" onKeyDown={onKey}>
          {navItems.map(({ href, label, Icon }) => (
            <Link
              key={href}
              href={href}
              aria-current={
                path === href ||
                (href === '/cases' && path.startsWith('/cases/')) ||
                (href === '/clients' && path.startsWith('/clients/')) ||
                (href === '/community' && path.startsWith('/community/')) ||
                (href === '/settings/profile' && path.startsWith('/settings/'))
                  ? 'page'
                  : undefined
              }
              className={href === '/settings/profile' ? 'settings-link' : undefined}
              onClick={() => setOpen(false)}
            >
              <Icon size={19} />
              {label}
            </Link>
          ))}
        </nav>
        <div className="sidebar-art">
          <div>
            <strong>
              Focused on
              <br />
              Arbitration Law
            </strong>
            <span className="sidebar-art-rule" aria-hidden="true" />
            <small>
              Smarter Tools.
              <br />
              Faster Resolution.
            </small>
          </div>
        </div>
      </aside>
      <button className="mobile-toggle" aria-label="Open navigation" onClick={() => setOpen(true)}>
        <Menu size={19} />
      </button>
      <header className="topbar">
        <button
          aria-label="Open global search"
          className="mobile-toggle search-toggle"
          onClick={() => setPalette(true)}
        >
          <Search size={17} />
        </button>
        <button className="searchbox" onClick={() => setPalette(true)} aria-label="Site search">
          <Search size={16} />
          <span>Search arbitration cases, documents, provisions, or ask TANTARA…</span>
          <span className="search-submit">
            <Search size={17} />
          </span>
        </button>
        <div className="shell-notifications">
          <button
            aria-label="Recent activity"
            aria-expanded={notifications}
            onClick={() => void showNotifications()}
          >
            <Bell size={19} />
          </button>
          {notifications && (
            <div className="notification-pop">
              <strong>Recent activity</strong>
              {noticeItems.length ? (
                noticeItems.slice(0, 5).map((item) => (
                  <div key={item.id}>
                    {item.title}
                    <small>{item.at}</small>
                  </div>
                ))
              ) : (
                <p className="muted">No recent activity.</p>
              )}
            </div>
          )}
        </div>
        <div className="user-menu">
          <button onClick={() => setProfile(!profile)} aria-expanded={profile} aria-label="Account menu">
            <span className="user-avatar">{initials || '—'}</span>
            <span className="user-caption">
              <strong>{displayName || (authReady && authError ? 'Signed out' : 'Signing in…')}</strong>
              <small>{displayEmail || displayRole || (authError ? 'Authentication unavailable' : '—')}</small>
            </span>
            <ChevronDown size={14} />
          </button>
          {profile && (
            <div className="profile-pop">
              <Link href="/settings/profile">Profile</Link>
              <Link href="/settings/profile">Settings</Link>
              <button
                onClick={() => {
                  clearToken();
                  router.push('/');
                  toast.success('Signed out');
                }}
              >
                Sign out
              </button>
            </div>
          )}
        </div>
      </header>
      <main id="main" className="main">
        {authReady ? (
          authError ? (
            <div className="card shell-auth-error">Signed out. Please sign in to open your workspace.</div>
          ) : (
            children
          )
        ) : (
          <div className="card shell-auth-error">Opening your workspace…</div>
        )}
      </main>
      <Dialog.Root open={palette} onOpenChange={setPalette}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-backdrop" />
          <Dialog.Content className="dialog">
            <Dialog.Title className="sr-only">Global search</Dialog.Title>
            <div className="shell-search-row">
              <Command size={18} />
              <input
                ref={input}
                value={q}
                onChange={(event) => void search(event.target.value)}
                aria-label="Search cases and documents"
                placeholder="Search cases and documents…"
              />
              <button onClick={() => setPalette(false)} aria-label="Close">
                <X size={17} />
              </button>
            </div>
            {offline ? (
              <div className="offline shell-search-feedback">Backend not reachable</div>
            ) : busy ? (
              <p className="muted">Searching…</p>
            ) : hits.length > 0 ? (
              <div className="shell-search-results">
                {hits.map((hit, index) => (
                  <Link key={index} href={hit.href} onClick={() => setPalette(false)}>
                    <span>{hit.title}</span>
                    <small className="muted">
                      {hit.kind}
                      <ArrowRight size={12} />
                    </small>
                  </Link>
                ))}
              </div>
            ) : q.length > 1 ? (
              <p className="muted">No matching records. Try another search.</p>
            ) : (
              <p className="muted">Type to search your cases and documents. Press Esc to close.</p>
            )}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
