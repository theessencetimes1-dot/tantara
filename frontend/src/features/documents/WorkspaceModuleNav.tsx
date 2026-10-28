'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  CalendarDays,
  CheckCircle2,
  FileText,
  FolderOpen,
  House,
  Search,
  Settings,
  Users,
} from 'lucide-react';

const moduleLinks = [
  { href: '/dashboard', label: 'Dashboard', Icon: House },
  { href: '/cases', label: 'My Cases', Icon: FolderOpen },
  { href: '/search', label: 'Research Desk', Icon: Search },
  { href: '/documents', label: 'Documents', Icon: FileText },
  { href: '/calendar', label: 'Calendar', Icon: CalendarDays },
  { href: '/tasks', label: 'Tasks', Icon: CheckCircle2 },
  { href: '/clients', label: 'Clients', Icon: Users },
  { href: '/community', label: 'Community (Arbitration)', Icon: Users },
  { href: '/settings/profile', label: 'Settings', Icon: Settings },
];

export function WorkspaceModuleNav() {
  const pathname = usePathname();
  const [nav, setNav] = useState<HTMLElement | null>(null);

  useEffect(() => {
    setNav(document.querySelector<HTMLElement>('.sidebar .nav'));
  }, []);

  if (!nav) return null;
  return createPortal(
    <div className="documents-module-nav">
      {moduleLinks.map(({ href, label, Icon }) => (
        <Link
          key={href}
          href={href}
          aria-current={
            pathname === href || (href === '/documents' && pathname.startsWith('/documents/'))
              ? 'true'
              : undefined
          }
          onClick={() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))}
        >
          <Icon size={19} aria-hidden="true" />
          {label}
        </Link>
      ))}
    </div>,
    nav,
  );
}
