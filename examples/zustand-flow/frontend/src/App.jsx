import React, { useState } from 'react';
import { useUserStore } from './store.js';
import { useIsAgentConnected } from 'react-agent-bridge';

export default function App() {
  const { username, token, count, login, logout, increment } = useUserStore();
  const isAgentConnected = useIsAgentConnected();

  // Local state for manual input controls
  const [inputUser, setInputUser] = useState('');
  const [inputToken, setInputToken] = useState('');

  const handleManualLogin = () => {
    if (!inputUser.trim() || !inputToken.trim()) return;
    login(inputUser, inputToken);
    setInputUser('');
    setInputToken('');
  };

  return (
    <div className="container">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
          background: #0b0c10;
          color: #c5c6c7;
          font-family: 'Outfit', sans-serif;
          min-height: 100vh;
          display: flex;
          justify-content: center;
          align-items: center;
          padding: 20px;
        }
        .container {
          background: #1f2833;
          border: 1px solid ${isAgentConnected ? '#66fcf1' : 'rgba(255, 255, 255, 0.08)'};
          border-radius: 20px;
          padding: 30px;
          max-width: 500px;
          width: 100%;
          box-shadow: 0 10px 30px rgba(0,0,0,0.5), 0 0 30px ${isAgentConnected ? 'rgba(102, 252, 241, 0.15)' : 'rgba(0,0,0,0)'};
          transition: all 0.4s ease;
          position: relative;
        }
        
        h2 {
          font-size: 26px;
          margin-bottom: 5px;
          background: linear-gradient(135deg, #66fcf1 0%, #45f3ff 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
        }
        .subtitle {
          font-size: 14px;
          color: #85929E;
          margin-bottom: 20px;
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
          background: rgba(102, 252, 241, 0.1);
          border: 1px solid #66fcf1;
          color: #66fcf1;
        }
        .badge-inactive {
          background: rgba(244, 63, 94, 0.1);
          border: 1px solid #f43f5e;
          color: #fb7185;
        }
        .section {
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 12px;
          padding: 15px;
          margin-bottom: 20px;
        }
        .section-title {
          font-size: 12px;
          font-weight: 800;
          text-transform: uppercase;
          color: #66fcf1;
          letter-spacing: 1px;
          margin-bottom: 10px;
        }
        .state-row {
          display: flex;
          justify-content: space-between;
          margin-bottom: 8px;
          font-size: 14px;
        }
        .state-label {
          color: #85929E;
        }
        .state-value {
          font-weight: 600;
          color: #ffffff;
        }
        .form-group {
          margin-bottom: 15px;
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        label {
          font-size: 13px;
          color: #85929E;
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
          border-color: #66fcf1;
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
        .btn-primary {
          background: #66fcf1;
          color: #0b0c10;
        }
        .btn-primary:hover {
          background: #45f3ff;
        }
        .btn-sec {
          background: rgba(255, 255, 255, 0.05);
          color: #ffffff;
          border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .btn-sec:hover {
          background: rgba(255, 255, 255, 0.1);
        }
        .btn-danger {
          background: rgba(244, 63, 94, 0.15);
          border: 1px solid #f43f5e;
          color: #fb7185;
        }
        .btn-danger:hover {
          background: rgba(244, 63, 94, 0.25);
        }
        .btn-group {
          display: flex;
          gap: 10px;
          margin-top: 10px;
        }
      `}</style>

      <h2>Zustand Flow</h2>
      <div className="subtitle">Global State Sync & Actions Demo</div>
      <div className={`badge ${isAgentConnected ? 'badge-active' : 'badge-inactive'}`}>
        {isAgentConnected ? '● Agent Connected' : '○ Offline'}
      </div>

      <div className="section">
        <div className="section-title">Store Values (UserStore)</div>
        <div className="state-row">
          <span className="state-label">username:</span>
          <span className="state-value" id="val-username">{username}</span>
        </div>
        <div className="state-row">
          <span className="state-label">token:</span>
          <span className="state-value" id="val-token" style={{ fontStyle: token ? 'normal' : 'italic' }}>
            {token ? `${token} (Agent sees [REDACTED])` : 'empty'}
          </span>
        </div>
        <div className="state-row">
          <span className="state-label">count:</span>
          <span className="state-value" id="val-count">{count}</span>
        </div>
      </div>

      <div className="section">
        <div className="section-title">Manual Controls</div>
        <div className="form-group">
          <label htmlFor="input-username">Username</label>
          <input
            id="input-username"
            type="text"
            className="form-input"
            value={inputUser}
            onChange={(e) => setInputUser(e.target.value)}
          />
        </div>
        <div className="form-group">
          <label htmlFor="input-token">Token</label>
          <input
            id="input-token"
            type="password"
            className="form-input"
            value={inputToken}
            onChange={(e) => setInputToken(e.target.value)}
          />
        </div>
        <div className="btn-group">
          <button className="btn btn-primary" onClick={handleManualLogin} id="btn-login">
            Login
          </button>
          <button className="btn btn-danger" onClick={logout} id="btn-logout">
            Logout
          </button>
          <button className="btn btn-sec" onClick={increment} id="btn-increment">
            Increment
          </button>
        </div>
      </div>
    </div>
  );
}
