'use client';
import { useState } from 'react';
import Link from 'next/link';
import { Eye, EyeOff, ArrowRight, BookOpen, FileText, BriefcaseBusiness, Users } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import { endpoints } from '@/lib/api/endpoints';
import { persistToken } from '@/lib/api/client';
const schema = z.object({
  email: z.string().email('Enter a valid email address'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
});
type Form = z.infer<typeof schema>;
export default function Home() {
  const [show, setShow] = useState(false),
    [busy, setBusy] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: { email: 'advocate@tantara.local', password: '' },
  });
  const submit = handleSubmit(async (values) => {
    setBusy(true);
    try {
      const r = await endpoints.login(values);
      persistToken(r.access_token);
      toast.success('Welcome to TANTARA');
      window.location.assign('/dashboard');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Unable to sign in');
    } finally {
      setBusy(false);
    }
  });
  return (
    <main className="home-layout">
      <section className="hero">
        <div className="hero-content">
          <div className="hero-welcome">Welcome to</div>
          <h1 style={{ letterSpacing: '.18em', marginTop: 8 }}>
            <img className="brandmark" src="/brand/t-mark.svg" alt="" /> TANTARA
          </h1>
          <p>
            AI-Powered Legal Workspace
            <br />
            for Arbitration Law
          </p>
          <div className="hero-actions">
            <a href="#login" className="primary">
              Continue as Advocate <ArrowRight size={16} />
            </a>
          </div>
        </div>
        <div className="home-tiles">
          {[
            [BookOpen, 'Research'],
            [FileText, 'Draft'],
            [BriefcaseBusiness, 'Manage Cases'],
            [Users, 'Community Support'],
          ].map(([I, label]: any) => (
            <div key={label}>
              <span className="icon-tile">
                <I size={20} />
              </span>
              {label}
            </div>
          ))}
        </div>
      </section>
      <section className="card login-card" id="login">
        <div className="brand" style={{ padding: 0, color: '#0f172a' }}>
          <img className="brandmark" src="/brand/t-mark.svg" alt="" />
          <span className="brandword" style={{ color: '#0f172a' }}>
            TANTARA
          </span>
        </div>
        <div className="separator" />
        <h2 style={{ fontSize: 22, margin: '0 0 6px' }}>Sign in to your workspace</h2>
        <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
          Continue your arbitration work securely.
        </p>
        <form onSubmit={submit} noValidate>
          <div className="field">
            <label htmlFor="email">Email address</label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              aria-invalid={Boolean(errors.email)}
              aria-describedby={errors.email ? 'email-error' : undefined}
              suppressHydrationWarning
              {...register('email')}
            />
            {errors.email && (
              <small id="email-error" style={{ color: '#be123c' }}>
                {errors.email.message}
              </small>
            )}
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <div className="password-field">
              <input
                id="password"
                type={show ? 'text' : 'password'}
                autoComplete="current-password"
                aria-invalid={Boolean(errors.password)}
                aria-describedby={errors.password ? 'password-error' : undefined}
                suppressHydrationWarning
                className="login-password"
                {...register('password')}
              />
              <button
                type="button"
                aria-label={show ? 'Hide password' : 'Show password'}
                onClick={() => setShow(!show)}
              >
                {show ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
            </div>
            {errors.password && (
              <small id="password-error" style={{ color: '#be123c' }}>
                {errors.password.message}
              </small>
            )}
          </div>
          <button className="primary" style={{ width: '100%', marginTop: 8, minHeight: 44 }} disabled={busy}>
            {busy ? 'Signing in…' : 'Continue as Advocate'} <ArrowRight size={16} />
          </button>
        </form>
        <div
          style={{
            marginTop: 22,
            padding: 12,
            background: '#f7f8fb',
            borderRadius: 9,
            fontSize: 11,
            color: '#64748b',
          }}
        >
          <strong style={{ color: '#334155' }}>Local development account</strong>
          <br />
          advocate@tantara.local · tantara-local
        </div>
        <p style={{ fontSize: 12, lineHeight: 1.5, color: '#64748b', marginTop: 18 }}>
          For legal research assistance only. Verify all authorities and advice against primary sources.
        </p>
      </section>
    </main>
  );
}
