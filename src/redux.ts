import { BridgeStore } from './store.js';
import { StateSlot } from './types.js';

export interface BridgeReduxMetadata {
  sensitive?: boolean;
  description?: string;
}

/**
 * Bridges a Redux Toolkit store to react-agent-bridge.
 * Automatically registers its top-level state slices as state slots and exposes its dispatch function.
 * Updates are automatically synced via store.subscribe.
 *
 * @param store The Redux store instance
 * @param metadata Runtime metadata containing descriptions and sensitivity flags for state slices
 * @param storeName Name of the store (defaults to "ReduxStore")
 * @returns The Redux store instance with an attached unsubscribeReduxBridge method
 */
export function bridgeRedux(
  store: any,
  metadata?: Record<string, BridgeReduxMetadata>,
  storeName: string = 'ReduxStore'
): any {
  if (!store || typeof store.getState !== 'function' || typeof store.subscribe !== 'function' || typeof store.dispatch !== 'function') {
    throw new Error('bridgeRedux requires a valid Redux store.');
  }

  const storeId = `${storeName}#redux`;

  const updateStoreRegistry = () => {
    const state = store.getState();
    const stateSlots: StateSlot[] = [];
    let hookIndex = 0;

    for (const [key, value] of Object.entries(state)) {
      const meta = metadata?.[key];
      stateSlots.push({
        key,
        value,
        setter: () => {
          throw new Error(`Direct setState mutation of Redux state slot '${key}' is prohibited. Use callAction to dispatch Redux actions.`);
        },
        hookIndex: hookIndex++,
        description: meta?.description,
        sensitive: !!meta?.sensitive,
        writeable: 'user', // Enforces that the agent cannot mutate this state slot directly
      });
    }

    const actions: Record<string, Function> = {
      dispatch: (action: any, payload?: any) => {
        if (typeof action === 'string') {
          return store.dispatch({ type: action, payload });
        }
        return store.dispatch(action);
      },
    };

    BridgeStore.registerComponent(storeId, {
      displayName: storeName,
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
  const unsubscribe = store.subscribe(() => {
    updateStoreRegistry();
  });

  // Attach unsubscribe method to the store object for easy cleanup
  (store as any).unsubscribeReduxBridge = () => {
    unsubscribe();
    BridgeStore.unregisterComponent(storeId);
  };

  return store;
}
