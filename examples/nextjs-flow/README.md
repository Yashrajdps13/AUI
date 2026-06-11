# nextjs-flow

A Next.js 14 App Router example demonstrating how `react-agent-bridge` integrates with Server and Client Components using direct API calls.

## Project Structure

| File | Component Type | Instrumented? |
|:---|:---|:---|
| `app/page.tsx` | Server Component | ❌ No — plugin skips Server Components |
| `app/counter/page.tsx` | Server Component | ❌ No |
| `app/counter/CounterClient.tsx` | **Client Component** | ✅ Yes — `count` slot is tracked |
| `app/readonly/ReadonlyRateClient.tsx` | **Client Component** | ✅ Yes — `efficiencyRate` slot (`@writeable user`) |
| `app/providers.tsx` | **Client Component** | ✅ Yes — connects the WebSocket client |

## Setup & Running

### 1. Start the Frontend
Install dependencies and run the Next.js dev server:
```bash
cd examples/nextjs-flow
npm install
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

### 2. Run the Deterministic Walkthrough
In a separate terminal:
```bash
cd examples/nextjs-flow
python agent.py
```

Step through the interactive command line prompt:
1. **Navigate to /counter**: Triggers programmatic navigation from the Home page (`/`) to the Counter page (`/counter`).
2. **Increment Counter**: Programmatically dispatches click events to the increment button 5 times, verifying live state graph updates.
3. **Navigate back to Home**: Programmatically returns to `/`.
4. **Navigate to /readonly**: Opens the Read-only page.
5. **Verify Safety Rule**: Attempts to directly write to the `@writeable user` slot (`efficiencyRate`) via `setState`. The Rules Engine immediately rejects the command on the backend.
6. **Command Audit Log**: Prints the append-only command audit log and browser ledger console logs recorded by the bridge.
