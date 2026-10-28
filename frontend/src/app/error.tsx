'use client';
export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main
      style={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        padding: 24,
        background: '#f6f7f9',
      }}
    >
      <section className="card" style={{ maxWidth: 520, padding: 28 }}>
        <h1 className="title">Something went wrong</h1>
        <p className="muted">The workspace could not render this page. You can try again.</p>
        <button className="primary" onClick={reset}>
          Try again
        </button>
      </section>
    </main>
  );
}
