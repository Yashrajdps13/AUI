'use client';

import { useState } from 'react';

/**
 * CounterClient demonstrates a simple Client Component tracked by the agent.
 *
 * The Babel plugin detects the 'use client' directive and transforms the
 * useState call below into a useBridgeState call, registering the slot
 * with the component name 'CounterClient' and the key 'count'.
 *
 * You can verify this is registered by running:
 *   react-agent-bridge registry
 *
 * Expected output:
 *   CounterClient#<id>
 *     count  (number)  The current counter value
 */
export default function CounterClient() {
  /** The current counter value */
  const [count, setCount] = useState(0);

  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', padding: '2rem', maxWidth: '480px', margin: '0 auto' }}>
      <h1>Counter</h1>
      <p style={{ color: '#555' }}>
        This is a <strong>Client Component</strong>. The <code>count</code> state
        slot is tracked by the agent.
      </p>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '1rem',
          marginTop: '1.5rem',
          padding: '1.5rem',
          border: '1px solid #ddd',
          borderRadius: '8px',
          background: '#f9f9f9',
        }}
      >
        <button
          id="counter-decrement"
          onClick={() => setCount((c) => c - 1)}
          style={{ fontSize: '1.5rem', width: '2.5rem', height: '2.5rem', cursor: 'pointer', border: '1px solid #ccc', borderRadius: '4px', background: '#fff' }}
        >
          −
        </button>
        <span id="counter-value" style={{ fontSize: '2rem', fontWeight: 700, minWidth: '3rem', textAlign: 'center' }}>
          {count}
        </span>
        <button
          id="counter-increment"
          onClick={() => setCount((c) => c + 1)}
          style={{ fontSize: '1.5rem', width: '2.5rem', height: '2.5rem', cursor: 'pointer', border: '1px solid #ccc', borderRadius: '4px', background: '#fff' }}
        >
          +
        </button>
      </div>

      <p style={{ marginTop: '1rem', fontSize: '0.875rem', color: '#666' }}>
        Run <code>react-agent-bridge watch</code> and click the buttons to see
        live state changes streamed to the agent.
      </p>
    </div>
  );
}
