'use client';

import { useEffect, useState, useRef } from 'react';
import { useIsAgentConnected } from 'react-agent-bridge';

interface LogEntry {
  id: string;
  time: string;
  component: string;
  slot: string;
  oldVal: string;
  newVal: string;
}

export default function StateWatchTerminal() {
  const isConnected = useIsAgentConnected();
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [minimized, setMinimized] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Register listener for state transitions
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const handleStateUpdate = (event: any) => {
      const { target, value } = event.detail;
      const parts = target.split('.');
      if (parts.length === 2) {
        const [comp, slot] = parts;
        // Skip env context logs to keep clean
        if (comp === '__context__#env') return;

        const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        
        setLogs((prev) => {
          // Find matching slot if any to get previous value
          const lastEntry = [...prev].reverse().find(e => e.component === comp && e.slot === slot);
          const oldVal = lastEntry ? lastEntry.newVal : '—';
          
          // Prevent log spam for identical values
          if (oldVal === String(value)) return prev;

          return [
            ...prev,
            {
              id: Math.random().toString(36).substring(7),
              time: timestamp,
              component: comp.split('#')[0], // strip unique react id suffix
              slot,
              oldVal,
              newVal: String(value)
            }
          ].slice(-50); // limit to last 50 logs
        });
      }
    };

    window.addEventListener('react-agent-bridge:state-update', handleStateUpdate);

    return () => {
      window.removeEventListener('react-agent-bridge:state-update', handleStateUpdate);
    };
  }, []);

  // Autoscroll logs
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  return (
    <div
      style={{
        position: 'fixed',
        bottom: '1.5rem',
        right: '1.5rem',
        width: minimized ? '220px' : '400px',
        height: minimized ? '45px' : '300px',
        background: 'rgba(15, 23, 42, 0.95)',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        borderRadius: '12px',
        boxShadow: '0 12px 40px rgba(0, 0, 0, 0.5)',
        zIndex: 9999,
        fontFamily: 'monospace',
        fontSize: '0.85rem',
        color: '#e2e8f0',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
        backdropFilter: 'blur(8px)'
      }}
    >
      {/* Title Header */}
      <div
        onClick={() => setMinimized(!minimized)}
        style={{
          padding: '0.75rem 1rem',
          background: 'rgba(30, 41, 59, 0.5)',
          borderBottom: minimized ? 'none' : '1px solid rgba(255, 255, 255, 0.08)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          cursor: 'pointer',
          userSelect: 'none'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600 }}>
          <span
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              background: isConnected ? '#10b981' : '#ef4444',
              boxShadow: isConnected ? '0 0 8px #10b981' : '0 0 8px #ef4444'
            }}
          />
          <span>AUI WATCH</span>
        </div>
        <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
          {isConnected ? 'AGENT ACTIVE' : 'NO AGENT'}
        </div>
      </div>

      {/* Logs Console body */}
      {!minimized && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          <div style={{ flex: 1, padding: '1rem', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {logs.length === 0 ? (
              <div style={{ color: '#64748b', fontStyle: 'italic', textAlign: 'center', marginTop: '4rem' }}>
                Waiting for state changes...
              </div>
            ) : (
              logs.map((log) => (
                <div key={log.id} style={{ display: 'flex', flexDirection: 'column', borderLeft: '2px solid #6366f1', paddingLeft: '0.5rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: '#94a3b8', marginBottom: '0.1rem' }}>
                    <span>[{log.time}] {log.component}</span>
                  </div>
                  <div>
                    <span style={{ color: '#38bdf8' }}>{log.slot}</span>:{' '}
                    <span style={{ color: '#f43f5e', textDecoration: 'line-through' }}>{log.oldVal}</span>{' '}
                    <span style={{ color: '#10b981' }}>➜</span>{' '}
                    <span style={{ color: '#10b981', fontWeight: 600 }}>{log.newVal}</span>
                  </div>
                </div>
              ))
            )}
            <div ref={logEndRef} />
          </div>
          {/* Action Footer */}
          <div style={{ padding: '0.5rem 1rem', background: 'rgba(0, 0, 0, 0.2)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.75rem', color: '#64748b' }}>
            <span>ws://localhost:8000</span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                setLogs([]);
              }}
              style={{ background: 'transparent', color: '#ef4444', border: 'none', cursor: 'pointer', fontSize: '0.75rem' }}
            >
              Clear Logs
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
