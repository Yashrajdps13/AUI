import { useState, useEffect } from 'react';
import { useIsAgentConnected } from 'react-agent-bridge';

export default function App() {
  /**
   * @description Indicates whether a background profile API/database load is in progress.
   */
  const [isLoading, setIsLoading] = useState(false);

  /**
   * @description The fetched user profile data, containing name, email, and role once loaded.
   */
  const [profile, setProfile] = useState(null);

  /**
   * @description Simple timer elapsed counter ticking every second.
   */
  const [secondsElapsed, setSecondsElapsed] = useState(0);

  const isAgentConnected = useIsAgentConnected();

  // Tick elapsed seconds
  useEffect(() => {
    const timer = setInterval(() => {
      setSecondsElapsed((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const handleSimulateLoad = () => {
    console.log('[App] Starting async load simulation (3 seconds)...');
    setIsLoading(true);
    setProfile(null);

    setTimeout(() => {
      console.log('[App] Async load completed successfully!');
      setProfile({
        name: 'Alice Smith',
        email: 'alice@example.com',
        role: 'Lead Architect',
      });
      setIsLoading(false);
    }, 3000);
  };

  const handleReset = () => {
    console.log('[App] Resetting profile state.');
    setProfile(null);
    setIsLoading(false);
  };

  return (
    <div className="container">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
          background: #0d0e15;
          color: #cbd5e1;
          font-family: 'Outfit', sans-serif;
          min-height: 100vh;
          display: flex;
          justify-content: center;
          align-items: center;
          padding: 20px;
        }
        .container {
          background: #151726;
          border: 1px solid ${isAgentConnected ? '#a855f7' : 'rgba(255, 255, 255, 0.08)'};
          border-radius: 24px;
          padding: 35px;
          max-width: 500px;
          width: 100%;
          box-shadow: 0 20px 50px rgba(0,0,0,0.5), 0 0 40px ${isAgentConnected ? 'rgba(168, 85, 247, 0.15)' : 'rgba(0,0,0,0)'};
          transition: all 0.4s ease;
          position: relative;
        }
        
        h2 {
          font-size: 26px;
          margin-bottom: 5px;
          background: linear-gradient(135deg, #c084fc 0%, #a855f7 100%);
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
          background: rgba(168, 85, 247, 0.1);
          border: 1px solid #a855f7;
          color: #c084fc;
        }
        .badge-inactive {
          background: rgba(244, 63, 94, 0.1);
          border: 1px solid #f43f5e;
          color: #fb7185;
        }
        .card {
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 16px;
          padding: 20px;
          margin-bottom: 25px;
        }
        .card-header {
          font-size: 11px;
          font-weight: 800;
          text-transform: uppercase;
          color: #c084fc;
          letter-spacing: 1px;
          margin-bottom: 15px;
          display: flex;
          justify-content: space-between;
        }
        .info-row {
          display: flex;
          justify-content: space-between;
          margin-bottom: 10px;
          font-size: 14px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.03);
          padding-bottom: 8px;
        }
        .info-row:last-child {
          border-bottom: none;
          padding-bottom: 0;
          margin-bottom: 0;
        }
        .info-label {
          color: #64748b;
        }
        .info-value {
          font-weight: 600;
          color: #f1f5f9;
        }
        .btn {
          width: 100%;
          padding: 12px 18px;
          border-radius: 12px;
          font-weight: 600;
          cursor: pointer;
          font-family: inherit;
          border: none;
          transition: all 0.2s ease;
          display: flex;
          justify-content: center;
          align-items: center;
          gap: 10px;
        }
        .btn-primary {
          background: #a855f7;
          color: white;
        }
        .btn-primary:hover {
          background: #9333ea;
        }
        .btn-primary:disabled {
          background: #475569;
          color: #94a3b8;
          cursor: not-allowed;
        }
        .btn-sec {
          background: rgba(255, 255, 255, 0.05);
          color: #cbd5e1;
          margin-top: 10px;
          border: 1px solid rgba(255, 255, 255, 0.08);
        }
        .btn-sec:hover {
          background: rgba(255, 255, 255, 0.1);
        }
        .spinner {
          width: 16px;
          height: 16px;
          border: 2px solid rgba(255,255,255,0.3);
          border-top-color: white;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>

      <h2>Async Handshake</h2>
      <div className="subtitle">Simulation of Delayed Transitions & T2-A waitFor</div>
      <div className={`badge ${isAgentConnected ? 'badge-active' : 'badge-inactive'}`}>
        {isAgentConnected ? '● Agent Connected' : '○ Offline'}
      </div>

      <div className="card">
        <div className="card-header">
          <span>Client Status</span>
          <span style={{ color: '#64748b' }}>Time: {secondsElapsed}s</span>
        </div>
        <div className="info-row">
          <span className="info-label">isLoading:</span>
          <span className="info-value" id="val-loading">{String(isLoading)}</span>
        </div>
        <div className="info-row">
          <span className="info-label">profile:</span>
          <span className="info-value" id="val-profile-status" style={{ fontStyle: profile ? 'normal' : 'italic', color: profile ? '#34d399' : '#64748b' }}>
            {profile ? 'Loaded' : 'null'}
          </span>
        </div>
      </div>

      {profile && (
        <div className="card" style={{ background: 'rgba(52, 211, 153, 0.03)', borderColor: 'rgba(52, 211, 153, 0.1)' }}>
          <div className="card-header" style={{ color: '#34d399' }}>
            Loaded User Profile Data
          </div>
          <div className="info-row">
            <span className="info-label">Name:</span>
            <span className="info-value" id="profile-name">{profile.name}</span>
          </div>
          <div className="info-row">
            <span className="info-label">Email:</span>
            <span className="info-value" id="profile-email">{profile.email}</span>
          </div>
          <div className="info-row">
            <span className="info-label">Role:</span>
            <span className="info-value" id="profile-role">{profile.role}</span>
          </div>
        </div>
      )}

      <button className="btn btn-primary" onClick={handleSimulateLoad} disabled={isLoading} id="btn-load">
        {isLoading ? (
          <>
            <div className="spinner"></div>
            Simulating Async Load...
          </>
        ) : (
          'Simulate Profile Async Load (3s)'
        )}
      </button>

      <button className="btn btn-sec" onClick={handleReset} id="btn-reset">
        Reset Profile State
      </button>
    </div>
  );
}
