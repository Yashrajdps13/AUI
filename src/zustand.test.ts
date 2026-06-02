import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createStore } from 'zustand/vanilla';
import { bridgeZustand } from './zustand.js';
import { BridgeStore } from './store.js';

interface TestState {
  count: number;
  username: string;
  token: string;
  increment: () => void;
  setUsername: (name: string) => void;
  setToken: (token: string) => void;
  asyncAction: () => Promise<string>;
}

describe('bridgeZustand', () => {
  let store: any;

  beforeEach(() => {
    BridgeStore.clear();

    store = createStore<TestState>((set) => ({
      count: 0,
      username: 'Alice',
      token: 'secret-token-123',
      increment: () => set((state) => ({ count: state.count + 1 })),
      setUsername: (name: string) => set({ username: name }),
      setToken: (token: string) => set({ token }),
      asyncAction: async () => {
        return new Promise<string>((resolve) => {
          setTimeout(() => resolve('done'), 10);
        });
      },
    }));
  });

  it('registers store state properties as state slots and actions as callable actions', () => {
    const cleanup = bridgeZustand('Auth', store, { sensitiveKeys: ['token'] });

    const registry = BridgeStore.getSnapshot();
    const entry = registry.get('ZustandStore#Auth');

    expect(entry).toBeDefined();
    expect(entry?.displayName).toBe('ZustandStore#Auth');
    expect(entry?.fiberRef).toBeNull();
    expect(entry?.domRef).toBeNull();

    // Check state slots
    expect(entry?.stateSlots).toHaveLength(3); // count, username, token
    const countSlot = entry?.stateSlots.find((s) => s.key === 'count');
    const usernameSlot = entry?.stateSlots.find((s) => s.key === 'username');
    const tokenSlot = entry?.stateSlots.find((s) => s.key === 'token');

    expect(countSlot).toBeDefined();
    expect(countSlot?.value).toBe(0);
    expect(countSlot?.sensitive).toBeFalsy();

    expect(usernameSlot).toBeDefined();
    expect(usernameSlot?.value).toBe('Alice');
    expect(usernameSlot?.sensitive).toBeFalsy();

    expect(tokenSlot).toBeDefined();
    expect(tokenSlot?.value).toBe('secret-token-123');
    expect(tokenSlot?.sensitive).toBe(true);

    // Check actions mapping
    expect(entry?.actions).toBeDefined();
    expect(typeof entry?.actions?.increment).toBe('function');
    expect(typeof entry?.actions?.setUsername).toBe('function');
    expect(typeof entry?.actions?.setToken).toBe('function');
    expect(typeof entry?.actions?.asyncAction).toBe('function');

    cleanup();
  });

  it('syncs state updates from Zustand to the BridgeStore registry', () => {
    const cleanup = bridgeZustand('Auth', store);

    // Initial check
    let registry = BridgeStore.getSnapshot();
    let entry = registry.get('ZustandStore#Auth');
    expect(entry?.stateSlots.find((s) => s.key === 'count')?.value).toBe(0);

    // Trigger state change via Zustand action
    store.getState().increment();

    registry = BridgeStore.getSnapshot();
    entry = registry.get('ZustandStore#Auth');
    expect(entry?.stateSlots.find((s) => s.key === 'count')?.value).toBe(1);

    cleanup();
  });

  it('allows state modifications from BridgeStore to update the Zustand store via slot setters', () => {
    const cleanup = bridgeZustand('Auth', store);

    const registry = BridgeStore.getSnapshot();
    const entry = registry.get('ZustandStore#Auth');
    const usernameSlot = entry?.stateSlots.find((s) => s.key === 'username');

    expect(usernameSlot?.setter).toBeDefined();
    usernameSlot?.setter('Bob');

    // Zustand store state should be updated
    expect(store.getState().username).toBe('Bob');

    // BridgeStore registry should also sync
    const updatedRegistry = BridgeStore.getSnapshot();
    const updatedEntry = updatedRegistry.get('ZustandStore#Auth');
    expect(updatedEntry?.stateSlots.find((s) => s.key === 'username')?.value).toBe('Bob');

    cleanup();
  });

  it('correctly executes actions and async actions registered in the bridge', async () => {
    const cleanup = bridgeZustand('Auth', store);

    const registry = BridgeStore.getSnapshot();
    const entry = registry.get('ZustandStore#Auth');

    // Synchronous action
    entry?.actions?.setUsername('Charlie');
    expect(store.getState().username).toBe('Charlie');

    // Async action
    const promise = entry?.actions?.asyncAction();
    expect(promise).toBeInstanceOf(Promise);
    const result = await promise;
    expect(result).toBe('done');

    cleanup();
  });

  it('unregisters the store from BridgeStore upon cleanup', () => {
    const cleanup = bridgeZustand('Auth', store);

    expect(BridgeStore.getSnapshot().has('ZustandStore#Auth')).toBe(true);

    cleanup();

    expect(BridgeStore.getSnapshot().has('ZustandStore#Auth')).toBe(false);
  });

  it('supports custom actions mapping and action exclusion via options', () => {
    const customActionSpy = vi.fn();
    const cleanup = bridgeZustand('Auth', store, {
      actions: {
        customAction: customActionSpy,
      },
      excludeActions: ['increment', 'setUsername'],
    });

    const registry = BridgeStore.getSnapshot();
    const entry = registry.get('ZustandStore#Auth');

    expect(entry).toBeDefined();
    // increment and setUsername should be excluded
    expect(entry?.actions?.increment).toBeUndefined();
    expect(entry?.actions?.setUsername).toBeUndefined();

    // setToken and asyncAction should still be included
    expect(entry?.actions?.setToken).toBeDefined();
    expect(entry?.actions?.asyncAction).toBeDefined();

    // customAction should be included and callable
    expect(entry?.actions?.customAction).toBeDefined();
    entry?.actions?.customAction('hello');
    expect(customActionSpy).toHaveBeenCalledWith('hello');

    cleanup();
  });
});
