# AUI Zustand Flow Example

This example demonstrates bridging a Zustand global store using the `bridgeZustand` adapter. It highlights state synchronization, custom callable actions, and PII masking.

## How to Run

### 1. Install & Build the Core Package

Ensure the root `react-agent-bridge` package is built:

```bash
# In the repository root
npm run build
```

### 2. Run the Frontend

Install dependencies and start the Vite dev server:

```bash
cd examples/zustand-flow/frontend
npm install
npm run dev
```

### 3. Run the Agent CLI

Create a python environment, install dependencies, and run:

```bash
cd examples/zustand-flow/agent
# Using uv (or venv + pip)
uv venv
source .venv/bin/activate # or .venv\Scripts\activate on Windows
uv pip install -e .
python agent.py
```
