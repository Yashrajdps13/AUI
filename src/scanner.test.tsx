// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { useBridgeState } from './hook.js';
import { BridgeStore } from './store.js';

function TestComponent() {
  const [value] = useBridgeState('TestComponent', 'value', 0, 'initial');
  return (
    <div data-testid="container">
      <span data-testid="text">{value}</span>
    </div>
  );
}

describe('Fiber Tree Scanner', () => {
  it('should automatically enrich registered component entry with fiberRef and domRef', () => {
    BridgeStore.clear();

    const { unmount } = render(<TestComponent />);

    const registry = BridgeStore.getSnapshot();
    expect(registry.size).toBe(1);

    const [componentId, entry] = Array.from(registry.entries())[0];
    expect(componentId).toContain('TestComponent#');
    expect(entry.displayName).toBe('TestComponent');

    // The commit phase must have triggered the scanner and enriched the references
    expect(entry.fiberRef).not.toBeNull();
    expect(entry.fiberRef?.type).toBe(TestComponent);

    expect(entry.domRef).not.toBeNull();
    expect(entry.domRef instanceof HTMLElement).toBe(true);
    expect(entry.domRef?.getAttribute('data-testid')).toBe('container');

    unmount();
    expect(BridgeStore.getSnapshot().size).toBe(0);
  });
});
