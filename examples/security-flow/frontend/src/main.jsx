import 'react-agent-bridge/preflight';
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import { AgentWebSocketManager } from 'react-agent-bridge';

// Connect the bridge manager to the local websocket server on port 8000
// Configure Write Scoping to allow modifications to FormComponent, but block AdminPanel!
AgentWebSocketManager.connect('ws://localhost:8000', {
  writeScope: {
    allowedTargets: ['FormComponent']
  }
});

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
