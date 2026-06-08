import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { AgentWebSocketManager } from 'react-agent-bridge'

// Connect the bridge manager to the local websocket backend on port 8000
AgentWebSocketManager.connect('ws://localhost:8000')

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
