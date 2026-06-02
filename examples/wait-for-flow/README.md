# AUI Async & waitFor Handshake Example

This example demonstrates the T2-A `waitFor` condition handshake protocol, which allows agents to cleanly coordinate multi-step workflows around asynchronous processes (like API calls and loaders) without guessing delays.

## How to Run

### 1. Compile the Library

```bash
# In the repository root
npm run build
```

### 2. Run the Frontend

```bash
cd examples/wait-for-flow/frontend
npm install
npm run dev
```

### 3. Run the Agent CLI

```bash
cd examples/wait-for-flow/agent
python -m venv venv
# On Windows
venv\Scripts\pip install -e .
venv\Scripts\python agent.py
```
