import 'react-agent-bridge/preflight';
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'
import { AgentWebSocketManager } from 'react-agent-bridge';

// Connect the bridge manager to the agent CLI's websocket server on port 8000
AgentWebSocketManager.connect('ws://localhost:8000');

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
