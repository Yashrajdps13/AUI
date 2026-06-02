import { create } from 'zustand';
import { bridgeZustand } from 'react-agent-bridge';

export const useUserStore = create((set) => ({
  username: 'Guest',
  token: '',
  count: 0,
  login: (username, token) => {
    console.log(`[Store] Login called with username="${username}"`);
    set({ username, token });
  },
  logout: () => {
    console.log('[Store] Logout called');
    set({ username: 'Guest', token: '' });
  },
  increment: () => {
    console.log('[Store] Increment called');
    set((state) => ({ count: state.count + 1 }));
  },
}));

// Bridge the store to react-agent-bridge
// Sensitive keys like 'token' will be automatically redacted from websocket state syncs
bridgeZustand('UserStore', useUserStore, { sensitiveKeys: ['token'] });
