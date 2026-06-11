'use client';

import { useState } from 'react';
import Link from 'next/link';

export default function HomePage() {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [instrumentationDummy, setInstrumentationDummy] = useState(0);

  return (
    <main style={{ padding: '4rem 2rem', maxWidth: '800px', margin: '0 auto', flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
      <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <header style={{ borderBottom: '1px solid var(--border)', paddingBottom: '1.5rem' }}>
          <h1 className="gradient-text" style={{ fontSize: '3rem', marginBottom: '0.5rem' }}>Next.js App Router Bridge</h1>
          <p style={{ color: '#94a3b8', fontSize: '1.1rem' }}>
            A premium showcase demonstrating react-agent-bridge component instrumentation, page routing, and safety rule enforcement in Next.js.
          </p>
        </header>

        <div>
          <h2 style={{ fontSize: '1.5rem', marginBottom: '1rem', color: '#f8fafc' }}>Available Walkthroughs</h2>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', marginTop: '0.5rem' }}>
            <div style={{ background: 'rgba(255, 255, 255, 0.02)', border: '1px solid var(--border)', padding: '1.5rem', borderRadius: '12px', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <h3 style={{ color: '#fff' }}>1. State Counter</h3>
              <p style={{ fontSize: '0.9rem', color: '#94a3b8' }}>
                A mutable counter component that translates state setters into bridge state slots.
              </p>
              <Link href="/counter" id="link-counter" style={{ display: 'inline-block', alignSelf: 'flex-start', background: 'var(--primary)', color: '#fff', padding: '0.5rem 1rem', borderRadius: '6px', fontWeight: 500 }}>
                Explore Counter →
              </Link>
            </div>

            <div style={{ background: 'rgba(255, 255, 255, 0.02)', border: '1px solid var(--border)', padding: '1.5rem', borderRadius: '12px', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <h3 style={{ color: '#fff' }}>2. Read-Only Rate</h3>
              <p style={{ fontSize: '0.9rem', color: '#94a3b8' }}>
                A write-protected slot annotated with <code>@writeable user</code>. Direct API writes are blocked by the safety engine.
              </p>
              <Link href="/readonly" id="link-readonly" style={{ display: 'inline-block', alignSelf: 'flex-start', background: 'var(--secondary)', color: '#fff', padding: '0.5rem 1rem', borderRadius: '6px', fontWeight: 500, border: '1px solid var(--border)' }}>
                Explore Protection →
              </Link>
            </div>
          </div>
        </div>

        <footer style={{ marginTop: '1rem', borderTop: '1px solid var(--border)', paddingTop: '1.5rem', display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', color: '#64748b' }}>
          <span>React Bridge active: localhost:8000</span>
          <span>Babel compile-time instrumentation</span>
        </footer>
      </div>
    </main>
  );
}
