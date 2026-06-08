import React, { useState, useEffect } from 'react';
import { useIsAgentConnected, useAgentStatus, CommandAuditLogger } from 'react-agent-bridge';

export default function App() {
  const [activeTab, setActiveTab] = useState('security');
  const isConnected = useIsIsAgentConnectedWrapper();

  // Helper because we must satisfy the existing useIsAgentConnected hook requirement
  function useIsIsAgentConnectedWrapper() {
    return useIsAgentConnected();
  }

  return (
    <div className="dashboard-container">
      <div className="dashboard-header">
        <h1>Smart Routing Control Panel</h1>
        <p>Routing, dynamic state registration, PII protection, and agent status signals.</p>
      </div>

      <nav className="tabs-navigation">
        <button
          id="tab-security"
          className={`tab-btn ${activeTab === 'security' ? 'active' : ''}`}
          onClick={() => setActiveTab('security')}
        >
          Security Settings
        </button>
        <button
          id="tab-controls"
          className={`tab-btn ${activeTab === 'controls' ? 'active' : ''}`}
          onClick={() => setActiveTab('controls')}
        >
          Device Controls
        </button>
        <button
          id="tab-status"
          className={`tab-btn ${activeTab === 'status' ? 'active' : ''}`}
          onClick={() => setActiveTab('status')}
        >
          Agent Status
        </button>
      </nav>

      <main className="panel-card">
        {activeTab === 'security' && <SecurityPanel />}
        {activeTab === 'controls' && <ControlsPanel />}
        {activeTab === 'status' && <StatusPanel isConnected={isConnected} />}
      </main>
    </div>
  );
}

function SecurityPanel() {
  /**
   * The private developer API Secret Key. Must never be exposed in plain logs.
   * @sensitive
   */
  const [apiSecret, setApiSecret] = useState('');

  /**
   * The 4-digit security authentication PIN code. Should remain protected.
   * @sensitive
   */
  const [securityPin, setSecurityPin] = useState('');

  const [message, setMessage] = useState('');

  const handleSave = (e) => {
    e.preventDefault();
    if (!apiSecret || !securityPin) {
      setMessage('Error: Both fields must be filled.');
      return;
    }
    console.log('Security settings updated with secret and pin.');
    setMessage('Settings successfully committed!');
  };

  return (
    <div id="panel-security">
      <div className="panel-title">
        <span>Security Configuration</span>
        <span className="sensitive-tag">PII Shield Active</span>
      </div>

      <form onSubmit={handleSave}>
        <div className="form-group">
          <label htmlFor="apiSecret">
            API Secret Key
            <span className="sensitive-tag">Sensitive</span>
          </label>
          <input
            type="password"
            id="apiSecret"
            className="form-control"
            value={apiSecret}
            onChange={(e) => setApiSecret(e.target.value)}
            placeholder="sk-live-..."
          />
        </div>

        <div className="form-group">
          <label htmlFor="securityPin">
            Security PIN
            <span className="sensitive-tag">Sensitive</span>
          </label>
          <input
            type="text"
            id="securityPin"
            maxLength={4}
            className="form-control"
            value={securityPin}
            onChange={(e) => setSecurityPin(e.target.value)}
            placeholder="0000"
          />
        </div>

        <button type="submit" id="btn-save-security" className="btn">
          Save Configuration
        </button>

        {message && (
          <div
            id="security-message"
            style={{
              marginTop: '1.25rem',
              color: message.startsWith('Error') ? 'var(--error-color)' : 'var(--success-color)',
              fontWeight: 500,
              fontSize: '0.95rem',
            }}
          >
            {message}
          </div>
        )}
      </form>
    </div>
  );
}

function ControlsPanel() {
  /**
   * The target fan speed rate in RPM percentage.
   */
  const [fanSpeed, setFanSpeed] = useState(50);

  /**
   * Input name for a new IoT device to add to the dashboard.
   */
  const [newDevice, setNewDevice] = useState('');

  const [devices, setDevices] = useState(['Living Room Light', 'Kitchen AC']);

  const handleAddDevice = () => {
    if (!newDevice.trim()) return;
    setDevices((prev) => [...prev, newDevice.trim()]);
    setNewDevice('');
  };

  const handleRemoveDevice = (idx) => {
    setDevices((prev) => prev.filter((_, i) => i !== idx));
  };

  return (
    <div id="panel-controls">
      <div className="panel-title">Smart Device Controller</div>

      <div className="form-group">
        <label>Active Managed Devices</label>
        <div className="device-tags">
          {devices.map((device, idx) => (
            <div key={idx} className="device-tag">
              <span className="device-dot"></span>
              <span>{device}</span>
              <span className="device-remove" onClick={() => handleRemoveDevice(idx)}>
                ×
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="form-group" style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end' }}>
        <div style={{ flex: 1 }}>
          <label htmlFor="newDevice">Add New Device</label>
          <input
            type="text"
            id="newDevice"
            className="form-control"
            value={newDevice}
            onChange={(e) => setNewDevice(e.target.value)}
            placeholder="e.g. Smart Thermostat"
          />
        </div>
        <button id="btn-add-device" className="btn" onClick={handleAddDevice}>
          Add
        </button>
      </div>

      <div className="form-group" style={{ marginTop: '1.5rem' }}>
        <label htmlFor="slider-fan">Adjust Cooling Fan Speed</label>
        <div className="slider-container">
          <input
            type="range"
            id="slider-fan"
            min="0"
            max="100"
            className="range-slider"
            value={fanSpeed}
            onChange={(e) => setFanSpeed(Number(e.target.value))}
          />
          <span className="slider-val" id="fan-speed-value">
            {fanSpeed}%
          </span>
        </div>
      </div>
    </div>
  );
}

function StatusPanel({ isConnected }) {
  const status = useAgentStatus();
  const [auditLog, setAuditLog] = useState([]);

  // Poll audit logs to show in UI
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

  return (
    <div id="panel-status" style={{ display: 'flex', flexDirection: 'column', height: '100%', flex: 1 }}>
      <div className="panel-title">
        <span>Agent Operations Status</span>
        <button className="btn btn-secondary" id="btn-clear-logs" style={{ padding: '0.4rem 0.8rem', fontSize: '0.85rem' }} onClick={handleClear}>
          Clear History
        </button>
      </div>

      <div className="agent-status-panel">
        <div className="status-box">
          <span className="status-label">Websocket Link</span>
          <span className={`status-badge ${isConnected ? 'connected' : 'disconnected'}`}>
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>

        <div className="status-box">
          <span className="status-label">Operational State</span>
          <span className={`status-badge ${status}`}>
            {status}
          </span>
        </div>
      </div>

      <div style={{ marginTop: '1.5rem', flex: 1, display: 'flex', flexDirection: 'column' }}>
        <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: '0.5rem', display: 'block', fontWeight: 500 }}>
          Bridge Action Ledger (Audit Logs)
        </span>
        <div
          id="status-logs-viewer"
          style={{
            background: 'rgba(0, 0, 0, 0.2)',
            borderRadius: '10px',
            border: '1px solid rgba(255, 255, 255, 0.05)',
            padding: '1rem',
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: '0.85rem',
            maxHeight: '180px',
            overflowY: 'auto',
            flex: 1,
          }}
        >
          {auditLog.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', textAlign: 'center', padding: '1.5rem 0' }}>
              No commands recorded yet.
            </div>
          ) : (
            [...auditLog].reverse().map((entry, idx) => (
              <div key={idx} style={{ marginBottom: '0.4rem', borderBottom: '1px dashed rgba(255, 255, 255, 0.03)', paddingBottom: '0.4rem' }}>
                <span style={{ color: entry.success ? 'var(--success-color)' : 'var(--error-color)', fontWeight: 'bold' }}>
                  [{entry.success ? 'OK' : 'ERR'}]
                </span>{' '}
                <span style={{ color: 'var(--accent-blue)' }}>{entry.type}</span> on{' '}
                <span style={{ color: 'var(--text-main)' }}>{entry.target}</span>: {JSON.stringify(entry.value)}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
