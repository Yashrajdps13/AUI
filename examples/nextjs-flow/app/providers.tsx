'use client';

import { useEffect } from 'react';
import { AgentWebSocketManager } from 'react-agent-bridge';

/**
 * Providers wraps the app and establishes the agent WebSocket connection.
 *
 * This component MUST be a Client Component ('use client') because
 * AgentWebSocketManager.connect() uses the browser WebSocket API.
 * It is safe to import AgentWebSocketManager in Server Components — the
 * connect() call is a no-op on the server (guarded by typeof window).
 */
export function Providers({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    // Connect to the local agent backend.
    // Change the URL to match your agent server address.
    AgentWebSocketManager.connect('ws://localhost:8000');

    return () => {
      AgentWebSocketManager.disconnect();
    };
  }, []);

  return <>{children}</>;
}
