import { UseBoundStore, StoreApi } from 'zustand';
import { BridgeStore } from './store.js';
import { StateSlot } from './types.js';

export interface BridgeZustandOptions {
  sensitiveKeys?: string[];
}

/**
 * Bridges a Zustand store to react-agent-bridge.
 * Automatically registers its state variables as state slots and its functions as callable actions.
 * Updates are automatically synced via store.subscribe.
 *
 * @param storeName Name of the store (e.g., "Auth" will be registered as "ZustandStore#Auth")
 * @param store The Zustand store hook or vanilla store api
 * @param options Adapter configuration options, including PII sensitive keys
 * @returns Cleanup/unsubscribe function
 */
export function bridgeZustand<T extends object>(
  storeName: string,
  store: UseBoundStore<StoreApi<T>> | StoreApi<T>,
  options?: BridgeZustandOptions
): () => void {
  const storeId = `ZustandStore#${storeName}`;
  const sensitiveKeys = options?.sensitiveKeys || [];

  const api: StoreApi<T> = typeof (store as any).getState === 'function' ? (store as any) : (store as any).getServerState;
  if (!api || typeof api.getState !== 'function' || typeof api.subscribe !== 'function') {
    throw new Error('bridgeZustand requires a valid Zustand store (bound or vanilla).');
  }

  const updateStoreRegistry = () => {
    const state = api.getState();
    const stateSlots: StateSlot[] = [];
    const actions: Record<string, Function> = {};
    let hookIndex = 0;

    for (const [key, value] of Object.entries(state)) {
      if (typeof value === 'function') {
        actions[key] = (...args: any[]) => {
          const latestAction = (api.getState() as any)[key];
          if (typeof latestAction === 'function') {
            return latestAction(...args);
          }
        };
      } else {
        stateSlots.push({
          key,
          value,
          setter: (newValue: any) => {
            api.setState({ [key]: newValue } as any);
          },
          hookIndex: hookIndex++,
          sensitive: sensitiveKeys.includes(key),
        });
      }
    }

    BridgeStore.registerComponent(storeId, {
      displayName: `ZustandStore#${storeName}`,
      fiberRef: null,
      domRef: null,
      stateSlots,
      mountedAt: Date.now(),
      route: typeof window !== 'undefined' ? window.location.pathname : null,
      actions,
    });
  };

  // Run initial registration
  updateStoreRegistry();

  // Subscribe to changes to update state slots dynamically
  const unsubscribe = api.subscribe(() => {
    updateStoreRegistry();
  });

  return () => {
    unsubscribe();
    BridgeStore.unregisterComponent(storeId);
  };
}
