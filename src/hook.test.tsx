// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import { render, act } from '@testing-library/react';
import { useBridgeState } from './hook.js';
import { BridgeStore } from './store.js';

// Test Component using useBridgeState
function TestCounter() {
  const [count, setCount] = useBridgeState('TestCounter', 'count', 0, 0);
  return (
    <div>
      <span data-testid="count">{count}</span>
      <button data-testid="increment" onClick={() => setCount((prev) => (prev ?? 0) + 1)}>
        Increment
      </button>
    </div>
  );
}

describe('useBridgeState Hook', () => {
  it('should register state slot on mount, update on setter, and unregister on unmount', () => {
    BridgeStore.clear();

    const { getByTestId, unmount } = render(<TestCounter />);

    const registry = BridgeStore.getSnapshot();
    expect(registry.size).toBe(1);

    const [componentId, entry] = Array.from(registry.entries())[0];
    expect(componentId).toContain('TestCounter#');
    expect(entry.displayName).toBe('TestCounter');
    expect(entry.stateSlots.length).toBe(1);
    expect(entry.stateSlots[0].key).toBe('count');
    expect(entry.stateSlots[0].value).toBe(0);
    expect(entry.stateSlots[0].hookIndex).toBe(0);

    // Simulate clicking button (state increment)
    const button = getByTestId('increment');
    act(() => {
      button.click();
    });

    // Registry value must be synchronized
    expect(BridgeStore.getSnapshot().get(componentId)?.stateSlots[0].value).toBe(1);
    expect(getByTestId('count').textContent).toBe('1');

    // Simulate dispatch update directly from the store dispatcher (agent behaviour)
    const dispatcher = BridgeStore.getSnapshot().get(componentId)?.stateSlots[0].setter;
    expect(dispatcher).toBeDefined();

    act(() => {
      dispatcher!(10);
    });

    // Check UI and registry synchrony
    expect(getByTestId('count').textContent).toBe('10');
    expect(BridgeStore.getSnapshot().get(componentId)?.stateSlots[0].value).toBe(10);

    // Unmount component
    unmount();

    // Registry should be cleaned up automatically
    expect(BridgeStore.getSnapshot().size).toBe(0);
  });

  it('should group multiple hooks under the same component ID instance', () => {
    BridgeStore.clear();

    // Secondary test component with multiple useBridgeState hooks
    function TestMultiCounter() {
      const [count1] = useBridgeState('TestMultiCounter', 'count1', 0, 10);
      const [count2] = useBridgeState('TestMultiCounter', 'count2', 1, 20);
      return (
        <div>
          <span data-testid="c1">{count1}</span>
          <span data-testid="c2">{count2}</span>
        </div>
      );
    }

    const { unmount } = render(<TestMultiCounter />);

    const registry = BridgeStore.getSnapshot();
    // Should have only 1 component registered, not 2
    expect(registry.size).toBe(1);

    const [componentId, entry] = Array.from(registry.entries())[0];
    expect(componentId).toContain('TestMultiCounter#');
    expect(entry.displayName).toBe('TestMultiCounter');
    
    // Should contain both slots sorted by hookIndex
    expect(entry.stateSlots.length).toBe(2);
    expect(entry.stateSlots[0].key).toBe('count1');
    expect(entry.stateSlots[0].value).toBe(10);
    expect(entry.stateSlots[1].key).toBe('count2');
    expect(entry.stateSlots[1].value).toBe(20);

    unmount();
    expect(BridgeStore.getSnapshot().size).toBe(0);
  });
});
