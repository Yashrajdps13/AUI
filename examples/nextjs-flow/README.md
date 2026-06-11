# nextjs-flow

A minimal **Next.js 14 App Router** example demonstrating how `react-agent-bridge` integrates with Server and Client Components.

## What This Shows

| File | Component Type | In Agent Registry? |
|:---|:---|:---|
| `app/page.tsx` | Server Component | ❌ No — plugin skips files without `'use client'` |
| `app/counter/page.tsx` | Server Component | ❌ No |
| `app/counter/CounterClient.tsx` | **Client Component** | ✅ Yes — `count` slot is tracked |
| `app/readonly/ReadonlyRateClient.tsx` | **Client Component** | ✅ Yes — `efficiencyRate` slot (`@writeable user`) |
| `app/providers.tsx` | **Client Component** | ❌ No — no useState calls |

## Key Pattern

1. `app/providers.tsx` is a `'use client'` component that calls `AgentWebSocketManager.connect()` in a `useEffect`. This is the only place the connection is established.

2. `app/layout.tsx` is a Server Component that wraps children with `<Providers>`. The agent connection is available throughout the app.

3. Client Components declare `'use client'` at the top of the file. The Babel plugin detects this and transforms `useState` calls into instrumented `useBridgeState` calls.

4. Server Components have **no** `'use client'` directive. The Babel plugin skips them entirely — they run on the server and are never instrumented.

## Setup

```bash
# From this directory
npm install
npm run dev
```

The app starts at http://localhost:3000.

The Babel plugin is configured via [`babel.config.js`](./babel.config.js) using `next/babel` as the base preset:

```js
// babel.config.js
module.exports = {
  presets: ['next/babel'],
  plugins: ['react-agent-bridge/babel-plugin'],
};
```

When `babel.config.js` is present, Next.js automatically switches from SWC to Babel. No changes to `next.config.mjs` are needed.

## Verify with the CLI

With the app running and `react-agent-bridge` CLI installed:

```bash
# See which components are registered
react-agent-bridge registry

# Watch live state changes as you click the counter
react-agent-bridge watch
```

You should see `CounterClient` and `ReadonlyRateClient` in the registry, but **not** any of the Server Component pages.
