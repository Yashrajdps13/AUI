# react-agent-bridge

🌉 **Zero-friction npm framework giving AI agents semantic read-write access to React internal state.**

`react-agent-bridge` intercepts your React Fiber tree and `useState` hooks at runtime, giving AI agents (like LangGraph, Playwright agents, or custom LLM loops) real-time access to application state and component DOM nodes—with **zero component-level code modifications**.

---

## Features

- **🔌 Zero-Friction Setup**: One Babel plugin and one entrypoint import. No wrappers, hooks, or context changes in your actual application code.
- **🕵️‍♂️ Passive Discovery Mode & SQLite Session Recorder**: Automatically records human user sessions (clicks, text changes, state transitions) into a local SQLite database (`discovery.db`) to reconstruct high-fidelity workflow pathways.
- **📈 Outcome-Based Workflow Inference Engine**: Analyzes recorded sessions to discover state slots reaching terminal completion values, cluster temporal slot transitions into step phases, identify step preconditions, and generate developer-reviewable YAML/Markdown workflow definitions (`agent-context.md`).
- **🤖 Automated Agent Runner & Replay Engine**: Boots an autonomous planner that parses compiled goal states, schedules action sequences using standard LLMs, and falls back to **Golden Trace Replay** to replay parameterized user interactions (clicks, state updates) in under a second with **0 LLM calls**.
- **📝 JSDoc Annotation Extraction**: Automatically parses developer JSDoc block comments (`/** ... */`) preceding `useState` declarations at build-time to provide semantic descriptions of state slots to the agent.
- **👁️ Dynamic Element Visibility & Disabled States**: Interactive element scanner detects computed CSS visibility (display, visibility, opacity) and HTML/ARIA disabled properties to prevent agent interactions with hidden or inactive fields.
- **🤝 Render Settlement Handshakes**: Hooks into React DevTools commits to notify the agent backend when rendering and layout updates have fully settled, eliminating execution race conditions.
- **🧠 Semantic Registry**: Live, hierarchical registry of active components and state variables.
- **⚡ State Subscriptions & Diffs**: Real-time push notifications to the agent when watched states change, minimizing websocket chatter.
- **✍️ Semantic Read & Write**: The agent can read state values and dispatch state mutations securely.
- **🎯 Host DOM Binding**: Correlates virtual component state slots to their exact browser DOM nodes for high-fidelity click, change, and focus event dispatches.
- **🚫 Safe Agent Mutation Rules**: Enforces strict page context constraints (preventing mutations of elements not visible in the DOM) and excludes direct collection/array state updates to protect data integrity.
- **🚨 Activity & Error Logging Ledger**: Zero-config runtime error and unhandled promise rejection interceptors stream errors to the agent in real time, accompanied by a circular history buffer ledger of recent console outputs and agent actions.
- **🎨 Agent Mode UX Connection Indicators**: Exposes a reactive `useIsAgentConnected()` React hook and toggles the `.aui-agent-mode` class on `document.body` for glowing agent connection styling.

---

## Installation & Local Development

This package is currently in active development. To use and test it in your local React application:

### 1. Build and Link the Package
In the root directory of this repository, run:
```bash
npm run build
npm link
```

### 2. Link to Your Application
Navigate to your React application directory (e.g., `examples/discovery-flow`) and link the package:
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

## 🏃 Running the Discovery Mode & Automated Agent Demo

The repository contains a fully integrated checkout flow frontend and Python LangGraph agent backend in the `/examples/discovery-flow` directory demonstrating session recording, context generation, and trace replay.

### Prerequisites
First, build the library from the root directory:
```bash
npm run build
```

### 1. Start the React Frontend
Navigate to the discovery flow example, install dependencies, link the framework, and run the dev server:
```bash
cd examples/discovery-flow
npm install
npm link react-agent-bridge
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

### 2. Run Passive Observation (Discovery Mode)
Open a separate terminal, navigate to the example, and run the Python playground:
```bash
cd examples/discovery-flow
python agent.py
```
Select option **`1`** (`Run passive discovery server`).

1. Go to your browser at [http://localhost:5173](http://localhost:5173).
2. Fill out the details (Attendee Name, Email). Click **Next Step**.
3. Select options (Ticket category, sessions). Click **Next Step**.
4. Enter Credit Card details. Click **Confirm and Pay**.
5. Observe the "Bridge Activity Log" in the UI to see how PII data is auto-redacted and recorded.
6. Click **Reset Form** and repeat the sequence **3 or more times** (each page reload/reset represents a session).
7. In the Python terminal, press **`Ctrl+C`** to finalize the observation.

This generates/updates **`agent-context.md`** containing:
* **Slot Annotations**: `@sensitive` markers on email and card numbers, collections list types, and derived total cost.
* **Workflows**: Multi-step flow steps extracted from sequential observation.
* **Constraints**: sequencing, write-protection, and page routing scope rules.

### 3. Try Golden Trace Replay
Once `agent-context.md` is generated, run `agent.py` again:
```bash
python agent.py
```
Select option **`2`** (`Run automated agent runner`).

1. The agent will formulate a Goal pointing directly to active state slots.
2. **Run 1 (Direct LLM)**: Plans step by step using LLM calls. This compiles and records a **Golden Trace** in the local database.
3. Once Run 1 completes, click **Reset Form** in the browser, and press **Enter** in the Python console.
4. **Run 2 (Golden Trace Replay)**: The runner detects a matching golden trace and executes it instantly with **0 LLM calls**, resulting in an immediate 50–80% planning speedup!

---

## 🧪 Running Tests

The library comes with comprehensive unit and integration tests covering the store, hook transformation, DevTools hook scanner, and WebSocket communication protocols.

To run the test suite:
* **Javascript/Vitest Tests**:
  ```bash
  npm test
  ```
* **Python SDK Tests**:
  ```bash
  cd sdk/python
  python -m pytest
  ```

---

## License

MIT