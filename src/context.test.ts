// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { BridgeStore } from './store.js';
import { registerContext, initUrlContext } from './context.js';

describe('Context System', () => {
  beforeEach(() => {
    BridgeStore.clear();
    // Re-initialize URL Context for the test environment
    initUrlContext();
  });

  afterEach(() => {
    BridgeStore.clear();
  });

  it('should automatically register BrowserContext __context__#env and populate location slots', () => {
    const registry = BridgeStore.getSnapshot();
    const env = registry.get('__context__#env');

    expect(env).toBeDefined();
    expect(env?.displayName).toBe('BrowserContext');
    expect(env?.stateSlots.length).toBe(5);

    const pathnameSlot = env?.stateSlots.find(s => s.key === 'pathname');
    const hrefSlot = env?.stateSlots.find(s => s.key === 'href');
    const searchSlot = env?.stateSlots.find(s => s.key === 'search');
    const queryParamsSlot = env?.stateSlots.find(s => s.key === 'queryParams');
    const hashSlot = env?.stateSlots.find(s => s.key === 'hash');

    expect(pathnameSlot?.value).toBe(window.location.pathname);
    expect(hrefSlot?.value).toBe(window.location.href);
    expect(searchSlot?.value).toBe(window.location.search);
    expect(queryParamsSlot?.value).toEqual({});
    expect(hashSlot?.value).toBe(window.location.hash);
  });

  it('should update BrowserContext when location pathname changes via history pushState', () => {
    // Navigate programmatically
    window.history.pushState({}, '', '/new-route?user=alice&id=123#section-3');

    const registry = BridgeStore.getSnapshot();
    const env = registry.get('__context__#env');

    const pathnameSlot = env?.stateSlots.find(s => s.key === 'pathname');
    const hrefSlot = env?.stateSlots.find(s => s.key === 'href');
    const searchSlot = env?.stateSlots.find(s => s.key === 'search');
    const queryParamsSlot = env?.stateSlots.find(s => s.key === 'queryParams');
    const hashSlot = env?.stateSlots.find(s => s.key === 'hash');

    expect(pathnameSlot?.value).toBe('/new-route');
    expect(hrefSlot?.value).toContain('/new-route?user=alice&id=123#section-3');
    expect(searchSlot?.value).toBe('?user=alice&id=123');
    expect(queryParamsSlot?.value).toEqual({ user: 'alice', id: '123' });
    expect(hashSlot?.value).toBe('#section-3');
  });

  it('should register custom contexts under AppContext __context__#custom', () => {
    let dummyValue = 'initial';
    registerContext('myCustomVal', () => dummyValue);
    registerContext('timezone', () => 'UTC', { sensitive: true });

    const registry = BridgeStore.getSnapshot();
    const custom = registry.get('__context__#custom');

    expect(custom).toBeDefined();
    expect(custom?.displayName).toBe('AppContext');
    expect(custom?.stateSlots.length).toBe(2);

    const valSlot = custom?.stateSlots.find(s => s.key === 'myCustomVal');
    const tzSlot = custom?.stateSlots.find(s => s.key === 'timezone');

    expect(valSlot?.value).toBe('initial');
    expect(tzSlot?.value).toBe('UTC');
    expect(tzSlot?.sensitive).toBe(true);
  });

  it('should poll custom contexts and update values on change', async () => {
    vi.useFakeTimers();

    let value = 1;
    registerContext('pollingVal', () => value, { pollIntervalMs: 50 });

    const registry = BridgeStore.getSnapshot();
    const slotBefore = registry.get('__context__#custom')?.stateSlots.find(s => s.key === 'pollingVal');
    expect(slotBefore?.value).toBe(1);

    // Mutate the polled value
    value = 2;

    // Fast-forward timers
    vi.advanceTimersByTime(50);

    const slotAfter = BridgeStore.getSnapshot().get('__context__#custom')?.stateSlots.find(s => s.key === 'pollingVal');
    expect(slotAfter?.value).toBe(2);

    vi.useRealTimers();
  });

  it('should prevent unregistering synthetic context components', () => {
    const registryBefore = BridgeStore.getSnapshot();
    expect(registryBefore.has('__context__#env')).toBe(true);

    // Attempt to unregister
    BridgeStore.unregisterComponent('__context__#env');

    const registryAfter = BridgeStore.getSnapshot();
    expect(registryAfter.has('__context__#env')).toBe(true);
  });
});
