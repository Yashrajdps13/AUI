import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import { initFiberScanner, AgentWebSocketManager } from 'react-agent-bridge';

// Initialize the scanner BEFORE React mounts
initFiberScanner();

// Connect the WebSocket Manager to the Python Agent backend
AgentWebSocketManager.connect('ws://localhost:8000');

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
