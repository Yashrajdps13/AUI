import 'react-agent-bridge/preflight'; // MUST be the first import
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import { AgentWebSocketManager } from 'react-agent-bridge';

// Connect to the local React Agent Bridge WebSocket server
AgentWebSocketManager.connect('ws://localhost:8000');

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
