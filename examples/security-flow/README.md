# AUI Write-Side Security Scoping Example

This example demonstrates the T2-B Write-Side Security Scoping guard. It configures the bridge to only allow state and event modifications on public forms, preventing agents from altering restricted state machines or clicking dangerous control targets.

## How to Run

### 1. Compile the Library

```bash
# In the repository root
npm run build
```

### 2. Run the Frontend

```bash
cd examples/security-flow/frontend
npm install
npm run dev
```

### 3. Run the Agent CLI

```bash
cd examples/security-flow/agent
python -m venv venv
# On Windows
venv\Scripts\pip install -e .
venv\Scripts\python agent.py
```
