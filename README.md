# react-agent-bridge

🌉 **Zero-friction npm framework giving AI agents semantic read-write access to React internal state.**

`react-agent-bridge` intercepts your React Fiber tree and `useState` hooks at runtime, giving AI agents (like LangGraph, Playwright agents, or custom LLM loops) real-time access to application state and component DOM nodes—with **zero component-level code modifications**.

---

## 💡 Why This Exists

Today, AI agents interact with web applications the same way humans do: by scraping raw HTML DOM trees (using Playwright or Puppeteer) or processing visual screenshots (using VLMs). 

This approach is fundamentally broken for developers building production-grade agentic systems:
* **Extremely Brittle**: Modern web apps use dynamic CSS classes, layout reflows, and complex single-page routing. A minor visual style update or class name change breaks the agent's selectors instantly.
* **Tokens & Latency Waste**: Sending raw DOM trees or high-res screenshots to an LLM on every single step is slow, expensive, and quickly hits context window limitations.
* **Zero Internal Visibility**: Agents operate in a black box. They cannot see loading indicators, hidden validation errors, asynchronous fetch state, or client-side store variables (like Zustand, Redux, or React context) until they are rendered visually.
* **Execution Race Conditions**: Agents click buttons and type inputs without knowing when React has finished rendering, leading to unstable test runs and execution failures.

### The React-Agent-Bridge Paradigm
`react-agent-bridge` shifts the paradigm: **it treats the UI not as a document of pixels, but as a live state graph.** 

By hooking directly into the React Fiber tree at runtime, it exposes a semantic, structured interface of your application’s state and actions directly to your AI agent backend. 

* Instead of scraping a page to check if logged in, the agent checks `ZustandStore#AuthStore.isAuthenticated`.
* Instead of typing letters into an input and hoping the value bound correctly, the agent mutates a state slot or dispatches a semantic action.
* Instead of guessing when a page is done loading, the agent relies on a native **Render Settlement Handshake** that fires only when React finishes updating the layout.

The result is agentic control that is **10x faster, 100x cheaper, and rock-solid resilient**.

---

## 🛠️ Key Capabilities & Features

* **🔌 Zero-Friction Setup**: Integrate with a single entry point import and build-time plugin without modifying any of your existing components, hooks, or context layouts.
* **🕵️‍♂️ Automatic Workflow Capture**: Automatically record human user sessions (clicks, inputs, route changes, and state transitions) in the background to visually capture precise developer/user pathways.
* **📈 Inferred Workflow Blueprints**: Automatically translate recorded human sessions into structured, developer-editable Markdown manuals detailing preconditions, step sequences, and successful goal outcomes.
* **🤖 Instant Zero-LLM-Cost Replays**: Replay parameter-mapped user paths (e.g. submitting forms, changing pages) in under a second with zero LLM API call costs by reusing previously completed golden traces.
* **📝 Clean Semantic Descriptions**: Provide direct context and metadata to your agent by simply writing standard JSDoc comments above state variables, keeping security policies alongside your code.
* **🤝 Zero Execution Race Conditions**: Guarantee execution stability by ensuring the agent only proceeds to subsequent actions when React rendering and layout updates have fully settled.
* **🚫 Safety & State Integrity Guarantees**: Restrict write access on sensitive variables, prevent direct mutations of computed/read-only slots, and block interactions with hidden or disabled elements.
* **🚨 Real-Time Error Interception**: Automatically stream runtime errors, promise rejections, and browser console warnings directly to the agent to debug failures instantly.
* **🎨 Agent-Aware Styling**: Use a native React hook or automatic body styling to change the app UI dynamically when an agent is active, giving users clear visual indicators of agent activity.

---

## 🚀 Installation & Local Development

This package is currently in active development. To use and test it in your local React application:

### 1. Build and Link the Core Package
In the root directory of this repository, run:
```bash
npm run build
npm link
```

### 2. Install and Link the Python SDK & CLI
To register the global `react-agent-bridge` command-line utility on your machine:
```bash
cd sdk/python
pip install -e .
```
*(This registers the global CLI script. You can also run it via `python -m react_agent_bridge` if your pip bin paths are not bound to your environment's PATH.)*

### 3. Link to Your Application
Navigate to your React application directory (e.g., `examples/discovery-flow`) and link the package:
```bash
npm link react-agent-bridge
```
*(Alternatively, you can install it directly using its relative path: `npm install ../..` or `npm install /path/to/AUI`)*

---

## ⚙️ Basic Configuration

### 1. Babel Plugin Integration
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

### 2. Connect Your App Preflight
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

## 📝 JSDoc Annotations & Code Comments

`react-agent-bridge` automatically extracts JSDoc block comments (`/** ... */`) preceding `useState` declarations at build-time. This provides the agent/bridge with semantic metadata and enforces security/access policies directly from your source code.

### 1. Supported Annotations

* **`/** @sensitive */`**: Marks a state slot as holding sensitive data (e.g., passwords, card numbers).
  * *Effect:* The value of this state slot is redacted (masked to `"[REDACTED]"`) before being passed to the agent planner or recorded in trace logs. The agent can write to these fields but cannot read their plain-text values back.
* **`/** @writeable user */`**: Restricts write access for the state slot to humans only.
  * *Effect:* Enforces a strict read-only policy for AI agents. Any attempt by the agent to mutate this slot via `setState` will be blocked by the Rules Engine. Useful for calculated values (e.g., total price, completion rates).
* **Descriptive Comments**: Any comment string within the JSDoc block.
  * *Effect:* Passed to the agent as description metadata. This gives LLMs semantic context on what a slot represents, preventing hallucination.

### 2. Code Example

```js
// src/Dashboard.jsx
import React, { useState } from 'react';

function Dashboard() {
  /** 
   * The current user's authentication token
   * @sensitive 
   */
  const [token, setToken] = useState('');

  /** 
   * Computed success percentage of the current portfolio.
   * @writeable user 
   */
  const [efficiencyRate, setEfficiencyRate] = useState(0);

  /** Name of the project entered in the creation form */
  const [projectName, setProjectName] = useState('');
  
  // ...
}
```

### 3. How the Bridge Ingests Metadata
1. **Babel Transformation**: The custom Babel plugin parses JSDoc comment blocks preceding `useState` hooks and extracts the metadata.
2. **Registry Mapping**: It binds these descriptions, sensitivity flags, and writeable restrictions directly to the virtual component state slots.
3. **Prompt Enrichment**: The bridge serves these annotations dynamically to the LLM agent runner during planning so the agent knows:
   - What the variables mean.
   - What fields are sensitive (and must be handled securely).
   - What fields are read-only (and must not be mutated).

---

## 🕵️‍♂️ Passive Discovery & Golden Trace Replay

`react-agent-bridge` features a built-in session recording, workflow inference, and instant execution system that enables zero-LLM-cost replays of complex multi-step forms and dashboards.

### 1. Passive Discovery Mode
When you run your application in **Discovery Mode**, the bridge acts as a passive recorder:
* **Session Recording**: Captures every user event—clicks, keystrokes, route changes, React state values, and console outputs—and streams them to a local SQLite database (`discovery.db`).
* **Workflow Clustering**: Upon stopping the recorder, the Outcome-Based Workflow Inference Engine analyzes the database. It clusters temporal state transitions, identifies target completion terminal states, and discovers preconditions (e.g., "Authentication token must be present before adding tasks").
* **Developer Agent Context**: The engine outputs an automated, reviewable `agent-context.md` file. This acts as the semantic map/guidebook for your agent, describing discovered paths, valid state ranges, and sequencing constraints.

> [!TIP]
> To launch discovery mode on a connected app, simply run:
> ```bash
> react-agent-bridge discover
> ```
> Complete your workflow in the browser, then press `Ctrl+C` in your terminal to compile the session records into `agent-context.md`.

### 2. Golden Trace Replay
Once a workflow has been successfully completed (either by a human during discovery or by the agent during a successful planning run), it is saved in the SQLite trace store as a **Golden Trace**.

* **Zero-LLM Execution**: When the Agent Runner receives a goal matching a known golden trace structure, it bypasses the LLM planner entirely.
* **Parameter Mapping**: It extracts parameter variables (e.g., matching the new target project name or password inputs) and maps them directly onto the historical trace steps.
* **Fast-Path Replay**: Dispatches the mapped sequence of events directly via the browser/web socket connection, executing complex flows in under **1 second** with **zero LLM cost**.
* **Settlement Syncing**: Replay commands wait for the settlement handshake before triggering subsequent steps, guaranteeing robustness against slow network requests or asynchronous rendering delays.

---

## 🛠️ Developer CLI Utility

The `react-agent-bridge` command-line utility provides immediate, zero-friction debugging, inspection, and health checks for any connected React application.

### LLM Provider Resolution (Four-Level Resolution)
When compiling natural language goals or executing plans, the utility determines which model/provider to use using a four-level hierarchy:
1. **Explicit Flag**: `--model <model_string>` (e.g., `--model gemini/gemini-1.5-flash` or `--model groq/llama3`)
2. **Environment Variable**: `REACT_AGENT_BRIDGE_MODEL`
3. **Global Config File**: `~/.react-agent-bridge/config.json` (created via `react-agent-bridge setup`)
4. **Recommended Default**: Ollama (`ollama/qwen2.5:7b`) running locally on port 11434.

### CLI Commands Reference

| CLI Command | Equivalent Python SDK Call | Purpose / Action |
|:---|:---|:---|
| **`setup`** | *N/A (config initialization)* | Launch the interactive menu setup to configure preferred model providers (Ollama, Gemini, OpenAI, Groq, Custom) and store credentials securely in `~/.react-agent-bridge/config.json`. |
| **`connect`** | `await bridge.wait_for_client()` | Verify WebSocket connection state and print linked app metadata (App Name, active component count, and current route list). |
| **`registry`** | `bridge.graph.get_mounted_components()` | Dump the active components, slots, types, descriptions, JSDoc tags, and visible interactive DOM selector elements. |
| **`watch`** | `bridge.add_listener("state_update", ...)` | Connect and listen in real time to state changes (slot, previous value, new value) as human users click and type in the browser. |
| **`run "<goal>"`** | `await runner.execute(goal)` | Compile the query into structured success/failure conditions and run the LangGraph planner, utilizing LLM actions and Golden Trace Replay. |
| **`audit`** | `await bridge.query_audit_log()` | Output the append-only command ledger containing all agent state changes and dispatched actions (with automatic sensitive value redaction). |
| **`logs`** | `await bridge.query_ledger()` | Fetch and output browser console outputs (`console.log`, `console.warn`, `console.error`) and unhandled promise exceptions. |
| **`discover`** | `session = bridge.discover()` | Start a passive observer server to record human walkthrough actions. Generates the `agent-context.md` file and sequencing rules upon pressing `Ctrl+C`. |

---

## 📂 Repository Examples Matrix

The AUI repository includes a comprehensive set of test apps and guided agent flows under the `examples/` folder.

| Example Directory | Focus / Highlights | Frontend Command | Agent / Script Command |
|:---|:---|:---|:---|
| **[ultimate-demo](examples/ultimate-demo)** | Product-grade project board with Auth, Settings, analytics, `@sensitive` values, and `@writeable user` read-only slot protection. Full SDK guided tour. | `cd examples/ultimate-demo` <br> `npm run dev` | `cd examples/ultimate-demo` <br> `python agent.py` |
| **[discovery-flow](examples/discovery-flow)** | Multi-step ticket registration flow demonstrating SQLite session logging, outcome step clustering, sequencing constraint inference, and Golden Trace replay. | `cd examples/discovery-flow` <br> `npm run dev` | `cd examples/discovery-flow` <br> `python agent.py` |
| **[zustand-flow](examples/zustand-flow)** | Bridges Zustand global store, demonstrates component-less bindings and direct array mutation validation. | `cd examples/zustand-flow/frontend` <br> `npm run dev` | `cd examples/zustand-flow/agent` <br> `python agent.py` |
| **[redux-flow](examples/redux-flow)** | Bridges Redux Toolkit global store slices, enforces read-only state rules, wraps dispatches to plain objects, and injects slice metadata for LLM planning guidance. | `cd examples/redux-flow` <br> `npm run dev` | *Explore using the CLI utility* (e.g. `react-agent-bridge registry`) |
| **[wait-for-flow](examples/wait-for-flow)** | Focuses on asynchronous mounting and state settlement delay verification. | `cd examples/wait-for-flow` <br> `npm run dev` | *Explore using the CLI utility* (e.g. `react-agent-bridge run`) |
| **[security-flow](examples/security-flow)** | Focuses on sensitive password field masking and read-only slot protection tests. | `cd examples/security-flow` <br> `npm run dev` | *Explore using the CLI utility* (e.g. `react-agent-bridge registry`) |
| **[routing-flow](examples/routing-flow)** | Verifies page route transitions and virtual slot condition checking. | `cd examples/routing-flow` <br> `npm run dev` | *Explore using the CLI utility* |
| **[audit-flow](examples/audit-flow)** | Tests command audit logs logging and circular console log histories. | `cd examples/audit-flow` <br> `npm run dev` | *Explore using the CLI utility* (e.g. `react-agent-bridge audit`) |

---

## 🧪 Running Tests

The library comes with comprehensive unit and integration tests covering the store, hook transformation, DevTools hook scanner, and WebSocket communication protocols.

### 1. JavaScript / Vitest Core Tests
```bash
# In the repository root
npm test
```

### 2. Python SDK / Planner Tests
```bash
# In the sdk/python directory
cd sdk/python
python -m pytest
```

---

## 📄 License

MIT