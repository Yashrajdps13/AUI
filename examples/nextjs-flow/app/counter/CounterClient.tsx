'use client';

import { useState } from 'react';

export default function CounterClient() {
  const [count, setCount] = useState(0);

  return (
    <div className="glass-card" style={{ maxWidth: '480px', width: '100%', display: 'flex', flexDirection: 'column', gap: '1.5rem', textAlign: 'center' }}>
      <div>
        <h1 className="gradient-text" style={{ fontSize: '2.5rem', marginBottom: '0.5rem' }}>Counter State</h1>
        <p style={{ color: '#94a3b8', fontSize: '0.95rem' }}>
          This Client Component has an instrumented <code>count</code> state slot that the agent can read and write.
        </p>
      </div>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '2rem',
          margin: '1rem 0',
          padding: '1.5rem',
          background: 'rgba(0, 0, 0, 0.2)',
          borderRadius: '12px',
          border: '1px solid var(--border)'
        }}
      >
        <button
          id="counter-decrement"
          onClick={() => setCount((c) => c - 1)}
          style={{
            fontSize: '1.5rem',
            width: '3.5rem',
            height: '3.5rem',
            background: 'var(--secondary)',
            color: '#fff',
            border: '1px solid var(--border)',
            borderRadius: '10px'
          }}
        >
          −
        </button>
        
        <span
          id="counter-value"
          style={{
            fontSize: '3.5rem',
            fontWeight: 700,
            minWidth: '5rem',
            color: '#ffffff',
            fontVariantNumeric: 'tabular-nums'
          }}
        >
          {count}
        </span>
        
        <button
          id="counter-increment"
          onClick={() => setCount((c) => c + 1)}
          style={{
            fontSize: '1.5rem',
            width: '3.5rem',
            height: '3.5rem',
            background: 'var(--primary)',
            color: '#fff',
            borderRadius: '10px'
          }}
        >
          +
        </button>
      </div>

      <p style={{ fontSize: '0.85rem', color: '#64748b' }}>
        Observe the value incrementing live on the backend terminal or on the watch overlay.
      </p>
    </div>
  );
}
