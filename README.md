# react-agent-bridge

🌉 **Zero-friction npm framework giving AI agents semantic read-write access to React internal state.**

`react-agent-bridge` intercepts your React Fiber tree and `useState` hooks at runtime, giving AI agents (like LangGraph, Playwright agents, or custom LLM loops) real-time access to application state and component DOM nodes—with **zero component-level code modifications**.

---

## Features

- **🔌 Zero-Friction Setup**: One Babel plugin and one entrypoint import. No wrappers, hooks, or context changes in your actual application code.
- **📝 JSDoc Annotation Extraction**: Automatically parses developer JSDoc block comments (`/** ... */`) preceding `useState` declarations at build-time to provide semantic descriptions of state slots to the agent.
- **👁️ Dynamic Element Visibility & Disabled States**: Interactive element scanner detects computed CSS visibility (display, visibility, opacity) and HTML/ARIA disabled properties to prevent agent interactions with hidden or inactive fields.
- **🤝 Render Settlement Handshakes**: Hooks into React DevTools commits to notify the agent backend when rendering and layout updates have fully settled, eliminating execution race conditions.
- **🧠 Semantic Registry**: Live, hierarchical registry of active components and state variables.
- **⚡ State Subscriptions & Diffs**: Real-time push notifications to the agent when watched states change, minimizing websocket chatter.
- **✍️ Semantic Read & Write**: The agent can read state values and dispatch state mutations securely.
- **🎯 Host DOM Binding**: Correlates virtual component state slots to their exact browser DOM nodes for high-fidelity click, change, and focus event dispatches.
- **🔗 Concurrent-Mode Safe**: Automatically schedules incoming state updates within React's `startTransition` blocks.
- **🚨 Activity & Error Logging Ledger**: Zero-config runtime error and unhandled promise rejection interceptors stream errors to the agent in real time, accompanied by a circular history buffer ledger of recent console outputs and agent actions.
- **🎨 Agent Mode UX Connection Indicators**: Exposes a reactive `useIsAgentConnected()` React hook and toggles the `.aui-agent-mode` class on `document.body` for glowing agent connection styling.

---

## Installation & Local Development

This package is currently in active development and has not been published to the public npm registry yet. To use and test it in your local React application:

### 1. Build and Link the Package
In the root directory of this repository, run:
```bash
npm run build
npm link
```

### 2. Link to Your Application
Navigate to your React application directory (e.g., `examples/frontend`) and link the package:
```bash
npm link react-agent-bridge
```
*(Alternatively, you can install it directly using its relative path: `npm install ../..` or `npm install /path/to/AUI`)*

---

## Basic Configuration

### 1. Babel Plugin
Add the plugin to your Babel configuration (or your framework's build configuration, e.g. Vite React plugin):

```js
// vite.config.js
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import reactAgentBridgeBabelPlugin from 'react-agent-bridge/babel-plugin';

export default defineConfig({
  plugins: [
    react({
      babel: {
        plugins: [reactAgentBridgeBabelPlugin],
      },
    }),
  ],
});
```

### 2. Connect Your App
Import the preflight library at the absolute top of your entry file (before React DOM evaluates) and connect the WebSocket manager:

```js
// main.jsx
import 'react-agent-bridge/preflight'; // MUST be the first import
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import { AgentWebSocketManager } from 'react-agent-bridge';

// Connect to the local AI agent server
AgentWebSocketManager.connect('ws://localhost:8000');

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

---

## 🏃 Running the Example Demo

The repository contains a fully integrated checkout flow frontend and Python LangGraph agent backend in the `/examples` directory.

### Prerequisites
First, build the library from the root directory:
```bash
npm run build
```

### 1. Start the React Frontend
Navigate to the frontend example, install dependencies, and run the dev server:
```bash
cd examples/shopping-cart-flow/frontend
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

### 2. Start the AI Agent Backend
Open a separate terminal, navigate to the agent example, set up a Python virtual environment, install dependencies, and boot the agent:
```bash
cd examples/shopping-cart-flow/agent
python -m venv venv

# On Windows:
.\venv\Scripts\activate
# On macOS/Linux:
# source venv/bin/activate

pip install -r pyproject.toml # or install websockets, langgraph, langchain
python agent.py
```
*(Optional: If you want the agent to use a live LLM planner, add `GEMINI_API_KEY="your-api-key"` to a `.env` file in the `examples/shopping-cart-flow/agent/` directory).*

### 3. Test Agent Interactions
Once the bridge connects, type commands into the Python agent CLI to see your browser react in real-time:
* `add apple` — Semantically clicks the Organic Apple card.
* `coupon SAVE10` — Sets the coupon state and applies it.
* `checkout` — Updates the multi-step navigation to the shipping screen.
* `set name to Bob` — Directly writes "Bob" to the shipping fullName state.
* `place order` — Dispatches the click event to submit the order.

---

## 🧪 Running Tests

The library comes with comprehensive unit and integration tests covering the store, hook transformation, DevTools hook scanner, and WebSocket communication protocols.

To run the test suite:
```bash
npm test
```

---

## License

MIT