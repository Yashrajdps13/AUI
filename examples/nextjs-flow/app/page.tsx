/**
 * Home page — this is a Server Component.
 *
 * Notice there is no 'use client' directive. The Babel plugin will skip
 * this file entirely, and it will never appear in the agent's component
 * registry. Only Client Components with useState are tracked.
 */
import Link from 'next/link';

export default function HomePage() {
  return (
    <main style={{ fontFamily: 'system-ui, sans-serif', padding: '2rem', maxWidth: '640px', margin: '0 auto' }}>
      <h1>nextjs-flow</h1>
      <p>
        This is a <strong>Server Component</strong>. It has no <code>&#39;use client&#39;</code>{' '}
        directive, so the react-agent-bridge Babel plugin skips it completely.
        It will not appear in the agent registry.
      </p>

      <h2>Examples</h2>
      <ul>
        <li>
          <Link href="/counter">Counter (Client Component)</Link> — a{' '}
          <code>useState</code> counter slot that the agent can read and write.
        </li>
        <li>
          <Link href="/readonly">Read-only Rate (Client Component)</Link> — a{' '}
          <code>@writeable user</code> slot that the agent can observe but not
          mutate.
        </li>
      </ul>

      <p style={{ marginTop: '2rem', color: '#666', fontSize: '0.875rem' }}>
        Start the agent backend with{' '}
        <code>react-agent-bridge registry</code> to see the registered slots.
      </p>
    </main>
  );
}
