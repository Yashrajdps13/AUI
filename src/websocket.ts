import { startTransition } from 'react';
import { BridgeStore } from './store.js';
import { AgentCommand, BridgeMessage, SerializedComponentEntry } from './protocol.js';
import { AgentLogger } from './logger.js';

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

  /**
   * Called by the scanner when React commits a render and scan is complete.
   */
  onRenderSettled(targetId: string): void {
    this.send({
      type: 'renderSettled',
      target: targetId,
    });
  }

  private onConnected(): void {
    BridgeStore.setAgentConnected(true);
    if (typeof document !== 'undefined') {
      document.body.classList.add('aui-agent-mode');
    }

    // Connect the agent logger listener to stream errors
    AgentLogger.setListener((entry) => {
      this.send({
        type: 'appLog',
        entry,
      });
    });

    // Sync the registry updates
    this.unsubscribeStore = BridgeStore.subscribe(() => {
      this.syncRegistryAndSubscriptions();
    });

    // Send initial full registry state
    this.syncRegistryAndSubscriptions(true);
  }

  private onDisconnected(): void {
    BridgeStore.setAgentConnected(false);
    if (typeof document !== 'undefined') {
      document.body.classList.remove('aui-agent-mode');
    }

    // Detach the agent logger listener
    AgentLogger.setListener(null);

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
   * Helper to scan all interactive elements (buttons, links, inputs, elements with action IDs)
   * under a DOM reference to expose to the agent planner.
   */
  private getInteractiveElements(dom: HTMLElement | null): {
    selector: string;
    tagName: string;
    text?: string;
    id?: string;
    placeholder?: string;
    disabled?: boolean;
    visible?: boolean;
  }[] {
    if (!dom || typeof window === 'undefined') return [];
    const list: any[] = [];
    try {
      const elements = dom.querySelectorAll('button, a, input, select, textarea, [id], [role="button"]');
      const allElements = [dom, ...Array.from(elements)];
      const seenSelectors = new Set<string>();

      const isElementVisible = (element: HTMLElement): boolean => {
        if (!element.ownerDocument || !element.ownerDocument.defaultView) return true;
        try {
          const style = element.ownerDocument.defaultView.getComputedStyle(element);
          if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
            return false;
          }
          let parent: HTMLElement | null = element.parentElement;
          while (parent && parent !== dom) {
            const parentStyle = element.ownerDocument.defaultView.getComputedStyle(parent);
            if (parentStyle.display === 'none' || parentStyle.visibility === 'hidden') {
              return false;
            }
            parent = parent.parentElement;
          }
        } catch {
          // Computed styles lookup might fail in environments without defaultView
        }
        return true;
      };

      for (const el of allElements) {
        if (!(el instanceof HTMLElement)) continue;

        const isInteractive =
          el.tagName === 'BUTTON' ||
          el.tagName === 'A' ||
          el.tagName === 'INPUT' ||
          el.tagName === 'SELECT' ||
          el.tagName === 'TEXTAREA' ||
          el.getAttribute('role') === 'button' ||
          (el.id && (el.id.startsWith('btn-') || el.id.startsWith('input-')));

        if (!isInteractive) continue;

        let selector = '';
        if (el.id) {
          selector = `#${el.id}`;
        } else {
          selector = el.tagName.toLowerCase();
          if (el.className) {
            const classes = String(el.className).split(/\s+/).filter(Boolean).map(c => `.${c}`).join('');
            selector += classes;
          }
        }

        if (seenSelectors.has(selector)) continue;
        seenSelectors.add(selector);

        const text = el.innerText ? el.innerText.trim().substring(0, 100) : '';
        const placeholder = el.getAttribute('placeholder') || undefined;
        const disabled = (el as any).disabled === true || el.getAttribute('aria-disabled') === 'true' || el.hasAttribute('disabled');
        const visible = isElementVisible(el);

        list.push({
          selector,
          tagName: el.tagName,
          text: text || undefined,
          id: el.id || undefined,
          placeholder: placeholder || undefined,
          disabled: disabled || undefined,
          visible,
        });
      }
    } catch (err) {
      console.error('Error scanning interactive elements:', err);
    }
    return list;
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
          description: s.description,
          sensitive: s.sensitive,
        })),
        interactiveElements: this.getInteractiveElements(entry.domRef),
        actions: entry.actions ? Object.keys(entry.actions) : undefined,
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
        const valueToSend = slot.sensitive ? '[REDACTED]' : slot.value;
        const valStr = JSON.stringify(valueToSend);
        const prevValStr = this.lastSentValues.get(target);

        if (forceFull || prevValStr !== valStr) {
          this.send({
            type: 'stateSnapshot',
            target,
            value: valueToSend,
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
      case 'queryLedger': {
        this.send({
          type: 'ledgerSnapshot',
          commandId: command.commandId,
          ledger: AgentLogger.getLedger(),
        });
        this.send({ type: 'commandAck', commandId: command.commandId, success: true });
        break;
      }

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
            const valueToSend = slot.sensitive ? '[REDACTED]' : slot.value;
            this.send({ type: 'stateSnapshot', target, value: valueToSend });
            this.lastSentValues.set(target, JSON.stringify(valueToSend));
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
          const valueToSend = slot.sensitive ? '[REDACTED]' : slot.value;
          this.send({ type: 'stateSnapshot', target: command.target, value: valueToSend });
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

        const isSensitive = slot?.sensitive === true;
        const loggedValue = isSensitive ? '[REDACTED]' : command.value;

        AgentLogger.addEntry({
          type: 'info',
          source: 'agent',
          message: `setState -> ${command.target} (value: ${typeof loggedValue === 'object' ? JSON.stringify(loggedValue) : String(loggedValue)})`,
          timestamp: Date.now(),
        });

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
        AgentLogger.addEntry({
          type: 'info',
          source: 'agent',
          message: `dispatchEvent -> ${command.event} on ${command.target} (payload: ${typeof command.payload === 'object' ? JSON.stringify(command.payload) : String(command.payload)})`,
          timestamp: Date.now(),
        });

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
            let targetDom = dom;
            let valueToSet = command.payload;

            if (command.payload && typeof command.payload === 'object') {
              const payloadObj = command.payload as any;
              if (typeof payloadObj.selector === 'string') {
                const selected = dom.querySelector(payloadObj.selector);
                if (selected instanceof HTMLElement) targetDom = selected;
              }
              if ('value' in payloadObj) {
                valueToSet = payloadObj.value;
              }
            }

            if (targetDom instanceof HTMLInputElement && targetDom.type === 'checkbox') {
              const currentChecked = targetDom.checked;
              const desiredChecked = Boolean(valueToSet);
              if (currentChecked !== desiredChecked) {
                targetDom.click();
              }
            } else {
              if ('value' in targetDom) {
                const valueSetter = Object.getOwnPropertyDescriptor(targetDom, 'value')?.set;
                const prototype = Object.getPrototypeOf(targetDom);
                const prototypeValueSetter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;

                if (prototypeValueSetter && valueSetter !== prototypeValueSetter) {
                  prototypeValueSetter.call(targetDom, valueToSet);
                } else if (valueSetter) {
                  valueSetter.call(targetDom, valueToSet);
                } else {
                  (targetDom as any).value = valueToSet;
                }
              }

              const inputEv = new Event('input', { bubbles: true });
              targetDom.dispatchEvent(inputEv);

              const changeEv = new Event('change', { bubbles: true });
              targetDom.dispatchEvent(changeEv);
            }
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

      case 'callAction': {
        const lastDot = command.target.lastIndexOf('.');
        if (lastDot === -1) {
          this.send({
            type: 'commandAck',
            commandId: command.commandId,
            success: false,
            error: 'Invalid target format. Expected "StoreName.actionName" or "ZustandStore#StoreName.actionName".',
          });
          return;
        }

        const rawStoreName = command.target.substring(0, lastDot);
        const actionName = command.target.substring(lastDot + 1);

        let componentId = rawStoreName;
        if (!componentId.startsWith('ZustandStore#') && registry.has(`ZustandStore#${componentId}`)) {
          componentId = `ZustandStore#${componentId}`;
        }

        const entry = registry.get(componentId);
        if (!entry) {
          this.send({
            type: 'commandAck',
            commandId: command.commandId,
            success: false,
            error: `Store/Component "${componentId}" not found in registry.`,
          });
          return;
        }

        const actionFn = entry.actions?.[actionName];
        if (typeof actionFn !== 'function') {
          this.send({
            type: 'commandAck',
            commandId: command.commandId,
            success: false,
            error: `Action "${actionName}" not found or is not a function in "${componentId}".`,
          });
          return;
        }

        AgentLogger.addEntry({
          type: 'info',
          source: 'agent',
          message: `callAction -> ${command.target} (args: ${JSON.stringify(command.args)})`,
          timestamp: Date.now(),
        });

        try {
          const result = actionFn(...command.args);
          if (result instanceof Promise) {
            result.then(
              () => {
                this.send({ type: 'commandAck', commandId: command.commandId, success: true });
              },
              (err: any) => {
                this.send({
                  type: 'commandAck',
                  commandId: command.commandId,
                  success: false,
                  error: `Async action failed: ${err.message || err}`,
                });
              }
            );
          } else {
            this.send({ type: 'commandAck', commandId: command.commandId, success: true });
          }
        } catch (err: any) {
          this.send({
            type: 'commandAck',
            commandId: command.commandId,
            success: false,
            error: `Action invocation failed: ${err.message || err}`,
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
