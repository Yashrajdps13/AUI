# Redux Toolkit Integration Flow — Example

This example demonstrates how to integrate a standard Redux Toolkit (RTK) global state store with `react-agent-bridge` using the dedicated `bridgeRedux` adapter. 

It showcases how state slices are mapped to read-only slots, how dispatches are safely wrapped to satisfy RTK plain-object constraints, and how LLM planners leverage registry metadata to control global application state.

---

## 🧠 How It Works (Architecture)

The `bridgeRedux` adapter bridges a standard Redux store into the `react-agent-bridge` component state registry:

1. **State Slices to Registry Slots**: Every slice registered in the root reducer (e.g., `counter`, `user`) is exposed as a state slot on a virtual component identifier `ReduxStore#redux`.
2. **Read-Only Enforcement**: Redux state must only be modified via dispatches. Direct state setter modifications are prohibited. The adapter enforces this by throwing errors on direct writes and setting the slot property `writeable: 'user'`.
3. **Dispatch Wrapper & Plain-Object Transform**: Redux Toolkit requires all actions passed to `dispatch` to be plain objects. Smaller LLMs and automation scripts prefer simple action name strings. The bridge wraps the native `dispatch` action, automatically converting input strings (e.g., `'counter/increment'`) into correct RTK action objects (e.g., `{ type: 'counter/increment', payload: undefined }`).
4. **Metadata & Planner Guidance**: Since action types are dynamic, LLM planners cannot automatically guess the names of valid actions accepted by the store. By passing a metadata dictionary to `bridgeRedux`, developers can specify slice descriptions that explicitly guide the LLM on which action strings to use.

```javascript
// src/store.js
const metadata = {
  counter: { description: 'Simple global click counter slice. Dispatched via Redux action string "counter/increment", "counter/decrement", or "counter/incrementByAmount"' },
  user: { sensitive: false, description: 'User profile details containing developer name. Dispatched via Redux action string "user/setName" with payload' },
};

export const store = bridgeRedux(
  configureStore({
    reducer: { counter: counterSlice.reducer, user: userSlice.reducer }
  }),
  metadata,
  'ReduxStore'
);
```

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
    - counter: {"value":0} [Collection] [Readonly]
        Description: Simple global click counter slice. Dispatched via Redux action string "counter/increment", "counter/decrement", or "counter/incrementByAmount"
    - user: {"name":"Developer"} [Collection] [Readonly]
        Description: User profile details containing developer name. Dispatched via Redux action string "user/setName" with payload
  Actions:
    - dispatch
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

