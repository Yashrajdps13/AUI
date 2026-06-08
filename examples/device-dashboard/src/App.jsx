import React, { useState, createContext, useContext, useEffect, useRef } from 'react';
import { useIsAgentConnected, useAgentStatus } from 'react-agent-bridge';

// Create a React Context to share device configuration state between components
const DeviceContext = createContext(null);

export default function App() {
  /**
   * @description Device unlock state. If locked, you cannot modify settings. Use PIN '7788' and click Unlock to unlock.
   * @readonly
   */
  const [isUnlocked, setIsUnlocked] = useState(false);

  /**
   * @description The PIN input field value used for authentication.
   */
  const [pinInput, setPinInput] = useState('');

  /**
   * @description The IP address of the target controller. Must follow valid IPv4 format.
   */
  const [ipAddress, setIpAddress] = useState('192.168.1.15');

  /**
   * @description The device operating mode. Allowed values: 'eco', 'boost', or 'maintain'.
   */
  const [operatingMode, setOperatingMode] = useState('eco');

  /**
   * @description The critical alert temperature threshold in Fahrenheit. Allowed range: 10 to 100.
   */
  const [criticalThreshold, setCriticalThreshold] = useState(45);

  /**
   * @description Current self-test/diagnostic state. Allowed values: 'idle', 'running', 'passed', 'failed'.
   */
  const [diagnosticStatus, setDiagnosticStatus] = useState('idle');

  /**
   * @description A highly confidential authentication key for backend API requests.
   * @sensitive
   */
  const [apiSecret, setApiSecret] = useState('SEC_KEY_8899FF00AA');

  // Audit logs state
  const [logs, setLogs] = useState([
    { time: new Date().toLocaleTimeString(), type: 'system', msg: 'Core controller started.' }
  ]);

  const addLog = (type, msg) => {
    setLogs((prev) => [...prev, { time: new Date().toLocaleTimeString(), type, msg }]);
  };

  return (
    <DeviceContext.Provider
      value={{
        isUnlocked,
        setIsUnlocked,
        pinInput,
        setPinInput,
        ipAddress,
        setIpAddress,
        operatingMode,
        setOperatingMode,
        criticalThreshold,
        setCriticalThreshold,
        diagnosticStatus,
        setDiagnosticStatus,
        apiSecret,
        setApiSecret,
        logs,
        addLog,
      }}
    >
      <DashboardContainer />
    </DeviceContext.Provider>
  );
}

function DashboardContainer() {
  const isAgentConnected = useIsAgentConnected();
  const agentStatus = useAgentStatus();
  const { logs } = useContext(DeviceContext);

  const logsEndRef = useRef(null);

  // Auto scroll logs
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  return (
    <div className="app-container">
      <header>
        <h1>Smart Device Management Console</h1>
        <p>Dynamic State Synchronizer & Security Control</p>
      </header>

      {/* Agent Status Panel */}
      <div className="agent-status-indicator">
        <div>
          <strong>Bridge Status: </strong>
          {isAgentConnected ? (
            <span style={{ color: '#10b981', fontWeight: 600 }}>CONNECTED</span>
          ) : (
            <span style={{ color: '#ef4444', fontWeight: 600 }}>DISCONNECTED</span>
          )}
        </div>
        <div>
          <strong>Agent Task Status: </strong>
          <span className={`status-badge ${agentStatus}`}>{agentStatus}</span>
        </div>
      </div>

      <div className="dashboard-grid">
        {/* Security & Access Card */}
        <SecurityCard />

        {/* Configuration Card */}
        <ConfigurationCard />

        {/* Diagnostics Card */}
        <DiagnosticsCard />

        {/* Audit Logs Card */}
        <div className="card audit-logs-card">
          <h2>System Audit Logs</h2>
          <div className="logs-container">
            {logs.map((log, index) => (
              <div key={index} className="log-entry">
                <span className="log-time">[{log.time}]</span>
                <span className={`log-msg ${log.type}`}>{log.msg}</span>
              </div>
            ))}
            <div ref={logsEndRef} />
          </div>
        </div>
      </div>
    </div>
  );
}

function SecurityCard() {
  const { isUnlocked, setIsUnlocked, pinInput, setPinInput, apiSecret, setApiSecret, addLog } =
    useContext(DeviceContext);

  const handleUnlock = () => {
    if (pinInput === '7788') {
      setIsUnlocked(true);
      setPinInput('');
      addLog('system', 'Console access unlocked via security PIN.');
    } else {
      addLog('system', `Access denied: PIN '${pinInput}' is invalid.`);
      setPinInput('');
    }
  };

  const handleLock = () => {
    setIsUnlocked(false);
    addLog('system', 'Console access locked.');
  };

  return (
    <div className="card">
      <h2>Console Security</h2>

      <div className="form-group">
        <label htmlFor="pin-input">
          Access PIN
          <span className="hint-badge">7788 to unlock</span>
        </label>
        <input
          id="pin-input"
          type="password"
          placeholder="Enter 4-digit PIN"
          value={pinInput}
          onChange={(e) => setPinInput(e.target.value)}
          disabled={isUnlocked}
        />
      </div>

      <div style={{ display: 'flex', gap: '10px', marginBottom: '20px' }}>
        <button
          id="btn-unlock"
          className="btn btn-primary"
          onClick={handleUnlock}
          disabled={isUnlocked || !pinInput}
        >
          Unlock Console
        </button>
        <button
          id="btn-lock"
          className="btn btn-danger"
          onClick={handleLock}
          disabled={!isUnlocked}
        >
          Lock Console
        </button>
      </div>

      <div className="form-group">
        <label htmlFor="secret-key">API Secret (Sensitive Token)</label>
        <input
          id="secret-key"
          type="text"
          value={apiSecret}
          onChange={(e) => {
            setApiSecret(e.target.value);
            addLog('state', `API Secret updated by operator.`);
          }}
          disabled={!isUnlocked}
        />
        <div className="input-desc">
          Note: This field has been marked as sensitive. The agent sees a redacted value in the snapshot.
        </div>
      </div>
    </div>
  );
}

function ConfigurationCard() {
  const {
    isUnlocked,
    ipAddress,
    setIpAddress,
    operatingMode,
    setOperatingMode,
    criticalThreshold,
    setCriticalThreshold,
    addLog,
  } = useContext(DeviceContext);

  return (
    <div className="card">
      <h2>Device Configuration</h2>

      <div className={`form-group ${!isUnlocked ? 'disabled' : ''}`}>
        <label htmlFor="ip-input">Controller IP Address</label>
        <input
          id="ip-input"
          type="text"
          placeholder="e.g. 192.168.1.10"
          value={ipAddress}
          onChange={(e) => {
            setIpAddress(e.target.value);
            addLog('state', `IP Address changed to: ${e.target.value}`);
          }}
        />
      </div>

      <div className={`form-group ${!isUnlocked ? 'disabled' : ''}`}>
        <label htmlFor="mode-select">Operational Mode</label>
        <select
          id="mode-select"
          value={operatingMode}
          onChange={(e) => {
            setOperatingMode(e.target.value);
            addLog('state', `Mode updated to: ${e.target.value.toUpperCase()}`);
          }}
        >
          <option value="eco">Eco Mode</option>
          <option value="boost">Boost Performance</option>
          <option value="maintain">Maintain Equilibrium</option>
        </select>
      </div>

      <div className={`form-group ${!isUnlocked ? 'disabled' : ''}`}>
        <label htmlFor="threshold-slider">Critical Temp Threshold (°F)</label>
        <div className="slider-container">
          <input
            id="threshold-slider"
            type="range"
            min="10"
            max="100"
            value={criticalThreshold}
            onChange={(e) => {
              const val = parseInt(e.target.value);
              setCriticalThreshold(val);
              addLog('state', `Critical threshold set to ${val}°F`);
            }}
          />
          <span className="slider-val" id="val-threshold">{criticalThreshold}°F</span>
        </div>
      </div>
    </div>
  );
}

function DiagnosticsCard() {
  const { isUnlocked, diagnosticStatus, setDiagnosticStatus, addLog } = useContext(DeviceContext);

  const runDiagnostics = () => {
    if (diagnosticStatus === 'running') return;
    setDiagnosticStatus('running');
    addLog('system', 'Starting diagnostic self-test...');

    setTimeout(() => {
      setDiagnosticStatus('passed');
      addLog('system', 'Diagnostics self-test completed: ALL SYSTEMS OPTIMAL.');
    }, 1500);
  };

  const resetDiagnostics = () => {
    setDiagnosticStatus('idle');
    addLog('system', 'Diagnostics report cleared.');
  };

  return (
    <div className="card">
      <h2>Diagnostics Panel</h2>

      <div className="diagnostic-status" style={{ marginBottom: '20px' }}>
        <div className="diag-item">
          <span className="diag-label">Test Suite:</span>
          <span className="diag-value">Self-Diagnostic v4.2</span>
        </div>
        <div className="diag-item">
          <span className="diag-label">Status:</span>
          <span className={`diag-value ${diagnosticStatus}`} id="val-status">
            {diagnosticStatus.toUpperCase()}
          </span>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '10px' }}>
        <button
          id="btn-run-diag"
          className="btn btn-success"
          onClick={runDiagnostics}
          disabled={!isUnlocked || diagnosticStatus === 'running'}
        >
          Run Diagnostics
        </button>
        <button
          id="btn-reset-diag"
          className="btn btn-secondary"
          onClick={resetDiagnostics}
          disabled={!isUnlocked || diagnosticStatus === 'idle'}
        >
          Clear Report
        </button>
      </div>
    </div>
  );
}
