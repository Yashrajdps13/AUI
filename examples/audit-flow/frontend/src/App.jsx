import React, { useState, useEffect } from 'react';
import { createStore } from 'zustand';
import { bridgeZustand, CommandAuditLogger } from 'react-agent-bridge';

// Create a Zustand store to demonstrate action calls and state slot logging
const authStore = createStore((set) => ({
  token: '',
  setToken: (token) => set({ token }),
  login: async (username, password) => {
    // Simulate async network request
    await new Promise((resolve) => setTimeout(resolve, 1000));
    set({ token: 'jwt_' + Math.random().toString(36).substring(7) });
    return { success: true };
  }
}));

// Bridge the Zustand store. 'token' is marked as sensitive.
bridgeZustand('AuthStore', authStore, {
  sensitiveKeys: ['token']
});

export default function App() {
  // State slots with standard React hooks.
  /**
   * The username input field. Set this to the user's login username.
   */
  const [username, setUsername] = useState('agent_user');
  
  /**
   * The social security number input field. Set this to verify user identity.
   * @sensitive
   */
  const [ssn, setSsn] = useState('');

  const [auditLog, setAuditLog] = useState([]);

  // Poll CommandAuditLogger for updates to show live entries in the UI
  useEffect(() => {
    const timer = setInterval(() => {
      setAuditLog(CommandAuditLogger.getAuditLog());
    }, 500);
    return () => clearInterval(timer);
  }, []);

  const handleClear = () => {
    CommandAuditLogger.clear();
    setAuditLog([]);
  };

  const handleFormSubmit = (e) => {
    e.preventDefault();
    console.log(`Form submitted locally! Username: ${username}`);
  };

  return (
    <div className="container">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=JetBrains+Mono:wght@400;700&display=swap');
        
        * {
          box-sizing: border-box;
          margin: 0;
          padding: 0;
        }

        body {
          background: radial-gradient(circle at 50% 50%, #0f1026 0%, #05050f 100%);
          color: #e0e0f8;
          font-family: 'Outfit', sans-serif;
          min-height: 100vh;
          display: flex;
          justify-content: center;
          align-items: center;
          padding: 2rem;
        }

        .container {
          width: 100%;
          max-width: 1100px;
          display: flex;
          flex-direction: column;
          gap: 2rem;
        }

        .header {
          text-align: center;
          margin-bottom: 1rem;
        }

        .header h1 {
          font-size: 2.8rem;
          font-weight: 800;
          background: linear-gradient(135deg, #a855f7 0%, #3b82f6 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          margin-bottom: 0.5rem;
          letter-spacing: -0.03em;
        }

        .header p {
          color: #94a3b8;
          font-size: 1.1rem;
        }

        .grid {
          display: grid;
          grid-template-columns: 1fr 1.2fr;
          gap: 2rem;
        }

        @media (max-width: 850px) {
          .grid {
            grid-template-columns: 1fr;
          }
        }

        .card {
          background: rgba(17, 18, 36, 0.45);
          backdrop-filter: blur(16px);
          -webkit-backdrop-filter: blur(16px);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 20px;
          padding: 2rem;
          box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        }

        .card-title {
          font-size: 1.4rem;
          font-weight: 600;
          margin-bottom: 1.5rem;
          display: flex;
          justify-content: space-between;
          align-items: center;
          color: #a855f7;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          padding-bottom: 0.75rem;
        }

        .form-group {
          margin-bottom: 1.25rem;
        }

        .form-group label {
          display: block;
          margin-bottom: 0.5rem;
          font-size: 0.9rem;
          color: #94a3b8;
        }

        .form-control {
          width: 100%;
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 10px;
          padding: 0.75rem 1rem;
          color: #fff;
          font-family: inherit;
          font-size: 1rem;
          transition: border-color 0.2s, box-shadow 0.2s;
        }

        .form-control:focus {
          outline: none;
          border-color: #3b82f6;
          box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.25);
        }

        .sensitive-badge {
          background: rgba(239, 68, 68, 0.15);
          border: 1px solid rgba(239, 68, 68, 0.3);
          color: #f87171;
          padding: 0.15rem 0.4rem;
          border-radius: 4px;
          font-size: 0.7rem;
          margin-left: 0.5rem;
          vertical-align: middle;
          text-transform: uppercase;
          font-weight: 600;
        }

        .btn {
          width: 100%;
          background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
          border: none;
          color: white;
          padding: 0.75rem 1.5rem;
          font-family: inherit;
          font-size: 1rem;
          font-weight: 600;
          border-radius: 10px;
          cursor: pointer;
          transition: filter 0.2s, transform 0.1s;
          box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
        }

        .btn:hover {
          filter: brightness(1.1);
        }

        .btn:active {
          transform: translateY(1px);
        }

        .btn-clear {
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.15);
          color: #94a3b8;
          font-size: 0.85rem;
          padding: 0.4rem 0.8rem;
          border-radius: 8px;
          width: auto;
          cursor: pointer;
          transition: all 0.2s;
          box-shadow: none;
        }

        .btn-clear:hover {
          background: rgba(239, 68, 68, 0.15);
          border-color: rgba(239, 68, 68, 0.4);
          color: #ef4444;
        }

        .log-list {
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
          max-height: 400px;
          overflow-y: auto;
          padding-right: 0.5rem;
        }

        .log-list::-webkit-scrollbar {
          width: 6px;
        }

        .log-list::-webkit-scrollbar-thumb {
          background: rgba(255, 255, 255, 0.15);
          border-radius: 3px;
        }

        .log-entry {
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 10px;
          padding: 0.75rem 1rem;
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.85rem;
          position: relative;
        }

        .log-header {
          display: flex;
          justify-content: space-between;
          margin-bottom: 0.35rem;
          font-size: 0.8rem;
        }

        .log-badge {
          padding: 0.1rem 0.35rem;
          border-radius: 4px;
          font-size: 0.7rem;
          font-weight: 700;
          text-transform: uppercase;
        }

        .log-badge.success {
          background: rgba(34, 197, 94, 0.15);
          border: 1px solid rgba(34, 197, 94, 0.3);
          color: #4ade80;
        }

        .log-badge.failed {
          background: rgba(239, 68, 68, 0.15);
          border: 1px solid rgba(239, 68, 68, 0.3);
          color: #f87171;
        }

        .log-timestamp {
          color: #64748b;
        }

        .log-details {
          color: #cbd5e1;
          word-break: break-all;
        }

        .log-target {
          color: #60a5fa;
        }

        .log-value {
          color: #a78bfa;
        }

        .log-error {
          color: #f87171;
          margin-top: 0.25rem;
          font-size: 0.8rem;
          border-top: 1px dashed rgba(239, 68, 68, 0.2);
          padding-top: 0.25rem;
        }

        .empty-logs {
          text-align: center;
          color: #64748b;
          font-style: italic;
          padding: 3rem 0;
        }
      `}</style>

      <div className="header">
        <h1>Command Audit Log Playground</h1>
        <p>Demonstrating Structured, Append-Only Mutation Logging with PII Redaction</p>
      </div>

      <div className="grid">
        {/* Left Side: Form & Interaction */}
        <div className="card">
          <div className="card-title">
            <span>AuditFormComponent</span>
          </div>

          <form onSubmit={handleFormSubmit}>
            <div className="form-group">
              <label htmlFor="username">Username</label>
              <input
                type="text"
                id="username"
                className="form-control"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label htmlFor="ssn">
                Social Security Number (SSN)
                <span className="sensitive-badge">Sensitive</span>
              </label>
              <input
                type="password"
                id="ssn"
                className="form-control"
                value={ssn}
                onChange={(e) => setSsn(e.target.value)}
                placeholder="--- --- ----"
              />
            </div>

            <button type="submit" id="btn-submit" className="btn">
              Submit Form
            </button>
          </form>
        </div>

        {/* Right Side: Command Audit Log Display */}
        <div className="card">
          <div className="card-title">
            <span>Browser Audit Log (Developer Console)</span>
            <button className="btn-clear" onClick={handleClear}>
              Clear Logs
            </button>
          </div>

          <div className="log-list">
            {auditLog.length === 0 ? (
              <div className="empty-logs">No agent commands recorded yet. Run agent commands to populate.</div>
            ) : (
              [...auditLog].reverse().map((entry, index) => (
                <div key={entry.commandId + '-' + index} className="log-entry">
                  <div className="log-header">
                    <span className={`log-badge ${entry.success ? 'success' : 'failed'}`}>
                      {entry.success ? 'Success' : 'Failed'}
                    </span>
                    <span className="log-timestamp">
                      {new Date(entry.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                  <div className="log-details">
                    <strong>CMD:</strong> {entry.type} |{' '}
                    <strong>Target:</strong> <span className="log-target">{entry.target}</span> |{' '}
                    <strong>Value:</strong> <span className="log-value">{JSON.stringify(entry.value)}</span>
                  </div>
                  {!entry.success && entry.error && (
                    <div className="log-error">Error: {entry.error}</div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
