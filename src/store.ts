import { useSyncExternalStore } from 'react';
import { ComponentEntry, BridgeRegistry, StateSlot } from './types.js';

const EMPTY_REGISTRY: BridgeRegistry = new Map();

class BridgeStoreImpl {
  private registry: BridgeRegistry = new Map();
  private listeners: Set<() => void> = new Set();
  private refCounts: Map<string, Set<number>> = new Map();
  private agentConnected: boolean = false;

  /**
   * Returns true if the agent is currently connected via websocket.
   */
  isAgentConnected = (): boolean => {
    return this.agentConnected;
  };

  /**
   * Sets the agent connection status and notifies subscribers.
   */
  setAgentConnected(connected: boolean): void {
    if (this.agentConnected === connected) return;
    this.agentConnected = connected;
    this.notify();
  }

  /**
   * Subscribes to store updates.
   * React calls this on mount and subscribes to state changes.
   * Returns an unsubscribe/cleanup function.
   */
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  /**
   * Returns the current snapshot of the registry.
   * Note: We treat the Map as immutable and replace it on every update
   * to guarantee that useSyncExternalStore detects state modifications.
   */
  getSnapshot = (): BridgeRegistry => {
    return this.registry;
  };

  /**
   * Returns a snapshot of the registry for Server-Side Rendering (SSR).
   * Since there is no live DOM/client Fiber tree during SSR, it returns
   * a reference-stable empty registry map.
   */
  getServerSnapshot = (): BridgeRegistry => {
    return EMPTY_REGISTRY;
  };

  /**
   * Notifies all registered listeners of an update.
   */
  private notify(): void {
    for (const listener of this.listeners) {
      listener();
    }
  }

  /**
   * Registers a single state slot dynamically under a component ID.
   * Uses reference counting of active hooks to track active slots per component.
   */
  registerStateSlot(id: string, displayName: string, slot: StateSlot): void {
    const existing = this.registry.get(id);
    const nextRegistry = new Map(this.registry);

    if (existing) {
      const updatedSlots = [...existing.stateSlots];
      const slotIndex = updatedSlots.findIndex((s) => s.hookIndex === slot.hookIndex);
      if (slotIndex !== -1) {
        updatedSlots[slotIndex] = slot;
      } else {
        updatedSlots.push(slot);
        updatedSlots.sort((a, b) => a.hookIndex - b.hookIndex);
      }
      nextRegistry.set(id, {
        ...existing,
        stateSlots: updatedSlots,
      });
    } else {
      nextRegistry.set(id, {
        id,
        displayName,
        fiberRef: null,
        domRef: null,
        stateSlots: [slot],
        mountedAt: Date.now(),
        route: typeof window !== 'undefined' ? window.location.pathname : null,
      });
    }
    this.registry = nextRegistry;

    // Track active hookIndex for this component
    let activeHooks = this.refCounts.get(id);
    if (!activeHooks) {
      activeHooks = new Set();
      this.refCounts.set(id, activeHooks);
    }
    activeHooks.add(slot.hookIndex);

    this.notify();
  }

  /**
   * Unregisters a single state slot. If no more active slots are registered for the
   * component ID, the component entry itself is removed from the registry.
   */
  unregisterStateSlot(id: string, hookIndex: number): void {
    const activeHooks = this.refCounts.get(id);
    if (!activeHooks) return;

    activeHooks.delete(hookIndex);

    if (activeHooks.size === 0) {
      this.refCounts.delete(id);
      const nextRegistry = new Map(this.registry);
      nextRegistry.delete(id);
      this.registry = nextRegistry;
    } else {
      const existing = this.registry.get(id);
      if (existing) {
        const nextRegistry = new Map(this.registry);
        nextRegistry.set(id, {
          ...existing,
          stateSlots: existing.stateSlots.filter((s) => s.hookIndex !== hookIndex),
        });
        this.registry = nextRegistry;
      }
    }
    this.notify();
  }

  /**
   * Registers a new component or completely updates an existing one.
   */
  registerComponent(id: string, entry: Omit<ComponentEntry, 'id'>): void {
    const nextRegistry = new Map(this.registry);
    nextRegistry.set(id, {
      ...entry,
      id,
    });
    this.registry = nextRegistry;
    this.notify();
  }

  /**
   * Removes a component entry by ID.
   */
  unregisterComponent(id: string): void {
    if (!this.registry.has(id)) return;
    const nextRegistry = new Map(this.registry);
    nextRegistry.delete(id);
    this.registry = nextRegistry;
    this.notify();
  }

  /**
   * Updates all state slots for a specific component entry.
   */
  updateStateSlots(id: string, slots: StateSlot[]): void {
    const component = this.registry.get(id);
    if (!component) return;

    const nextRegistry = new Map(this.registry);
    nextRegistry.set(id, {
      ...component,
      stateSlots: [...slots],
    });
    this.registry = nextRegistry;
    this.notify();
  }

  /**
   * Updates the value of a specific state slot within a registered component.
   */
  updateStateSlotValue(id: string, key: string, value: unknown): void {
    const component = this.registry.get(id);
    if (!component) return;

    const slotIndex = component.stateSlots.findIndex((s) => s.key === key);
    if (slotIndex === -1) return;

    const updatedSlots = [...component.stateSlots];
    updatedSlots[slotIndex] = {
      ...updatedSlots[slotIndex],
      value,
    };

    const nextRegistry = new Map(this.registry);
    nextRegistry.set(id, {
      ...component,
      stateSlots: updatedSlots,
    });
    this.registry = nextRegistry;
    this.notify();
  }

  /**
   * Updates a component's live Fiber reference, DOM reference, and path/route details.
   * Performs comparison checks to prevent redundant rendering updates.
   */
  updateFiberAndDomRef(
    id: string,
    fiberRef: any,
    domRef: HTMLElement | null,
    route: string | null
  ): void {
    const component = this.registry.get(id);
    if (!component) return;

    if (
      component.fiberRef === fiberRef &&
      component.domRef === domRef &&
      component.route === route
    ) {
      return;
    }

    const nextRegistry = new Map(this.registry);
    nextRegistry.set(id, {
      ...component,
      fiberRef,
      domRef,
      route,
    });
    this.registry = nextRegistry;
    this.notify();
  }

  /**
   * Cleans the registry store completely.
   */
  clear(): void {
    if (this.registry.size === 0 && this.refCounts.size === 0) return;
    this.registry = new Map();
    this.refCounts.clear();
    this.notify();
  }
}

// Export the singleton store instance
export const BridgeStore = new BridgeStoreImpl();

/**
 * React hook to retrieve and subscribe to the live Bridge registry.
 * This hook is safe to use in Concurrent Mode and SSR environments.
 */
export function useBridgeRegistry(): BridgeRegistry {
  return useSyncExternalStore(
    BridgeStore.subscribe,
    BridgeStore.getSnapshot,
    BridgeStore.getServerSnapshot
  );
}

/**
 * React hook to check if an agent is currently connected.
 * Safe to use in Concurrent Mode and SSR environments.
 */
export function useIsAgentConnected(): boolean {
  return useSyncExternalStore(
    BridgeStore.subscribe,
    BridgeStore.isAgentConnected,
    () => false
  );
}

