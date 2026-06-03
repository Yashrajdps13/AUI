import { useState } from 'react';
import { useIsAgentConnected } from 'react-agent-bridge';

function FormComponent() {
  /**
   * @description The user's input email address for registering.
   */
  const [email, setEmail] = useState('');

  /**
   * @description Public notes submitted along with the form.
   */
  const [notes, setNotes] = useState('');

  return (
    <div className="section">
      <div className="section-title">Public Registration Form (Allowlisted Component)</div>
      <div className="form-group">
        <label htmlFor="input-email">Email Address</label>
        <input
          id="input-email"
          type="text"
          className="form-input"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>
      <div className="form-group">
        <label htmlFor="input-notes">Public Notes</label>
        <textarea
          id="input-notes"
          className="form-input"
          style={{ minHeight: '60px', resize: 'vertical' }}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </div>
      <div className="info-row">
        <span className="info-label">Active Values:</span>
        <span className="info-value" style={{ fontSize: '12px' }}>
          email="{email}", notes="{notes}"
        </span>
      </div>
    </div>
  );
}

function AdminPanel() {
  /**
   * @description Boolean flag to elevate user profile to global system administrator.
   */
  const [isAdmin, setIsAdmin] = useState(false);

  /**
   * @description Master passcode required to access restricted database queries.
   * @sensitive
   */
  const [adminCode, setAdminCode] = useState('');

  return (
    <div className="section" style={{ borderColor: isAdmin ? '#f59e0b' : 'rgba(239, 68, 68, 0.2)' }}>
      <div className="section-title" style={{ color: isAdmin ? '#f59e0b' : '#ef4444' }}>
        Restricted Administrative Console (Blocked Target)
      </div>

      <div className="state-row">
        <span className="state-label">Admin Status:</span>
        <span className={`status-badge ${isAdmin ? 'status-badge-admin' : 'status-badge-restricted'}`} id="val-admin-status">
          {isAdmin ? 'System Administrator' : 'Restricted Guest'}
        </span>
      </div>

      <div className="form-group">
        <label htmlFor="input-code">Admin Password</label>
        <input
          id="input-code"
          type="password"
          className="form-input"
          placeholder="Requires admin privilege"
          value={adminCode}
          onChange={(e) => setAdminCode(e.target.value)}
        />
      </div>

      <div className="btn-group">
        <button
          className="btn btn-danger"
          style={{ width: '100%' }}
          onClick={() => setIsAdmin(true)}
          id="btn-escalate"
        >
          Elevate to Admin Privilege
        </button>
      </div>
    </div>
  );
}

export default function App() {
  const isAgentConnected = useIsAgentConnected();

  return (
    <div className="container">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
          background: #090a0f;
          color: #e2e8f0;
          font-family: 'Outfit', sans-serif;
          min-height: 100vh;
          display: flex;
          justify-content: center;
          align-items: center;
          padding: 20px;
        }
        .container {
          background: #11131c;
          border: 1px solid ${isAgentConnected ? '#10b981' : 'rgba(255, 255, 255, 0.08)'};
          border-radius: 24px;
          padding: 35px;
          max-width: 500px;
          width: 100%;
          box-shadow: 0 20px 50px rgba(0,0,0,0.5), 0 0 40px ${isAgentConnected ? 'rgba(16, 185, 129, 0.12)' : 'rgba(0,0,0,0)'};
          transition: all 0.4s ease;
          position: relative;
        }
        
        h2 {
          font-size: 26px;
          margin-bottom: 5px;
          background: linear-gradient(135deg, #34d399 0%, #10b981 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
        }
        .subtitle {
          font-size: 14px;
          color: #64748b;
          margin-bottom: 25px;
        }
        .badge {
          display: inline-block;
          padding: 6px 12px;
          border-radius: 20px;
          font-size: 12px;
          font-weight: 600;
          margin-bottom: 25px;
        }
        .badge-active {
          background: rgba(16, 185, 129, 0.1);
          border: 1px solid #10b981;
          color: #34d399;
        }
        .badge-inactive {
          background: rgba(244, 63, 94, 0.1);
          border: 1px solid #f43f5e;
          color: #fb7185;
        }
        .section {
          background: rgba(255, 255, 255, 0.01);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 16px;
          padding: 20px;
          margin-bottom: 20px;
          transition: all 0.3s ease;
        }
        .section-title {
          font-size: 12px;
          font-weight: 800;
          text-transform: uppercase;
          color: #34d399;
          letter-spacing: 1px;
          margin-bottom: 15px;
        }
        .form-group {
          margin-bottom: 15px;
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        label {
          font-size: 13px;
          color: #64748b;
        }
        .form-input {
          width: 100%;
          padding: 10px;
          background: rgba(255, 255, 255, 0.04);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 8px;
          color: white;
          outline: none;
          font-family: inherit;
        }
        .form-input:focus {
          border-color: #10b981;
        }
        .info-row {
          display: flex;
          justify-content: space-between;
          font-size: 13px;
          color: #64748b;
          margin-top: 10px;
        }
        .state-row {
          display: flex;
          justify-content: space-between;
          margin-bottom: 15px;
          align-items: center;
        }
        .state-label {
          font-size: 14px;
          color: #94a3b8;
        }
        .status-badge {
          padding: 4px 10px;
          border-radius: 6px;
          font-size: 12px;
          font-weight: 600;
        }
        .status-badge-restricted {
          background: rgba(239, 68, 68, 0.1);
          color: #fb7185;
          border: 1px solid rgba(239, 68, 68, 0.3);
        }
        .status-badge-admin {
          background: rgba(245, 158, 11, 0.1);
          color: #fbbf24;
          border: 1px solid #d97706;
        }
        .btn {
          padding: 10px 15px;
          border-radius: 8px;
          font-weight: 600;
          cursor: pointer;
          font-family: inherit;
          border: none;
          transition: all 0.2s ease;
        }
        .btn-danger {
          background: rgba(239, 68, 68, 0.15);
          border: 1px solid #ef4444;
          color: #fca5a5;
        }
        .btn-danger:hover {
          background: rgba(239, 68, 68, 0.25);
        }
      `}</style>

      <h2>Write Security Scope</h2>
      <div className="subtitle">Option 2 — Client-Defined Mutation Guards</div>
      <div className={`badge ${isAgentConnected ? 'badge-active' : 'badge-inactive'}`}>
        {isAgentConnected ? '● Agent Connected' : '○ Offline'}
      </div>

      <FormComponent />
      <AdminPanel />
    </div>
  );
}
