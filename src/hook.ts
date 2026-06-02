import { useState, useEffect, useLayoutEffect, useId, useRef } from 'react';
import { BridgeStore } from './store.js';
import { StateSlot } from './types.js';

// Safe SSR checks to select useLayoutEffect or useEffect
const useIsomorphicLayoutEffect = typeof window !== 'undefined' ? useLayoutEffect : useEffect;

// Keep track of the active instance ID for each component name during the synchronous render pass
const activeInstanceIds = new Map<string, string>();

/**
 * Interceptor hook replacing React's default `useState`.
 * Automatically registers the state slot in the Bridge registry,
 * preserves name/meta, and intercepts state updates.
 */
export function useBridgeState<S>(
  componentName: string,
  stateKey: string,
  hookIndex: number,
  initialState: S | (() => S)
): [S, React.Dispatch<React.SetStateAction<S>>];
export function useBridgeState<S = undefined>(
  componentName: string,
  stateKey: string,
  hookIndex: number,
  initialState?: S | (() => S)
): [S | undefined, React.Dispatch<React.SetStateAction<S | undefined>>];
export function useBridgeState<S>(
  componentName: string,
  stateKey: string,
  hookIndex: number,
  initialState?: S | (() => S)
) {
  const [state, setState] = useState<S | undefined>(initialState);

  // Generate or retrieve a stable, unique runtime ID for this component instance.
  // We unconditionally call useId to satisfy React's rule of hooks, but we only store/use the
  // ID from hookIndex === 0 for all hooks within the same component instance.
  const backupId = useId();
  let instanceId: string;
  if (hookIndex === 0) {
    instanceId = backupId;
    activeInstanceIds.set(componentName, backupId);
  } else {
    instanceId = activeInstanceIds.get(componentName) || backupId;
  }
  const componentId = `${componentName}#${instanceId}`;

  // Use refs to keep references stable across renders to prevent unnecessary effect execution
  const latestValueRef = useRef<S | undefined>(state);
  latestValueRef.current = state;

  const latestSetterRef = useRef<React.Dispatch<React.SetStateAction<S | undefined>>>(setState);
  latestSetterRef.current = setState;

  // Intercept the setter reference. The returned reference remains stable.
  const bridgeSetter = useRef<React.Dispatch<React.SetStateAction<S | undefined>>>((valueOrFunc) => {
    // Execute the actual React state update
    latestSetterRef.current(valueOrFunc);
  });

  // Handle slot registration and cleanup lifecycle
  useIsomorphicLayoutEffect(() => {
    const slot: StateSlot = {
      key: stateKey,
      value: latestValueRef.current,
      setter: bridgeSetter.current,
      hookIndex,
    };

    BridgeStore.registerStateSlot(componentId, componentName, slot);

    return () => {
      BridgeStore.unregisterStateSlot(componentId, hookIndex);
    };
  }, [componentId, componentName, stateKey, hookIndex]);

  // Keep the registry value in sync synchronously on state changes
  useIsomorphicLayoutEffect(() => {
    BridgeStore.updateStateSlotValue(componentId, stateKey, state);
  }, [componentId, stateKey, state]);

  return [state, bridgeSetter.current];
}
