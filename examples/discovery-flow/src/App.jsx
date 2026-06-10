import React, { useState, useEffect } from 'react';
import { useIsAgentConnected, useAgentStatus, CommandAuditLogger } from 'react-agent-bridge';

export default function App() {
  const isAgentConnected = useIsAgentConnected();
  const agentStatus = useAgentStatus();

  // Step state
  const [activeStep, setActiveStep] = useState('details'); // 'details' | 'options' | 'payment' | 'success'

  // --- Step 1 Slots ---
  /**
   * The natural name of the event attendee.
   */
  const [attendeeName, setAttendeeName] = useState('');

  /**
   * The contact email address of the attendee.
   * @sensitive
   */
  const [email, setEmail] = useState('');

  // --- Step 2 Slots ---
  /**
   * The category of ticket (VIP, Standard, or Speaker).
   */
  const [ticketType, setTicketType] = useState('standard');

  /**
   * Checked technical session options selected by the attendee.
   */
  const [selectedSessions, setSelectedSessions] = useState([]);

  // --- Step 3 Slots ---
  /**
   * The 16-digit credit card number for ticket purchase payment.
   * @sensitive
   */
  const [cardNumber, setCardNumber] = useState('');

  // --- Derived State & Submit Slots ---
  /**
   * The derived total transaction cost based on ticket type and selected sessions.
   */
  const [totalCost, setTotalCost] = useState(100);

  /**
   * Whether the booking registration form was submitted successfully.
   */
  const [isSubmitted, setIsSubmitted] = useState(false);

  const [auditLogs, setAuditLogs] = useState([]);

  // Poll audit logs to show in UI
  useEffect(() => {
    const timer = setInterval(() => {
      setAuditLogs(CommandAuditLogger.getAuditLog());
    }, 500);
    return () => clearInterval(timer);
  }, []);

  // Update total cost when ticketType or selectedSessions change
  useEffect(() => {
    let base = 100;
    if (ticketType === 'vip') base = 500;
    if (ticketType === 'speaker') base = 0;
    setTotalCost(base + selectedSessions.length * 50);
  }, [ticketType, selectedSessions]);

  // Sync window.location.pathname based on step
  useEffect(() => {
    const path = `/${activeStep}`;
    if (window.location.pathname !== path) {
      window.history.pushState(null, '', path);
    }
  }, [activeStep]);

  const handleNext = () => {
    if (activeStep === 'details') {
      setActiveStep('options');
    } else if (activeStep === 'options') {
      setActiveStep('payment');
    }
  };

  const handleBack = () => {
    if (activeStep === 'options') {
      setActiveStep('details');
    } else if (activeStep === 'payment') {
      setActiveStep('options');
    }
  };

  const handleSubmitSubmit = (e) => {
    if (e) e.preventDefault();
    if (!attendeeName || !email || !cardNumber) {
      return;
    }
    setIsSubmitted(true);
    setActiveStep('success');
  };

  const handleReset = () => {
    setAttendeeName('');
    setEmail('');
    setTicketType('standard');
    setSelectedSessions([]);
    setCardNumber('');
    setIsSubmitted(false);
    setActiveStep('details');
  };

  const toggleSession = (session) => {
    setSelectedSessions((prev) =>
      prev.includes(session) ? prev.filter((s) => s !== session) : [...prev, session]
    );
  };

  return (
    <div className="app-wrapper">
      <div className="hero-header">
        <h1>TechConf Registration Hub</h1>
        <p>A multi-step checkout form to showcase Discovery Mode and Golden Trace Replay.</p>
      </div>

      <div className={`glow-panel ${isAgentConnected ? 'connected' : ''}`}>
        <div className="panel-title">
          <span>Booking Registration</span>
          <span className="badge-sensitive" style={{ background: 'rgba(0,180,216,0.1)', borderColor: 'var(--accent-blue)', color: 'var(--accent-blue)' }}>
            Step: {activeStep.toUpperCase()}
          </span>
        </div>

        {/* Steps Tab Indicators */}
        <div className="steps-bar">
          <button className={`step-tab ${activeStep === 'details' ? 'active' : ''}`} onClick={() => setActiveStep('details')}>
            1. Details
          </button>
          <button className={`step-tab ${activeStep === 'options' ? 'active' : ''}`} onClick={() => setActiveStep('options')}>
            2. Options
          </button>
          <button className={`step-tab ${activeStep === 'payment' ? 'active' : ''}`} onClick={() => setActiveStep('payment')}>
            3. Payment
          </button>
          <button className={`step-tab ${activeStep === 'success' ? 'active' : ''}`} onClick={() => setActiveStep('success')} disabled={!isSubmitted}>
            4. Done
          </button>
        </div>

        {/* Form Screens */}
        {activeStep === 'details' && (
          <div id="step-details-container">
            <div className="form-group">
              <label htmlFor="attendeeName">Attendee Full Name</label>
              <input
                type="text"
                id="attendeeName"
                className="form-control"
                value={attendeeName}
                onChange={(e) => setAttendeeName(e.target.value)}
                placeholder="e.g. John Doe"
              />
            </div>

            <div className="form-group">
              <label htmlFor="email">
                Email Address
                <span className="badge-sensitive">Sensitive</span>
              </label>
              <input
                type="email"
                id="email"
                className="form-control"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="e.g. john@example.com"
              />
            </div>

            <div className="nav-buttons">
              <button style={{ visibility: 'hidden' }} className="btn btn-secondary">Back</button>
              <button id="btn-details-next" className="btn btn-primary" onClick={handleNext} disabled={!attendeeName || !email}>
                Next Step
              </button>
            </div>
          </div>
        )}

        {activeStep === 'options' && (
          <div id="step-options-container">
            <div className="form-group">
              <label htmlFor="ticketType">Select Ticket Category</label>
              <select
                id="ticketType"
                className="form-control"
                value={ticketType}
                onChange={(e) => setTicketType(e.target.value)}
              >
                <option value="standard">Standard Pass ($100)</option>
                <option value="vip">VIP Executive Pass ($500)</option>
                <option value="speaker">Speaker Access ($0)</option>
              </select>
            </div>

            <div className="form-group">
              <label>Select Optional Tech Sessions (+$50 each)</label>
              <div className="checkbox-grid">
                {['Keynote Panel', 'AI Masterclass', 'Hands-on Labs', 'Networking Dinner'].map((session) => (
                  <div
                    key={session}
                    className={`checkbox-card ${selectedSessions.includes(session) ? 'selected' : ''}`}
                    onClick={() => toggleSession(session)}
                  >
                    <input
                      type="checkbox"
                      checked={selectedSessions.includes(session)}
                      readOnly
                    />
                    <span>{session}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="cost-display">
              <span>Calculated Total Cost:</span>
              <span className="amount">${totalCost}</span>
            </div>

            <div className="nav-buttons">
              <button id="btn-options-back" className="btn btn-secondary" onClick={handleBack}>
                Back
              </button>
              <button id="btn-options-next" className="btn btn-primary" onClick={handleNext}>
                Next Step
              </button>
            </div>
          </div>
        )}

        {activeStep === 'payment' && (
          <div id="step-payment-container">
            <div className="form-group">
              <label htmlFor="cardNumber">
                Credit Card Number (16-digits)
                <span className="badge-sensitive">Sensitive</span>
              </label>
              <input
                type="text"
                id="cardNumber"
                maxLength={16}
                className="form-control"
                value={cardNumber}
                onChange={(e) => setCardNumber(e.target.value)}
                placeholder="4000 1234 5678 9010"
              />
            </div>

            <div className="cost-display">
              <span>Payment Amount:</span>
              <span className="amount">${totalCost}</span>
            </div>

            <div className="nav-buttons">
              <button id="btn-payment-back" className="btn btn-secondary" onClick={handleBack}>
                Back
              </button>
              <button id="btn-submit-booking" className="btn btn-primary" onClick={handleSubmitSubmit} disabled={!cardNumber}>
                Confirm and Pay
              </button>
            </div>
          </div>
        )}

        {activeStep === 'success' && (
          <div className="success-message" id="success-screen">
            <div className="success-icon">✓</div>
            <h2>Registration Successful!</h2>
            <p>Thank you, {attendeeName}. We've sent a ticket validation to {email}.</p>
            <p><strong>Amount Paid:</strong> ${totalCost}</p>
            
            <button id="btn-reset" className="btn btn-secondary" style={{ marginTop: '2rem', maxWidth: '200px' }} onClick={handleReset}>
              Reset Form
            </button>
          </div>
        )}

        {/* Audit Logs and Info section */}
        <hr style={{ border: 'none', borderTop: '1px solid rgba(255, 255, 255, 0.05)', margin: '2rem 0' }} />
        
        <div className="audit-logs-card">
          <h3>Bridge Activity log</h3>
          <div className="logs-viewer">
            {auditLogs.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', textAlign: 'center', padding: '1rem' }}>
                No mutations registered. Try clicking or changing fields.
              </div>
            ) : (
              [...auditLogs].reverse().map((entry, idx) => (
                <div className="log-row" key={idx}>
                  <span style={{ color: entry.success ? 'var(--accent-neon)' : 'var(--error-red)', fontWeight: 'bold' }}>
                    [{entry.success ? 'SUCCESS' : 'FAILED'}]
                  </span>{' '}
                  {entry.type} on <span style={{ color: 'var(--accent-blue)' }}>{entry.target}</span> to{' '}
                  <span style={{ color: 'var(--accent-purple)' }}>{JSON.stringify(entry.value)}</span>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="status-row">
          <span>
            Link Status:{' '}
            <span className={`status-dot ${isAgentConnected ? 'active' : ''}`}></span>{' '}
            {isAgentConnected ? 'Connected' : 'Disconnected'}
          </span>
          {isAgentConnected && (
            <span>
              Agent Status: <strong style={{ color: 'var(--accent-blue)', textTransform: 'uppercase' }}>{agentStatus}</strong>
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
