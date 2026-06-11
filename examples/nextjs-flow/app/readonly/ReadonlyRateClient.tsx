'use client';

import { useState } from 'react';
import Link from 'next/link';

export default function ReadonlyRateClient() {
  /**
   * Computed task completion rate (0-100%).
   * @writeable user
   * @description Percentage of tasks completed in the current sprint
   */
  const [efficiencyRate, setEfficiencyRate] = useState(72);

  return (
    <div className="glass-card" style={{ maxWidth: '480px', width: '100%', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: '0.5rem' }}>
        <Link href="/" id="link-home" style={{ color: 'var(--accent)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 500 }}>
          <span>←</span> Back to Home
        </Link>
      </div>

      <div>
        <h1 className="gradient-text" style={{ fontSize: '2.5rem', marginBottom: '0.5rem' }}>Read-only Rate</h1>
        <p style={{ color: '#94a3b8', fontSize: '0.95rem' }}>
          The <code>efficiencyRate</code> slot is annotated with <code>@writeable user</code>. 
          Agents can observe it but direct writes via the API will be blocked.
        </p>
      </div>

      <div
        style={{
          padding: '1.5rem',
          background: 'rgba(0, 0, 0, 0.2)',
          borderRadius: '12px',
          border: '1px solid var(--border)',
          display: 'flex',
          flexDirection: 'column',
          gap: '1rem'
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 600 }}>
          <span>Efficiency Rate</span>
          <span id="rate-display" style={{ color: 'var(--accent)', fontSize: '1.25rem' }}>{efficiencyRate}%</span>
        </div>
        
        <input
          id="rate-slider"
          type="range"
          min={0}
          max={100}
          value={efficiencyRate}
          onChange={(e) => setEfficiencyRate(Number(e.target.value))}
          style={{ width: '100%', height: '6px', borderRadius: '3px' }}
        />
      </div>

      <p style={{ fontSize: '0.85rem', color: '#64748b', textAlign: 'center' }}>
        Try sliding the control manually to watch updates stream to the bridge.
      </p>
    </div>
  );
}
