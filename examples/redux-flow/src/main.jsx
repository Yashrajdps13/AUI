import 'react-agent-bridge/preflight'; // Must be first
import React from 'react';
import ReactDOM from 'react-dom/client';
import { Provider } from 'react-redux';
import { store } from './store.js';
import App from './App.jsx';
import { AgentWebSocketManager } from 'react-agent-bridge';

// Connect to agent bridge
AgentWebSocketManager.connect('ws://localhost:8000');

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Provider store={store}>
      <App />
    </Provider>
  </React.StrictMode>
);
