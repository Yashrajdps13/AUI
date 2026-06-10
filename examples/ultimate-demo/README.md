# Enterprise Project Dashboard — Ultimate Demo & Guided Tour

Welcome to the **Ultimate Demo** for `react-agent-bridge` (AUI). This project is a realistic, product-grade project management dashboard featuring user authentication, project portfolios, task boards, profile settings, and computed metrics.

This codebase is designed as a **guided tour** to show you every capability of the react-agent-bridge framework—with **zero application code modifications**—using our global developer command-line interface (CLI).

---

## 🚀 Setup & Installation

Before exploring the features, build the core framework and install dependencies.

### 1. Build the monorepo core
From the repository root, run:
```bash
npm run build
```

### 2. Install example dependencies and link
Navigate to this directory, install packages, and link the local framework:
```bash
cd examples/ultimate-demo
npm install
npm link react-agent-bridge
```

### 3. Start the React Frontend
Start the local development server:
```bash
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser. You will see the Enterprise Gateway login portal.

---

## 🧠 LLM Provider Configuration (Four-Level Resolution)

When running agent goals, `react-agent-bridge` compiles your natural language queries and schedules execution paths. It resolves which LLM to query using a **four-level resolution hierarchy**:
1. **Explicit CLI Flag**: `--model <model_string>`
2. **Environment Variable**: `REACT_AGENT_BRIDGE_MODEL`
3. **Global Configuration File**: `~/.react-agent-bridge/config.json`
4. **Recommended Default**: Ollama (`ollama/qwen2.5:7b`) running locally on port 11434.

### The First Step: Running Setup
To configure your provider globally on your machine, run:
```bash
react-agent-bridge setup
```
*Equivalent SDK path:* [__main__.py](file:///c:/Users/Utkarsh%20Ranjan/Desktop/AUI/sdk/python/react_agent_bridge/__main__.py)

**Interactive Menu Prompt:**
```text
=== React Agent Bridge LLM Configuration ===
Please select your preferred LLM provider:
1. Ollama (free, local, no API key, recommended default)
2. Gemini
3. OpenAI
4. Groq
5. Other (manual LiteLLM model string)
Select provider (1-5): 1
Checking if Ollama is running locally...
[SUCCESS] Ollama detected running locally.
Configuration saved successfully to C:\Users\<Username>\.react-agent-bridge\config.json
```

---

## 🕵️‍♂️ Guided Tour of Features

Now, open a separate terminal to walk through every core feature of the framework using the CLI utility.

### Feature 1: Connection Health Check
Verify that the browser React app is successfully linked to the agent bridge. The React application displays a visual connection glow indicator in the header (powered by the React hook `useIsAgentConnected()`).

**Run the CLI command:**
```bash
react-agent-bridge connect
```
*Equivalent SDK method:* `await bridge.wait_for_client()`

**Sample Output:**
```text
Connecting to React application on ws://localhost:8000...

================ Health Check ================
Status:            [CONNECTED]
React App Name:    App
Component Count:   6
Mounted Routes:    /
==============================================
```

---

### Feature 2: Semantic Component Registry & JSDoc Annotations
The bridge extracts developer JSDoc block comments preceding `useState` calls at build-time to provide semantic descriptions to the agent.
1. **Sensitive Fields**: The password field on login is marked `/** @sensitive */`. Its value is never transmitted plain-text to the agent or planner.
2. **Write-Restricted Fields**: The completion efficiency rate on the analytics page is marked `/** @writeable user */`. The agent is blocked from writing to it.
3. **Collection Slots**: Arrays (like list items) are marked so the planner knows not to perform direct mutation commands, but rather use buttons.

**Run the CLI command:**
```bash
react-agent-bridge registry
```
*Equivalent SDK method:* `bridge.graph.get_mounted_components()`

**Sample Output:**
```text
================ Component Registry ================

Component: App (App#r9)
  Route: /
  State Slots:
    - isAuthenticated: false
    - user: {"name":"Developer","email":"dev@agent.com"} [Collection]
    - notifications: {"email":true,"slack":false} [Collection]

Component: LoginView (LoginView#r11)
  Route: /
  State Slots:
    - email: "dev@agent.com"
    - password: "[REDACTED]" [Sensitive]
    - error: ""
```

---

### Feature 3: Live State Change Watcher
Watch state transitions in real time as humans interact with the browser page.

**Run the CLI command:**
```bash
react-agent-bridge watch
```
*Equivalent SDK listener:* `bridge.add_listener("state_update", callback)`

**Sample Output:**
*(Click "Sign In" in the browser with password "secretpassword")*
```text
Watching state changes on ws://localhost:8000... Press Ctrl+C to stop.

[LoginView] email: "" -> "dev@agent.com"
[LoginView] password: "[REDACTED]" -> "[REDACTED]"
[App] isAuthenticated: false -> true
```

---

### Feature 4: Goal Execution & Safe State Mutation
The agent compiler translates natural language queries into structured goal checklists, parses route contexts, checks preconditions, and executes steps. 

** ZUSTAND ACTIONS VS DIRECT STATE MUTATION:**
To maintain state consistency, the agent is restricted from directly mutating collections (like adding tasks by overwriting the `projects` array). Instead, the planner is forced to click the form buttons which dispatch Zustand actions like `addTask` and `markTaskComplete`.

**Run the CLI command:**
```bash
react-agent-bridge run "Log in with password 'secretpassword', create project 'Synergy Core', open it, add task 'Setup Bridge' for Alice, and mark it complete."
```
*Equivalent SDK method:* `await runner.execute(goal)`

**Sample Output:**
```text
Successfully compiled Goal!
  Description: Complete Synergy Core setup
  Success Conditions:
    - App.isAuthenticated equals true
    - App.projects includes project Synergy Core
    - Task "Setup Bridge" is completed on project Synergy Core

[Trace Replay] No matching trace found. Initiating LLM Planning...
[LLM Planner] Step 1: Setting App#r9.email to "dev@agent.com"
[LLM Planner] Step 2: Setting App#r9.password to "[REDACTED]"
[LLM Planner] Step 3: Clicking button#btn-login
[LLM Planner] Step 4: Setting input#new-project-name to "Synergy Core"
[LLM Planner] Step 5: Clicking button#btn-create-project
[LLM Planner] Step 6: Clicking link#link-project-proj-12498239
[LLM Planner] Step 7: Setting input#new-task-title to "Setup Bridge"
[LLM Planner] Step 8: Selecting Alice in select#new-task-assignee
[LLM Planner] Step 9: Clicking button#btn-add-task
[LLM Planner] Step 10: Clicking button#btn-complete-task-task-12498240

[Success] Goal accomplished! Steps taken: 10
```

---

### Feature 5: Command Audit Log & PII Redaction
All agent-initiated mutation commands (`setState`, `dispatchEvent`, `callAction`) are logged in an append-only ledger on the client. Sensitive data is automatically redacted on-the-fly.

**Run the CLI command:**
```bash
react-agent-bridge audit
```
*Equivalent SDK method:* `await bridge.query_audit_log()`

**Sample Output:**
```text
================ Command Audit Log ================
[19:35:12] setState on LoginView#r11.email -> SUCCESS
  Value: dev@agent.com
[19:35:14] setState on LoginView#r11.password -> SUCCESS
  Value: [REDACTED]
[19:35:15] dispatchEvent on LoginView#r11.click -> SUCCESS
  Value: button#btn-login
[19:35:18] callAction on App#r9.createProject -> SUCCESS
  Value: Synergy Core
===================================================
```

---

### Feature 6: Browser Console Output capture
The SDK captures browser `console.log`, `console.warn`, `console.error` and unhandled promise rejections automatically.

**Run the CLI command:**
```bash
react-agent-bridge logs
```
*Equivalent SDK method:* `await bridge.query_ledger()`

**Sample Output:**
```text
================ Browser Logs ================
[19:35:10] [INFO] [CONSOLE] React Agent Bridge WebSocket established.
[19:35:14] [INFO] [CONSOLE] setState App.password to "[REDACTED]"
[19:35:15] [INFO] [CONSOLE] callAction loginAction completed successfully
==============================================
```

---

### Feature 7: Passive Discovery & Workflow Inference
Record actual human walkthroughs to build the workflow blueprint (`agent-context.md`) and capture parameterized **Golden Traces** to skip future LLM calls entirely.

**Run the CLI command:**
```bash
react-agent-bridge discover --db ./discovery.db --context-out ./agent-context.md
```
*Equivalent SDK session run:* `session = bridge.discover()`

1. Run the command and navigate to the application in your browser.
2. Complete the entire login -> create project -> complete task flow **3 times**.
3. Press `Ctrl+C` in your terminal to shut down recording.
4. The workflow engine will cluster state transitions, request Ollama/Gemini to write plain-English descriptions, discover sequencing constraints, and write them to `agent-context.md`.

---

## 🧪 Testing the Integrated Tour Script
If you want to run all of these phases sequentially in a guided tour environment:
```bash
python agent.py
```
This script will prompt you step-by-step to click the application, observe state modifications, run goals, check audit ledgers, and execute discovery mode.
