'use client';

import { useState } from 'react';
import CounterClient from './CounterClient';
import Link from 'next/link';

export default function CounterPage() {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [instrumentationDummy, setInstrumentationDummy] = useState(0);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <div style={{ padding: '1.5rem 2rem', borderBottom: '1px solid var(--border)', background: 'rgba(30, 41, 59, 0.2)' }}>
        <div style={{ maxWidth: '800px', margin: '0 auto', display: 'flex', alignItems: 'center' }}>
          <Link href="/" id="link-home" style={{ color: 'var(--accent)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 500 }}>
            <span>←</span> Back to Home
          </Link>
        </div>
      </div>
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '2rem' }}>
        <CounterClient />
      </div>
    </div>
  );
}
