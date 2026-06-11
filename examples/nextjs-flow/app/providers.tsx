'use client';

import { useEffect } from 'react';
import { AgentWebSocketManager, registerContext } from 'react-agent-bridge';

// Register custom AppContext slots
if (typeof window !== 'undefined') {
  registerContext('activeTab', () => {
    return window.location.pathname.substring(1) || 'home';
  });
  registerContext('userTimezone', () => {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  });
  registerContext('featureFlag', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return (window as any).__featureFlags?.newDashboard ?? false;
  });
}

export function Providers({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    AgentWebSocketManager.connect('ws://localhost:8000');

    return () => {
      AgentWebSocketManager.disconnect();
    };
  }, []);

  return <div id="app-root">{children}</div>;
}

