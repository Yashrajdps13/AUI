'use client';

import { useState } from 'react';
import Link from 'next/link';

/**
 * ReadonlyRateClient demonstrates a @writeable user slot.
 *
 * The agent can observe the efficiencyRate value in real time but any
 * attempt to mutate it via setState will be blocked by the Rules Engine.
 */
export default function ReadonlyRateClient() {
  /**
   * Computed task completion rate (0–100%).
   * @writeable user
   * @description Percentage of tasks completed in the current sprint
   */
  const [efficiencyRate, setEfficiencyRate] = useState(72);

  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', padding: '2rem', maxWidth: '480px', margin: '0 auto' }}>
      <div style={{ marginBottom: '1.5rem' }}>
        <Link href="/" style={{ color: '#0070f3', textDecoration: 'none' }}>
          ← Back to Home
        </Link>
      </div>

      <h1>Read-only Rate</h1>
      <p style={{ color: '#555' }}>
        The <code>efficiencyRate</code> slot has a{' '}
        <code>@writeable user</code> annotation. Human users can change it; the
        agent can only read it.
      </p>

      <div
        style={{
          padding: '1.5rem',
          border: '1px solid #ddd',
          borderRadius: '8px',
          background: '#f9f9f9',
          marginTop: '1.5rem',
        }}
      >
        <label
          htmlFor="rate-slider"
          style={{ display: 'block', fontWeight: 600, marginBottom: '0.5rem' }}
        >
          Efficiency Rate: <span id="rate-display">{efficiencyRate}%</span>
        </label>
        <input
          id="rate-slider"
          type="range"
          min={0}
          max={100}
          value={efficiencyRate}
          onChange={(e) => setEfficiencyRate(Number(e.target.value))}
          style={{ width: '100%' }}
        />
      </div>

      <p style={{ marginTop: '1rem', fontSize: '0.875rem', color: '#666' }}>
        Run <code>react-agent-bridge registry</code> — you will see{' '}
        <em>writeable: "user"</em> on this slot, meaning the agent cannot mutate
        it.
      </p>
    </div>
  );
}
