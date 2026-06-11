/**
 * Counter page — Server Component.
 *
 * This file itself has no 'use client' directive, so the Babel plugin skips
 * it. The actual interactive component (CounterClient) lives in its own file
 * and declares 'use client' at the top. This is the recommended App Router
 * pattern: push the Client Component boundary as far down as possible.
 */
import CounterClient from './CounterClient';
import Link from 'next/link';

export default function CounterPage() {
  return (
    <div>
      <div style={{ padding: '1rem 2rem', borderBottom: '1px solid #eee' }}>
        <Link href="/" style={{ color: '#0070f3', textDecoration: 'none' }}>
          ← Back to Home
        </Link>
      </div>
      <CounterClient />
    </div>
  );
}
