import { startTransition } from 'react';
import { BridgeStore } from './store.js';
import { AgentCommand, BridgeMessage, SerializedComponentEntry } from './protocol.js';

class AgentWebSocketManagerImpl {
  private ws: any = null;
  private url: string | null = null;
  private reconnectTimer: any = null;
  private reconnectDelay = 1000;
  private maxReconnectDelay = 30000;
  private isDisconnecting = false;

  // Active subscriptions (component IDs the agent wants live values for)
  private subscribedComponents: Set<string> = new Set();

  // Store subscription cleanup callback
  private unsubscribeStore: (() => void) | null = null;

  // Cache to store the last sent state of components and values to compute deltas
  private lastSentRegistry: Map<string, string> = new Map(); // id -> JSON-serialized component
  private lastSentValues: Map<string, string> = new Map(); // "componentId.stateKey" -> JSON-serialized value

  // Allow overriding WebSocket class (for Node.js testing environments)
  public WebSocketClass: any = typeof WebSocket !== 'undefined' ? WebSocket : null;

  /**
   * Connects to the agent backend WebSocket.
   */
  connect(url: string): void {
    this.url = url;
    this.isDisconnecting = false;

    const WS = this.WebSocketClass || (typeof globalThis !== 'undefined' ? (globalThis as any).WebSocket : null);
    if (!WS) {
      console.warn('WebSocket constructor not found. Postponing connection until runtime.');
      return;
    }

    try {
      this.ws = new WS(url);
    } catch (err) {
      console.error('Failed to instantiate WebSocket:', err);
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.reconnectDelay = 1000; // Reset backoff
      this.onConnected();
    };

    this.ws.onclose = () => {
      this.onDisconnected();
    };

    this.ws.onerror = (err: any) => {
      console.error('Bridge WebSocket error:', err);
    };

    this.ws.onmessage = (event: any) => {
      try {
        const command: AgentCommand = JSON.parse(event.data);
        this.handleCommand(command);
      } catch (err) {
        console.error('Failed to parse Agent command:', err);
      }
    };
  }

  /**
   * Closes the active connection and prevents auto-reconnection.
   */
  disconnect(): void {
    this.isDisconnecting = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.unsubscribeStore) {
      this.unsubscribeStore();
      this.unsubscribeStore = null;
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    this.subscribedComponents.clear();
    this.lastSentRegistry.clear();
    this.lastSentValues.clear();
  }

  /**
   * Sends a message to the agent if the connection is open.
   */
  send(message: BridgeMessage): void {
    if (this.ws && this.ws.readyState === 1) { // WebSocket.OPEN is 1
      try {
        this.ws.send(JSON.stringify(message));
      } catch (err) {
        console.error('Failed to send Bridge message:', err);
      }
    }
  }

  private onConnected(): void {
    // Sync the registry updates
    this.unsubscribeStore = BridgeStore.subscribe(() => {
      this.syncRegistryAndSubscriptions();
    });

    // Send initial full registry state
    this.syncRegistryAndSubscriptions(true);
  }

  private onDisconnected(): void {
    if (this.unsubscribeStore) {
      this.unsubscribeStore();
      this.unsubscribeStore = null;
    }

    this.ws = null;

    if (!this.isDisconnecting) {
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
      if (this.url) {
        this.connect(this.url);
      }
    }, this.reconnectDelay);
  }

  /**
   * Scans current store registry, diffs against cache, and publishes registryDelta and stateSnapshots.
   */
  private syncRegistryAndSubscriptions(forceFull = false): void {
    const currentRegistry = BridgeStore.getSnapshot();
    const added: SerializedComponentEntry[] = [];
    const updated: SerializedComponentEntry[] = [];
    const removed: string[] = [];

    const nextRegistryCache = new Map<string, string>();

    // 1. Diffs Added and Updated components
    for (const [id, entry] of currentRegistry.entries()) {
      const serialized: SerializedComponentEntry = {
        id: entry.id,
        displayName: entry.displayName,
        mountedAt: entry.mountedAt,
        route: entry.route,
        stateSlots: entry.stateSlots.map((s) => ({
          key: s.key,
          hookIndex: s.hookIndex,
        })),
      };

      const serializedStr = JSON.stringify(serialized);
      nextRegistryCache.set(id, serializedStr);

      const previousStr = this.lastSentRegistry.get(id);

      if (forceFull || !previousStr) {
        added.push(serialized);
      } else if (previousStr !== serializedStr) {
        updated.push(serialized);
      }
    }

    // 2. Diffs Removed components
    for (const id of this.lastSentRegistry.keys()) {
      if (!currentRegistry.has(id)) {
        removed.push(id);
      }
    }

    // Send registry delta message if changes exist
    if (added.length > 0 || updated.length > 0 || removed.length > 0) {
      this.send({
        type: 'registryDelta',
        added,
        updated,
        removed,
      });

      this.lastSentRegistry = nextRegistryCache;
    }

    // 3. Sync live values for subscribed components
    for (const componentId of this.subscribedComponents) {
      const entry = currentRegistry.get(componentId);
      if (!entry) continue;

      for (const slot of entry.stateSlots) {
        const target = `${componentId}.${slot.key}`;
        const valStr = JSON.stringify(slot.value);
        const prevValStr = this.lastSentValues.get(target);

        if (forceFull || prevValStr !== valStr) {
          this.send({
            type: 'stateSnapshot',
            target,
            value: slot.value,
          });
          this.lastSentValues.set(target, valStr);
        }
      }
    }
  }

  /**
   * Dispatches inbound agent commands.
   */
  private handleCommand(command: AgentCommand): void {
    const registry = BridgeStore.getSnapshot();

    switch (command.type) {
      case 'getRegistry': {
        this.syncRegistryAndSubscriptions(true);
        this.send({ type: 'commandAck', commandId: command.commandId, success: true });
        break;
      }

      case 'subscribe': {
        this.subscribedComponents.add(command.target);
        this.send({ type: 'commandAck', commandId: command.commandId, success: true });
        
        // Immediately send current values for the newly subscribed component
        const entry = registry.get(command.target);
        if (entry) {
          for (const slot of entry.stateSlots) {
            const target = `${command.target}.${slot.key}`;
            this.send({ type: 'stateSnapshot', target, value: slot.value });
            this.lastSentValues.set(target, JSON.stringify(slot.value));
          }
        }
        break;
      }

      case 'unsubscribe': {
        this.subscribedComponents.delete(command.target);
        this.send({ type: 'commandAck', commandId: command.commandId, success: true });
        
        // Clear cached values for the component to prevent leak
        const entry = registry.get(command.target);
        if (entry) {
          for (const slot of entry.stateSlots) {
            this.lastSentValues.delete(`${command.target}.${slot.key}`);
          }
        }
        break;
      }

      case 'queryState': {
        const lastDot = command.target.lastIndexOf('.');
        if (lastDot === -1) {
          this.send({
            type: 'commandAck',
            commandId: command.commandId,
            success: false,
            error: 'Invalid target path format. Expected "componentId.stateKey".',
          });
          return;
        }

        const componentId = command.target.substring(0, lastDot);
        const stateKey = command.target.substring(lastDot + 1);

        const entry = registry.get(componentId);
        const slot = entry?.stateSlots.find((s) => s.key === stateKey);

        if (slot) {
          this.send({ type: 'stateSnapshot', target: command.target, value: slot.value });
          this.send({ type: 'commandAck', commandId: command.commandId, success: true });
        } else {
          this.send({
            type: 'commandAck',
            commandId: command.commandId,
            success: false,
            error: `Target state "${stateKey}" not found in component "${componentId}".`,
          });
        }
        break;
      }

      case 'setState': {
        const lastDot = command.target.lastIndexOf('.');
        if (lastDot === -1) {
          this.send({
            type: 'commandAck',
            commandId: command.commandId,
            success: false,
            error: 'Invalid target path format. Expected "componentId.stateKey".',
          });
          return;
        }

        const componentId = command.target.substring(0, lastDot);
        const stateKey = command.target.substring(lastDot + 1);

        const entry = registry.get(componentId);
        const slot = entry?.stateSlots.find((s) => s.key === stateKey);

        if (slot) {
          try {
            startTransition(() => {
              slot.setter(command.value);
            });
            this.send({ type: 'commandAck', commandId: command.commandId, success: true });
          } catch (err: any) {
            this.send({
              type: 'commandAck',
              commandId: command.commandId,
              success: false,
              error: `State setter failed: ${err.message || err}`,
            });
          }
        } else {
          this.send({
            type: 'commandAck',
            commandId: command.commandId,
            success: false,
            error: `Target state "${stateKey}" not found in component "${componentId}".`,
          });
        }
        break;
      }

      case 'dispatchEvent': {
        const entry = registry.get(command.target);
        if (!entry || !entry.domRef) {
          this.send({
            type: 'commandAck',
            commandId: command.commandId,
            success: false,
            error: `Component DOM reference for "${command.target}" not found.`,
          });
          return;
        }

        try {
          const dom = entry.domRef;
          if (command.event === 'click') {
            let targetDom = dom;
            if (command.payload && typeof command.payload === 'string') {
              const selected = dom.querySelector(command.payload);
              if (selected instanceof HTMLElement) targetDom = selected;
            }
            targetDom.click();
          } else if (command.event === 'focus') {
            let targetDom = dom;
            if (command.payload && typeof command.payload === 'string') {
              const selected = dom.querySelector(command.payload);
              if (selected instanceof HTMLElement) targetDom = selected;
            }
            targetDom.focus();
          } else if (command.event === 'change') {
            // Check if payload is provided to set input value
            if (command.payload !== undefined && 'value' in dom) {
              (dom as any).value = command.payload;
            }
            const ev = new Event('change', { bubbles: true });
            dom.dispatchEvent(ev);
          } else {
            throw new Error(`Unsupported event type "${command.event}"`);
          }

          this.send({ type: 'commandAck', commandId: command.commandId, success: true });
        } catch (err: any) {
          this.send({
            type: 'commandAck',
            commandId: command.commandId,
            success: false,
            error: `Failed to dispatch event: ${err.message || err}`,
          });
        }
        break;
      }

      default: {
        this.send({
          type: 'commandAck',
          commandId: (command as any).commandId || '',
          success: false,
          error: `Unknown command type: ${(command as any).type}`,
        });
      }
    }
  }
}

export const AgentWebSocketManager = new AgentWebSocketManagerImpl();
