import { describe, it, expect, beforeEach, vi } from 'vitest';
import { bridgeRedux } from './redux.js';
import { BridgeStore } from './store.js';

describe('bridgeRedux', () => {
  let store: any;
  let state: any;
  let listeners: Set<() => void>;

  beforeEach(() => {
    BridgeStore.clear();
    state = {
      counter: { value: 0 },
      user: { name: 'Alice' },
    };
    listeners = new Set();
    store = {
      getState: () => state,
      subscribe: (listener: () => void) => {
        listeners.add(listener);
        return () => {
          listeners.delete(listener);
        };
      },
      dispatch: vi.fn((action: any) => {
        if (action.type === 'counter/increment') {
          state = {
            ...state,
            counter: { value: state.counter.value + 1 },
          };
        } else if (action.type === 'user/setName') {
          state = {
            ...state,
            user: { name: action.payload },
          };
        }
        listeners.forEach((l) => l());
        return action;
      }),
    };
  });

  it('registers store state slices as state slots', () => {
    const metadata = {
      user: { sensitive: true, description: 'User profile slice' },
    };
    const boundStore = bridgeRedux(store, metadata, 'ReduxStore');

    const registry = BridgeStore.getSnapshot();
    const entry = registry.get('ReduxStore#redux');

    expect(entry).toBeDefined();
    expect(entry?.displayName).toBe('ReduxStore');
    expect(entry?.stateSlots).toHaveLength(2); // counter, user

    const counterSlot = entry?.stateSlots.find((s) => s.key === 'counter');
    const userSlot = entry?.stateSlots.find((s) => s.key === 'user');

    expect(counterSlot).toBeDefined();
    expect(counterSlot?.value).toEqual({ value: 0 });
    expect(counterSlot?.sensitive).toBe(false);
    expect(counterSlot?.writeable).toBe('user');

    expect(userSlot).toBeDefined();
    expect(userSlot?.value).toEqual({ name: 'Alice' });
    expect(userSlot?.sensitive).toBe(true);
    expect(userSlot?.description).toBe('User profile slice');
    expect(userSlot?.writeable).toBe('user');

    boundStore.unsubscribeReduxBridge();
  });

  it('syncs state updates from Redux to the registry when actions are dispatched', () => {
    const boundStore = bridgeRedux(store);

    let registry = BridgeStore.getSnapshot();
    let entry = registry.get('ReduxStore#redux');
    expect(entry?.stateSlots.find((s) => s.key === 'counter')?.value).toEqual({ value: 0 });

    // Simulate dispatch
    store.dispatch({ type: 'counter/increment' });

    registry = BridgeStore.getSnapshot();
    entry = registry.get('ReduxStore#redux');
    expect(entry?.stateSlots.find((s) => s.key === 'counter')?.value).toEqual({ value: 1 });

    boundStore.unsubscribeReduxBridge();
  });

  it('blocks direct setState on Redux state slots', () => {
    const boundStore = bridgeRedux(store);

    const registry = BridgeStore.getSnapshot();
    const entry = registry.get('ReduxStore#redux');
    const counterSlot = entry?.stateSlots.find((s) => s.key === 'counter');

    expect(counterSlot?.setter).toBeDefined();
    // Setting state directly should throw
    expect(() => counterSlot?.setter({ value: 99 })).toThrow();

    boundStore.unsubscribeReduxBridge();
  });

  it('exposes the dispatch function for callAction to dispatch to the Redux store', () => {
    const boundStore = bridgeRedux(store);

    const registry = BridgeStore.getSnapshot();
    const entry = registry.get('ReduxStore#redux');

    expect(entry?.actions).toBeDefined();
    expect(typeof entry?.actions?.dispatch).toBe('function');

    entry?.actions?.dispatch({ type: 'user/setName', payload: 'Bob' });

    expect(store.dispatch).toHaveBeenCalledWith({ type: 'user/setName', payload: 'Bob' });
    expect(store.getState().user.name).toBe('Bob');

    boundStore.unsubscribeReduxBridge();
  });
});
