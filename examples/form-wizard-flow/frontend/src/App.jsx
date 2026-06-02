import { useState } from 'react';

export default function App() {
  const [step, setStep] = useState('account'); // 'account' | 'preference' | 'success'
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [tier, setTier] = useState('free'); // 'free' | 'premium'
  const [acceptTerms, setAcceptTerms] = useState(false);

  const isStep1Disabled = username.trim() === '' || password.trim() === '';
  const isStep2Disabled = tier === 'premium' && !acceptTerms;

  return (
    <div className="app-container">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap');
        
        * {
          box-sizing: border-box;
          margin: 0;
          padding: 0;
        }

        body {
          background: radial-gradient(circle at 50% 50%, #0d0f1a 0%, #050608 100%);
          font-family: 'Outfit', sans-serif;
          color: #f1f3f9;
          min-height: 100vh;
          display: flex;
          justify-content: center;
          align-items: center;
          padding: 20px;
        }

        .app-container {
          background: rgba(18, 22, 40, 0.7);
          backdrop-filter: blur(20px);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 28px;
          width: 100%;
          max-width: 550px;
          min-height: 480px;
          padding: 40px;
          box-shadow: 0 25px 60px rgba(0, 0, 0, 0.55), 0 0 100px rgba(99, 102, 241, 0.12);
          display: flex;
          flex-direction: column;
          justify-content: space-between;
        }

        .header {
          margin-bottom: 30px;
          text-align: center;
        }

        h2 {
          font-size: 28px;
          font-weight: 800;
          background: linear-gradient(135deg, #c7d2fe 0%, #818cf8 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          margin-bottom: 8px;
        }

        p.subtitle {
          font-size: 14px;
          color: #94a3b8;
        }

        .progress-bar {
          display: flex;
          justify-content: space-between;
          margin-bottom: 30px;
          position: relative;
        }

        .progress-line {
          position: absolute;
          top: 15px;
          left: 0;
          right: 0;
          height: 2px;
          background: rgba(255, 255, 255, 0.06);
          z-index: 1;
        }

        .progress-line-active {
          position: absolute;
          top: 15px;
          left: 0;
          height: 2px;
          background: #6366f1;
          transition: width 0.3s ease;
          z-index: 2;
        }

        .progress-step {
          width: 32px;
          height: 32px;
          border-radius: 50%;
          background: #1e293b;
          border: 2px solid #334155;
          display: flex;
          justify-content: center;
          align-items: center;
          font-size: 12px;
          font-weight: 600;
          z-index: 3;
          transition: all 0.3s ease;
          color: #94a3b8;
        }

        .progress-step.active {
          background: #6366f1;
          border-color: #818cf8;
          color: #ffffff;
          box-shadow: 0 0 15px rgba(99, 102, 241, 0.4);
        }

        .progress-step.completed {
          background: #10b981;
          border-color: #34d399;
          color: #ffffff;
        }

        .form-group {
          margin-bottom: 20px;
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        label {
          font-size: 14px;
          font-weight: 600;
          color: #cbd5e1;
        }

        .form-input {
          width: 100%;
          padding: 14px 16px;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 12px;
          color: #f1f3f9;
          font-size: 15px;
          outline: none;
          transition: all 0.3s ease;
          font-family: inherit;
        }

        .form-input:focus {
          border-color: #6366f1;
          background: rgba(255, 255, 255, 0.06);
          box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
        }

        .tier-selection {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 16px;
          margin-bottom: 24px;
        }

        .tier-card {
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 16px;
          padding: 20px;
          text-align: center;
          cursor: pointer;
          transition: all 0.3s ease;
        }

        .tier-card:hover {
          border-color: rgba(99, 102, 241, 0.3);
          background: rgba(255, 255, 255, 0.04);
        }

        .tier-card.active {
          background: rgba(99, 102, 241, 0.08);
          border-color: #6366f1;
          box-shadow: 0 0 20px rgba(99, 102, 241, 0.1);
        }

        .tier-name {
          font-size: 16px;
          font-weight: 600;
          margin-bottom: 6px;
        }

        .tier-price {
          font-size: 20px;
          font-weight: 800;
          color: #818cf8;
        }

        .checkbox-group {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 16px;
          background: rgba(99, 102, 241, 0.05);
          border: 1px solid rgba(99, 102, 241, 0.15);
          border-radius: 14px;
          margin-top: 15px;
          animation: fadeIn 0.4s ease-out;
        }

        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }

        .checkbox-input {
          width: 18px;
          height: 18px;
          cursor: pointer;
          accent-color: #6366f1;
        }

        .checkbox-label {
          font-size: 13px;
          color: #94a3b8;
          line-height: 1.4;
          cursor: pointer;
        }

        .button-group {
          display: flex;
          gap: 16px;
          margin-top: 30px;
        }

        .btn {
          flex: 1;
          padding: 14px 20px;
          font-size: 15px;
          font-weight: 600;
          border-radius: 12px;
          border: none;
          cursor: pointer;
          transition: all 0.3s ease;
          font-family: inherit;
        }

        .btn-primary {
          background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
          color: white;
          box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);
        }

        .btn-primary:hover:not(:disabled) {
          transform: translateY(-2px);
          box-shadow: 0 6px 18px rgba(79, 70, 229, 0.45);
        }

        .btn-primary:disabled {
          background: #1e293b;
          color: #475569;
          box-shadow: none;
          cursor: not-allowed;
          border: 1px solid rgba(255, 255, 255, 0.03);
        }

        .btn-secondary {
          background: transparent;
          border: 1px solid rgba(255, 255, 255, 0.1);
          color: #cbd5e1;
        }

        .btn-secondary:hover {
          background: rgba(255, 255, 255, 0.03);
          border-color: rgba(255, 255, 255, 0.2);
        }

        .success-icon {
          font-size: 64px;
          margin-bottom: 20px;
          animation: scaleIn 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275);
          text-align: center;
        }

        @keyframes scaleIn {
          0% { transform: scale(0); }
          100% { transform: scale(1); }
        }
      `}</style>

      {/* Progress Indicator */}
      <div className="progress-bar">
        <div className="progress-line"></div>
        <div 
          className="progress-line-active" 
          style={{ 
            width: step === 'account' ? '0%' : step === 'preference' ? '50%' : '100%' 
          }}
        ></div>
        <div className={`progress-step ${step === 'account' ? 'active' : 'completed'}`}>1</div>
        <div className={`progress-step ${step === 'preference' ? 'active' : step === 'success' ? 'completed' : ''}`}>2</div>
        <div className={`progress-step ${step === 'success' ? 'active' : ''}`}>3</div>
      </div>

      {/* Step 1: Account details */}
      {step === 'account' && (
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, justifyContent: 'space-between' }}>
          <div>
            <div className="header">
              <h2>Create Account</h2>
              <p className="subtitle">Set your login credentials to get started</p>
            </div>
            
            <div className="form-group">
              <label htmlFor="input-username">Username</label>
              <input
                id="input-username"
                type="text"
                className="form-input"
                placeholder="Choose a username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            
            <div className="form-group">
              <label htmlFor="input-password">Password</label>
              <input
                id="input-password"
                type="password"
                className="form-input"
                placeholder="Choose a secure password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
          </div>

          <div className="button-group">
            <button
              className="btn btn-primary"
              disabled={isStep1Disabled}
              onClick={() => setStep('preference')}
              id="btn-next-step-1"
            >
              Continue
            </button>
          </div>
        </div>
      )}

      {/* Step 2: Preferences */}
      {step === 'preference' && (
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, justifyContent: 'space-between' }}>
          <div>
            <div className="header">
              <h2>Select Subscription</h2>
              <p className="subtitle">Choose a plan tier that fits your needs</p>
            </div>

            <div className="tier-selection">
              <div 
                className={`tier-card ${tier === 'free' ? 'active' : ''}`}
                onClick={() => setTier('free')}
                id="btn-tier-free"
              >
                <div className="tier-name">Free Tier</div>
                <div className="tier-price">$0</div>
              </div>
              <div 
                className={`tier-card ${tier === 'premium' ? 'active' : ''}`}
                onClick={() => setTier('premium')}
                id="btn-tier-premium"
              >
                <div className="tier-name">Premium Tier</div>
                <div className="tier-price">$9.99</div>
              </div>
            </div>

            {/* Conditionally Rendered Terms for Premium */}
            {tier === 'premium' && (
              <div className="checkbox-group" id="group-terms">
                <input
                  id="input-accept-terms"
                  type="checkbox"
                  className="checkbox-input"
                  checked={acceptTerms}
                  onChange={(e) => setAcceptTerms(e.target.checked)}
                />
                <label htmlFor="input-accept-terms" className="checkbox-label">
                  I accept the Premium Subscription Agreement and authorize monthly billing.
                </label>
              </div>
            )}
          </div>

          <div className="button-group">
            <button
              className="btn btn-secondary"
              onClick={() => setStep('account')}
              id="btn-back-step-2"
            >
              Back
            </button>
            <button
              className="btn btn-primary"
              disabled={isStep2Disabled}
              onClick={() => setStep('success')}
              id="btn-submit-wizard"
            >
              Submit Registration
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Success Screen */}
      {step === 'success' && (
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, justifyContent: 'center', alignItems: 'center', textAlign: 'center' }}>
          <div className="success-icon">🎉</div>
          <h2>Registration Complete!</h2>
          <p style={{ color: '#94a3b8', margin: '15px 0 30px', fontSize: '15px', lineHeight: '1.5' }}>
            Welcome, <strong>@{username}</strong>! Your <strong>{tier.toUpperCase()}</strong> account has been configured successfully.
          </p>
          
          <button
            className="btn btn-primary"
            style={{ width: '100%' }}
            onClick={() => {
              setUsername('');
              setPassword('');
              setTier('free');
              setAcceptTerms(false);
              setStep('account');
            }}
            id="btn-start-over"
          >
            Start Over
          </button>
        </div>
      )}
    </div>
  );
}
