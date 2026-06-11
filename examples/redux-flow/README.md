# Redux Toolkit Integration Flow — Example

This example demonstrates how to integrate a standard Redux Toolkit (RTK) global state store with `react-agent-bridge` using the dedicated `bridgeRedux` adapter.

---

## 🚀 Setup & Installation

### 1. Build the monorepo core
From the repository root, run:
```bash
npm run build
```

### 2. Install dependencies
Navigate to this directory, install packages, and link the local framework:
```bash
cd examples/redux-flow
npm install
```

### 3. Start the React Frontend
Start the local development server:
```bash
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 🕵️‍♂️ Verification Path (CLI Validation)

Open a separate terminal window to verify that the Redux state is correctly bridged to the agent registry using the three commands below.

*(Note: If the `react-agent-bridge` CLI tool is not globally on your environment's PATH, you can run it via python: `python -m react_agent_bridge.cli <command>` from the `sdk/python/` directory).*

### 1. Registry Inspection
Verify that the Redux slices are correctly registered in the live bridge component snapshot.

**Command:**
```bash
react-agent-bridge registry
```

**Expected Output:**
```text
Component: ReduxStore (ReduxStore#redux)
  Route: /
  State Slots:
    - counter: {"value":0} [Collection]
    - user: {"name":"Developer"} [Collection]
  Actions: dispatch
```

### 2. Live State Watcher
Listen to real-time state slot transitions as user actions occur in the browser.

**Command:**
```bash
react-agent-bridge watch
```

*Now go to the browser and click the **Increment** or **+3** button. You will see state update notifications immediately in the terminal:*

**Expected Output:**
```text
Watching state changes on ws://localhost:8000... Press Ctrl+C to stop.

[ReduxStore] counter: {"value":0} -> {"value":1}
[ReduxStore] counter: {"value":1} -> {"value":4}
```

### 3. Agent Execution (Action Dispatching)
Verify that the agent planner can dispatch native Redux actions via the `callAction` path to modify global state.

**Command:**
```bash
react-agent-bridge run "increment the counter three times"
```

**Expected Output:**
```text
Executing goal: 'increment the counter three times' using model: 'ollama/qwen2.5:7b'
...
[Success] Goal accomplished!
```
*(In the browser, you will observe the counter value increase by 3.)*

---

## 🧪 Testing the Integrated Tour Script

If you want to run all of these verification phases sequentially in a guided tour environment:
```bash
python agent.py
```
This script will prompt you step-by-step to click the application, observe state modifications, and run the automated planning goal, demonstrating the complete Redux bridge capabilities.

