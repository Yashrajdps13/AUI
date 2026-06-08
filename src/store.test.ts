// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest';
import { BridgeStore } from './store.js';
import { ComponentEntry, FiberNode } from './types.js';

// Dummy Fiber Node for testing
const mockFiber: FiberNode = {
  tag: 1,
  type: 'div',
  key: null,
  child: null,
  sibling: null,
  return: null,
  memoizedState: null,
  memoizedProps: {},
  stateNode: null,
};

describe('BridgeStore', () => {
  it('should initially be empty', () => {
    const snapshot = BridgeStore.getSnapshot();
    expect(snapshot.size).toBe(0);
  });

  it('should allow subscribing to updates', () => {
    const listener = vi.fn();
    const unsubscribe = BridgeStore.subscribe(listener);

    const mockEntry: Omit<ComponentEntry, 'id'> = {
      displayName: 'Button',
      fiberRef: mockFiber,
      domRef: null,
      stateSlots: [],
      mountedAt: Date.now(),
      route: '/',
    };

    BridgeStore.registerComponent('button-1', mockEntry);

    expect(listener).toHaveBeenCalledTimes(1);

    unsubscribe();
    BridgeStore.registerComponent('button-2', mockEntry);

    // Listener should not have been called again after unsubscribe
    expect(listener).toHaveBeenCalledTimes(1);

    // Clean up
    BridgeStore.clear();
  });

  it('should update the registry map reference on change to satisfy useSyncExternalStore requirements', () => {
    const mockEntry: Omit<ComponentEntry, 'id'> = {
      displayName: 'Input',
      fiberRef: mockFiber,
      domRef: null,
      stateSlots: [],
      mountedAt: Date.now(),
      route: '/',
    };

    const initialSnapshot = BridgeStore.getSnapshot();

    BridgeStore.registerComponent('input-1', mockEntry);

    const afterRegisterSnapshot = BridgeStore.getSnapshot();
    expect(afterRegisterSnapshot).not.toBe(initialSnapshot); // Reference should change
    expect(afterRegisterSnapshot.size).toBe(1);

    BridgeStore.registerComponent('input-1', {
      ...mockEntry,
      route: '/home', // updated route
    });

    const afterUpdateSnapshot = BridgeStore.getSnapshot();
    expect(afterUpdateSnapshot).not.toBe(afterRegisterSnapshot); // Reference should change on update
    expect(afterUpdateSnapshot.get('input-1')?.route).toBe('/home');

    // Getting the snapshot again without updates should return the exact same reference
    const checkSameRef = BridgeStore.getSnapshot();
    expect(checkSameRef).toBe(afterUpdateSnapshot);

    // Clean up
    BridgeStore.clear();
  });

  it('should handle unregistering components', () => {
    const listener = vi.fn();
    const unsubscribe = BridgeStore.subscribe(listener);

    const mockEntry: Omit<ComponentEntry, 'id'> = {
      displayName: 'Input',
      fiberRef: mockFiber,
      domRef: null,
      stateSlots: [],
      mountedAt: Date.now(),
      route: '/',
    };

    BridgeStore.registerComponent('input-1', mockEntry);
    expect(BridgeStore.getSnapshot().size).toBe(1);

    BridgeStore.unregisterComponent('input-1');
    expect(BridgeStore.getSnapshot().size).toBe(0);
    expect(listener).toHaveBeenCalledTimes(2); // One for register, one for unregister

    // Unregistering non-existing component should not trigger notification
    listener.mockClear();
    BridgeStore.unregisterComponent('input-1');
    expect(listener).not.toHaveBeenCalled();

    unsubscribe();
  });

  it('should support updating state slots and specific state slot values', () => {
    const mockEntry: Omit<ComponentEntry, 'id'> = {
      displayName: 'Counter',
      fiberRef: mockFiber,
      domRef: null,
      stateSlots: [
        { key: 'count', value: 0, setter: () => {}, hookIndex: 0 }
      ],
      mountedAt: Date.now(),
      route: '/',
    };

    BridgeStore.registerComponent('counter-1', mockEntry);

    // Update all slots
    const newSlots = [
      { key: 'count', value: 1, setter: () => {}, hookIndex: 0 },
      { key: 'name', value: 'Test', setter: () => {}, hookIndex: 1 }
    ];
    BridgeStore.updateStateSlots('counter-1', newSlots);
    expect(BridgeStore.getSnapshot().get('counter-1')?.stateSlots).toEqual(newSlots);

    // Update specific slot value
    BridgeStore.updateStateSlotValue('counter-1', 'count', 42);
    expect(BridgeStore.getSnapshot().get('counter-1')?.stateSlots[0].value).toBe(42);
    // Name slot should remain unchanged
    expect(BridgeStore.getSnapshot().get('counter-1')?.stateSlots[1].value).toBe('Test');

    // Clean up
    BridgeStore.clear();
  });

  it('should return a stable empty map for SSR snapshot', () => {
    const ssrSnapshot1 = BridgeStore.getServerSnapshot();
    const ssrSnapshot2 = BridgeStore.getServerSnapshot();
    expect(ssrSnapshot1.size).toBe(0);
    expect(ssrSnapshot1).toBe(ssrSnapshot2); // Reference stability is critical for SSR
  });

  it('should support agent status updates and document body class toggles', () => {
    // Initial status should be 'idle'
    expect(BridgeStore.getAgentStatus()).toBe('idle');
    expect(document.body.className).not.toContain('aui-agent-');

    // Change status to 'working'
    BridgeStore.setAgentStatus('working');
    expect(BridgeStore.getAgentStatus()).toBe('working');
    expect(document.body.classList.contains('aui-agent-working')).toBe(true);
    expect(document.body.classList.contains('aui-agent-succeeded')).toBe(false);

    // Change status to 'succeeded'
    BridgeStore.setAgentStatus('succeeded');
    expect(BridgeStore.getAgentStatus()).toBe('succeeded');
    expect(document.body.classList.contains('aui-agent-succeeded')).toBe(true);
    expect(document.body.classList.contains('aui-agent-working')).toBe(false);

    // Disconnect agent should reset status to 'idle'
    BridgeStore.setAgentConnected(true);
    BridgeStore.setAgentConnected(false);
    expect(BridgeStore.getAgentStatus()).toBe('idle');
    expect(document.body.classList.contains('aui-agent-succeeded')).toBe(false);
  });
});
