import { useState } from 'react';
import { useIsAgentConnected, AgentLogger } from 'react-agent-bridge';

function BuggyComponent({ shouldCrash }) {
  if (shouldCrash) {
    throw new Error('Fatal BuggyComponent Render Exception!');
  }
  return <div style={{ color: '#94a3b8', fontSize: '14px' }}>Component Status: Stable</div>;
}

export default function App() {
  /**
   * @description The user's input email address for the form submission.
   */
  const [email, setEmail] = useState('');

  /**
   * @description The user's feedback text description.
   */
  const [feedback, setFeedback] = useState('');

  /**
   * @description Boolean flag to trigger a fatal React rendering exception.
   */
  const [shouldCrash, setShouldCrash] = useState(false);

  const isAgentConnected = useIsAgentConnected();

  const handleFormSubmit = () => {
    // 1. Check for blank form
    if (!email.trim() || !feedback.trim()) {
      console.warn('User attempted to submit an incomplete form.');
      return;
    }

    // 2. Validate email format (mock validation)
    if (!email.includes('@')) {
      console.error(`Validation Failed: Invalid email format "${email}".`);
      alert('Error: Email must contain @ symbol');
      return;
    }

    // 3. Success log
    console.log(`Form submitted successfully! Email: ${email}`);
    alert('Thank you for your feedback!');
    setEmail('');
    setFeedback('');
  };

  const handlePromiseRejection = () => {
    // Dispatch an unhandled promise rejection
    new Promise((_, reject) => {
      setTimeout(() => {
        reject(new Error('Database Timeout rejection from unhandled async hook!'));
      }, 100);
    });
  };

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
          border: 1px solid ${isAgentConnected ? '#6366f1' : 'rgba(255, 255, 255, 0.08)'};
          border-radius: 24px;
          padding: 35px;
          max-width: 500px;
          width: 100%;
          box-shadow: 0 20px 50px rgba(0,0,0,0.5), 0 0 50px ${isAgentConnected ? 'rgba(99, 102, 241, 0.15)' : 'rgba(0,0,0,0)'};
          transition: all 0.4s ease;
          position: relative;
        }
        
        /* Agent connected flashing border animation */
        ${isAgentConnected ? `
        .container::after {
          content: '';
          position: absolute;
          top: -2px; left: -2px; right: -2px; bottom: -2px;
          background: linear-gradient(135deg, #6366f1, #a855f7, #6366f1);
          border-radius: 26px;
          z-index: -1;
          animation: borderGlow 3s linear infinite;
        }
        @keyframes borderGlow {
          0% { filter: hue-rotate(0deg); }
          100% { filter: hue-rotate(360deg); }
        }
        ` : ''}

        h2 {
          font-size: 24px;
          margin-bottom: 10px;
          background: linear-gradient(135deg, #818cf8 0%, #c084fc 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
        }
        .badge {
          display: inline-block;
          padding: 6px 12px;
          border-radius: 20px;
          font-size: 12px;
          font-weight: 600;
          margin-bottom: 25px;
          transition: all 0.3s ease;
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
        .form-group {
          margin-bottom: 20px;
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        label {
          font-size: 14px;
          color: #94a3b8;
          font-weight: 600;
        }
        .form-input {
          width: 100%;
          padding: 12px;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 10px;
          color: white;
          outline: none;
          font-family: inherit;
        }
        .form-input:focus {
          border-color: #6366f1;
        }
        .btn {
          padding: 12px 18px;
          border-radius: 10px;
          font-weight: 600;
          cursor: pointer;
          font-family: inherit;
          border: none;
          transition: all 0.2s ease;
        }
        .btn-primary {
          background: #6366f1;
          color: white;
        }
        .btn-primary:hover {
          background: #4f46e5;
        }
        .btn-danger {
          background: rgba(244, 63, 94, 0.15);
          border: 1px solid rgba(244, 63, 94, 0.3);
          color: #fb7185;
          margin-top: 10px;
        }
        .btn-danger:hover {
          background: rgba(244, 63, 94, 0.25);
        }
        .btn-sec {
          background: rgba(255, 255, 255, 0.05);
          color: #cbd5e1;
          margin-top: 10px;
          border: 1px solid rgba(255,255,255,0.08);
        }
        .btn-sec:hover {
          background: rgba(255,255,255,0.1);
        }
        .log-section {
          margin-top: 30px;
          border-top: 1px solid rgba(255,255,255,0.06);
          padding-top: 20px;
        }
      `}</style>

      <h2>Logging & Connection Playground</h2>
      <div className={`badge ${isAgentConnected ? 'badge-active' : 'badge-inactive'}`}>
        {isAgentConnected ? '● Agent Connected' : '○ Offline'}
      </div>

      <div className="form-group">
        <label htmlFor="input-email">Email Input (Throws validation error if @ is missing)</label>
        <input
          id="input-email"
          type="text"
          className="form-input"
          placeholder="Enter email address"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>

      <div className="form-group">
        <label htmlFor="input-feedback">Feedback Text</label>
        <textarea
          id="input-feedback"
          className="form-input"
          style={{ minHeight: '80px', resize: 'vertical' }}
          placeholder="Type some logs or notes"
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
        />
      </div>

      <button className="btn btn-primary" style={{ width: '100%' }} onClick={handleFormSubmit} id="btn-submit">
        Submit Feedback
      </button>

      <div className="log-section">
        <h3 style={{ fontSize: '16px', marginBottom: '15px' }}>Simulate Crashes & Ledger Checks</h3>
        <BuggyComponent shouldCrash={shouldCrash} />
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '10px' }}>
          <button className="btn btn-danger" onClick={() => setShouldCrash(true)} id="btn-crash">
            Trigger Component Rendering Exception
          </button>
          <button className="btn btn-danger" onClick={handlePromiseRejection} id="btn-reject">
            Trigger Unhandled Promise Rejection
          </button>
          <button className="btn btn-sec" onClick={() => { AgentLogger.clear(); alert('Local Ledger Cleared!'); }} id="btn-clear">
            Clear Local Ledger History
          </button>
        </div>
      </div>
    </div>
  );
}
