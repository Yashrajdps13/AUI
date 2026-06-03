# Command Audit Log (T3-A) Example Flow

This example demonstrates the **Command Audit Log** feature. It showcases how a separate, append-only ledger tracks all agent mutation commands (`setState`, `dispatchEvent`, `callAction`), how sensitive data (PII) is automatically redacted, and how developers can view/clear the log.

## Features Illustrated
1. **Append-Only Command Log**: Keeps a structured log history of all write operations (unlike the circular console output ledger).
2. **Auto Redaction**:
   - `setState` on hooks marked `/** @sensitive */`.
   - `callAction` on stores/actions with credentials/login/passwords.
3. **Live Inspector**: The frontend displays a real-time list of commands executed by the agent, and allows the developer to clear the logs explicitly.
4. **Agent Querying**: The agent can request a full snapshot of the audit log using the `queryAuditLog` command.

---

## Setup & Running the Example

### 1. Build the library
Ensure the standard library is compiled first. In the repository root, run:
```bash
npm run build
```

### 2. Run the React Frontend
Navigate to the frontend folder and install packages, then start the Vite dev server:
```bash
cd examples/audit-flow/frontend
npm install
npm run dev
```
Open your browser and navigate to the local URL (e.g. `http://localhost:5173`).

### 3. Run the Python Agent
Navigate to the agent folder, set up a virtual environment, install dependencies, and run:
```bash
cd examples/audit-flow/agent
python -m venv venv
.\venv\Scripts\activate
pip install websockets python-dotenv
python agent.py
```

---

## Interactive Steps to Try

Once the agent terminal says `[Bridge Connected] React application successfully linked!`, enter these commands in the agent console:

1. **`registry`**: Note that `ssn` is marked as `[SENSITIVE]`.
2. **`fill`**: Sets the username to `hacker_agent` and the sensitive SSN to `999-88-7777`.
3. **`login`**: Calls the `AuthStore.login` action with credentials.
4. **`click`**: Clicks the form submit button in the browser.
5. **`audit`**: Query the command audit log. Note that:
   - The `username` value `hacker_agent` is recorded as-is.
   - The sensitive `ssn` value is redacted to `"[REDACTED]"`.
   - The `login` action arguments `["admin", "supersecret123"]` are redacted to `"[REDACTED]"`.
   - The click action is fully audited.
6. **Clear Logs (Frontend UI)**: Click the "Clear Logs" button in the browser app. Query `audit` again on the agent, and verify it is empty.
