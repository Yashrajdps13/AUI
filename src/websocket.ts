import { startTransition } from 'react';
import { BridgeStore } from './store.js';
import { AgentCommand, BridgeMessage, SerializedComponentEntry } from './protocol.js';
import { AgentLogger, CommandAuditLogger } from './logger.js';

export interface WriteSecurityScope {
  allowedTargets?: string[];
  allowedActions?: string[];
  allowedRoutes?: string[];
}

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

  // Active condition watchers for waitFor command
  private activeWatchers: Map<string, {
    commandId: string;
    target: string;
    condition: { operator: 'equals' | 'truthy' | 'falsy' | 'changed'; value?: unknown };
    initialValue: unknown;
    timeoutTimer: any;
  }> = new Map();

  private writeScope?: WriteSecurityScope = undefined;

  // Allow overriding WebSocket class (for Node.js testing environments)
  public WebSocketClass: any = typeof WebSocket !== 'undefined' ? WebSocket : null;

  /**
   * Connects to the agent backend WebSocket.
   */
  connect(url: string, options?: { writeScope?: WriteSecurityScope }): void {
    this.url = url;
    this.isDisconnecting = false;
    this.writeScope = options?.writeScope;

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

    const socket = this.ws;
    this.ws.onopen = () => {
      if (this.ws !== socket) return;
      this.reconnectDelay = 1000; // Reset backoff
      this.onConnected();
    };

    this.ws.onclose = () => {
      if (this.ws === socket) {
        this.onDisconnected();
      }
    };

    this.ws.onerror = (err: any) => {
      if (this.ws !== socket) return;
      console.error('Bridge WebSocket error:', err);
    };

    this.ws.onmessage = (event: any) => {
      if (this.ws !== socket) return;
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

    for (const watcher of this.activeWatchers.values()) {
      clearTimeout(watcher.timeoutTimer);
    }
    this.activeWatchers.clear();
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

  private getRedactedValue(
    target: string,
    type: 'setState' | 'dispatchEvent' | 'callAction',
    rawValue: any
  ): any {
    const registry = BridgeStore.getSnapshot();

    if (type === 'setState') {
      const lastDot = target.lastIndexOf('.');
      if (lastDot !== -1) {
        const componentId = target.substring(0, lastDot);
        const stateKey = target.substring(lastDot + 1);
        const entry = registry.get(componentId);
        const slot = entry?.stateSlots.find((s) => s.key === stateKey);
        if (slot?.sensitive) {
          return '[REDACTED]';
        }
      }
    } else if (type === 'dispatchEvent') {
      const componentId = target;
      const entry = registry.get(componentId);
      if (entry) {
        const hasSensitiveSlots = entry.stateSlots.some(s => s.sensitive);
        if (hasSensitiveSlots) {
          const payloadStr = typeof rawValue === 'object' ? JSON.stringify(rawValue) : String(rawValue);
          const isPayloadSensitive = entry.stateSlots.some(s => s.sensitive && (
            payloadStr.toLowerCase().includes(s.key.toLowerCase()) ||
            target.toLowerCase().includes(s.key.toLowerCase())
          ));
          if (isPayloadSensitive) {
            return '[REDACTED]';
          }
        }

        const dom = entry.domRef;
        if (dom) {
          let targetDom: HTMLElement | null = dom;
          let selector = '';
          if (rawValue && typeof rawValue === 'object' && typeof (rawValue as any).selector === 'string') {
            selector = (rawValue as any).selector;
          } else if (rawValue && typeof rawValue === 'string') {
            selector = rawValue;
          }
          if (selector) {
            try {
              const selected = dom.querySelector(selector);
              if (selected instanceof HTMLElement) targetDom = selected;
            } catch {
              // query failed
            }
          }

          if (targetDom) {
            const isPassword = targetDom instanceof HTMLInputElement && targetDom.type === 'password';
            const name = targetDom.getAttribute('name') || '';
            const id = targetDom.id || '';
            const autocomplete = targetDom.getAttribute('autocomplete') || '';
            const placeholder = targetDom.getAttribute('placeholder') || '';
            const className = targetDom.className || '';
            const sensitiveKeywords = ['password', 'pin', 'secret', 'cvc', 'cvv', 'creditcard', 'cardnumber', 'ssn', 'token'];
            const matchesKeyword = sensitiveKeywords.some(keyword =>
              name.toLowerCase().includes(keyword) ||
              id.toLowerCase().includes(keyword) ||
              autocomplete.toLowerCase().includes(keyword) ||
              placeholder.toLowerCase().includes(keyword) ||
              className.toLowerCase().includes(keyword) ||
              selector.toLowerCase().includes(keyword)
            );

            if (isPassword || matchesKeyword) {
              return '[REDACTED]';
            }
          }
        }
      }
    } else if (type === 'callAction') {
      const lastDot = target.lastIndexOf('.');
      if (lastDot !== -1) {
        const storeName = target.substring(0, lastDot);
        const actionName = target.substring(lastDot + 1);
        
        let componentId = storeName;
        if (!componentId.startsWith('ZustandStore#') && registry.has(`ZustandStore#${componentId}`)) {
          componentId = `ZustandStore#${componentId}`;
        }
        const entry = registry.get(componentId);
        
        const sensitiveKeywords = ['password', 'pin', 'secret', 'cvc', 'cvv', 'creditcard', 'cardnumber', 'ssn', 'token', 'auth', 'login', 'credentials'];
        const matchesKeyword = sensitiveKeywords.some(keyword =>
          actionName.toLowerCase().includes(keyword)
        );

        if (matchesKeyword) {
          return '[REDACTED]';
        }

        if (entry) {
          const hasSensitiveKeyInAction = entry.stateSlots.some(s => s.sensitive && (
            actionName.toLowerCase().includes(s.key.toLowerCase())
          ));
          if (hasSensitiveKeyInAction) {
            return '[REDACTED]';
          }
        }
      }
    }

    return rawValue;
  }

  private isWriteAllowed(target: string, type: 'state' | 'event' | 'action'): { allowed: boolean; error?: string } {
    if (!this.writeScope) {
      return { allowed: true };
    }

    // 1. Route validation
    if (this.writeScope.allowedRoutes && typeof window !== 'undefined') {
      const currentRoute = window.location.pathname;
      const isRouteAllowed = this.writeScope.allowedRoutes.some((route) => {
        return currentRoute === route || currentRoute.startsWith(route);
      });
      if (!isRouteAllowed) {
        return {
          allowed: false,
          error: `Write operation on route "${currentRoute}" is not allowed under the current security scope.`,
        };
      }
    }

    // 2. Target ID and action validation
    if (type === 'action') {
      const lastDot = target.lastIndexOf('.');
      if (lastDot === -1) {
        return { allowed: false, error: `Invalid action target format: "${target}".` };
      }
      const rawStoreName = target.substring(0, lastDot);

      if (this.writeScope.allowedActions) {
        const matchesAction = this.writeScope.allowedActions.some((allowed) => {
          return allowed === target || allowed === `ZustandStore#${target}` || `ZustandStore#${allowed}` === target;
        });
        if (!matchesAction) {
          return {
            allowed: false,
            error: `Action "${target}" is not allowed under the current security scope.`,
          };
        }
      }

      if (this.writeScope.allowedTargets) {
        let componentId = rawStoreName;
        const matchesTarget = this.writeScope.allowedTargets.some((allowed) => {
          return (
            allowed === componentId ||
            allowed === `ZustandStore#${componentId}` ||
            `ZustandStore#${allowed}` === componentId
          );
        });
        if (!matchesTarget) {
          return {
            allowed: false,
            error: `Store "${componentId}" is not allowed under the current security scope.`,
          };
        }
      }
    } else {
      let componentId = target;
      if (type === 'state') {
        const lastDot = target.lastIndexOf('.');
        if (lastDot !== -1) {
          componentId = target.substring(0, lastDot);
        }
      }

      if (this.writeScope.allowedTargets) {
        const registry = BridgeStore.getSnapshot();
        const entry = registry.get(componentId);
        const displayName = entry?.displayName;

        const matchesTarget = this.writeScope.allowedTargets.some((allowed) => {
          return (
            allowed === componentId ||
            (displayName && allowed === displayName) ||
            allowed === `ZustandStore#${componentId}` ||
            `ZustandStore#${allowed}` === componentId
          );
        });

        if (!matchesTarget) {
          return {
            allowed: false,
            error: `Target "${componentId}" is not allowed under the current security scope.`,
          };
        }
      }
    }

    return { allowed: true };
  }

  private getTargetValue(target: string): { found: boolean; value?: unknown } {
    const registry = BridgeStore.getSnapshot();
    const lastDot = target.lastIndexOf('.');
    if (lastDot === -1) return { found: false };

    const componentId = target.substring(0, lastDot);
    const stateKey = target.substring(lastDot + 1);

    const entry = registry.get(componentId);
    const slot = entry?.stateSlots.find((s) => s.key === stateKey);

    if (!slot) return { found: false };
    return { found: true, value: slot.value };
  }

  private checkWatcherCondition(watcher: {
    target: string;
    condition: { operator: 'equals' | 'truthy' | 'falsy' | 'changed'; value?: unknown };
    initialValue: unknown;
  }): boolean {
    const { found, value } = this.getTargetValue(watcher.target);
    if (!found) return false;

    const op = watcher.condition.operator;
    const targetVal = watcher.condition.value;

    if (op === 'equals') {
      if (typeof targetVal === 'object' && targetVal !== null) {
        return JSON.stringify(value) === JSON.stringify(targetVal);
      }
      return value === targetVal;
    } else if (op === 'truthy') {
      return !!value;
    } else if (op === 'falsy') {
      return !value;
    } else if (op === 'changed') {
      if (typeof watcher.initialValue === 'object' && watcher.initialValue !== null) {
        return JSON.stringify(value) !== JSON.stringify(watcher.initialValue);
      }
      return value !== watcher.initialValue;
    }
    return false;
  }

  private evaluateWatchers(): void {
    if (this.activeWatchers.size === 0) return;

    for (const [commandId, watcher] of this.activeWatchers.entries()) {
      if (this.checkWatcherCondition(watcher)) {
        clearTimeout(watcher.timeoutTimer);
        this.activeWatchers.delete(commandId);
        this.send({ type: 'commandAck', commandId, success: true });
      }
    }
  }

  /**
   * Scans current store registry, diffs against cache, and publishes registryDelta and stateSnapshots.
   */
  private syncRegistryAndSubscriptions(forceFull = false): void {
    this.evaluateWatchers();
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
        const valueToSend = (slot.sensitive && slot.value) ? '[REDACTED]' : slot.value;
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
      case 'agentStatus': {
        BridgeStore.setAgentStatus(command.status);
        if (command.commandId) {
          this.send({ type: 'commandAck', commandId: command.commandId, success: true });
        }
        break;
      }
      case 'queryLedger': {
        this.send({
          type: 'ledgerSnapshot',
          commandId: command.commandId,
          ledger: AgentLogger.getLedger(),
        });
        this.send({ type: 'commandAck', commandId: command.commandId, success: true });
        break;
      }

      case 'queryAuditLog': {
        this.send({
          type: 'auditLogSnapshot',
          commandId: command.commandId,
          auditLog: CommandAuditLogger.getAuditLog(),
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
            const valueToSend = (slot.sensitive && slot.value) ? '[REDACTED]' : slot.value;
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
          const valueToSend = (slot.sensitive && slot.value) ? '[REDACTED]' : slot.value;
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
        const securityCheck = this.isWriteAllowed(command.target, 'state');
        if (!securityCheck.allowed) {
          AgentLogger.addEntry({
            type: 'warn',
            source: 'agent',
            message: `Blocked setState -> ${command.target}: ${securityCheck.error}`,
            timestamp: Date.now(),
          });
          const redactedVal = this.getRedactedValue(command.target, 'setState', command.value);
          CommandAuditLogger.addEntry({
            commandId: command.commandId,
            type: 'setState',
            target: command.target,
            value: redactedVal,
            success: false,
            error: securityCheck.error,
            timestamp: Date.now(),
          });
          this.send({
            type: 'commandAck',
            commandId: command.commandId,
            success: false,
            error: securityCheck.error,
          });
          return;
        }

        const lastDot = command.target.lastIndexOf('.');
        if (lastDot === -1) {
          const err = 'Invalid target path format. Expected "componentId.stateKey".';
          const redactedVal = this.getRedactedValue(command.target, 'setState', command.value);
          CommandAuditLogger.addEntry({
            commandId: command.commandId,
            type: 'setState',
            target: command.target,
            value: redactedVal,
            success: false,
            error: err,
            timestamp: Date.now(),
          });
          this.send({
            type: 'commandAck',
            commandId: command.commandId,
            success: false,
            error: err,
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
            CommandAuditLogger.addEntry({
              commandId: command.commandId,
              type: 'setState',
              target: command.target,
              value: loggedValue,
              success: true,
              timestamp: Date.now(),
            });
            this.send({ type: 'commandAck', commandId: command.commandId, success: true });
          } catch (err: any) {
            const errMsg = `State setter failed: ${err.message || err}`;
            CommandAuditLogger.addEntry({
              commandId: command.commandId,
              type: 'setState',
              target: command.target,
              value: loggedValue,
              success: false,
              error: errMsg,
              timestamp: Date.now(),
            });
            this.send({
              type: 'commandAck',
              commandId: command.commandId,
              success: false,
              error: errMsg,
            });
          }
        } else {
          const errMsg = `Target state "${stateKey}" not found in component "${componentId}".`;
          CommandAuditLogger.addEntry({
            commandId: command.commandId,
            type: 'setState',
            target: command.target,
            value: loggedValue,
            success: false,
            error: errMsg,
            timestamp: Date.now(),
          });
          this.send({
            type: 'commandAck',
            commandId: command.commandId,
            success: false,
            error: errMsg,
          });
        }
        break;
      }

      case 'dispatchEvent': {
        const securityCheck = this.isWriteAllowed(command.target, 'event');
        if (!securityCheck.allowed) {
          AgentLogger.addEntry({
            type: 'warn',
            source: 'agent',
            message: `Blocked dispatchEvent -> ${command.event} on ${command.target}: ${securityCheck.error}`,
            timestamp: Date.now(),
          });
          const redactedVal = this.getRedactedValue(command.target, 'dispatchEvent', command.payload);
          CommandAuditLogger.addEntry({
            commandId: command.commandId,
            type: 'dispatchEvent',
            target: `${command.target}.${command.event}`,
            value: redactedVal,
            success: false,
            error: securityCheck.error,
            timestamp: Date.now(),
          });
          this.send({
            type: 'commandAck',
            commandId: command.commandId,
            success: false,
            error: securityCheck.error,
          });
          return;
        }

        const redactedVal = this.getRedactedValue(command.target, 'dispatchEvent', command.payload);

        AgentLogger.addEntry({
          type: 'info',
          source: 'agent',
          message: `dispatchEvent -> ${command.event} on ${command.target} (payload: ${typeof redactedVal === 'object' ? JSON.stringify(redactedVal) : String(redactedVal)})`,
          timestamp: Date.now(),
        });

        const entry = registry.get(command.target);
        if (!entry || !entry.domRef) {
          const errMsg = `Component DOM reference for "${command.target}" not found.`;
          CommandAuditLogger.addEntry({
            commandId: command.commandId,
            type: 'dispatchEvent',
            target: `${command.target}.${command.event}`,
            value: redactedVal,
            success: false,
            error: errMsg,
            timestamp: Date.now(),
          });
          this.send({
            type: 'commandAck',
            commandId: command.commandId,
            success: false,
            error: errMsg,
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

          CommandAuditLogger.addEntry({
            commandId: command.commandId,
            type: 'dispatchEvent',
            target: `${command.target}.${command.event}`,
            value: redactedVal,
            success: true,
            timestamp: Date.now(),
          });
          this.send({ type: 'commandAck', commandId: command.commandId, success: true });
        } catch (err: any) {
          const errMsg = `Failed to dispatch event: ${err.message || err}`;
          CommandAuditLogger.addEntry({
            commandId: command.commandId,
            type: 'dispatchEvent',
            target: `${command.target}.${command.event}`,
            value: redactedVal,
            success: false,
            error: errMsg,
            timestamp: Date.now(),
          });
          this.send({
            type: 'commandAck',
            commandId: command.commandId,
            success: false,
            error: errMsg,
          });
        }
        break;
      }

      case 'callAction': {
        const securityCheck = this.isWriteAllowed(command.target, 'action');
        if (!securityCheck.allowed) {
          AgentLogger.addEntry({
            type: 'warn',
            source: 'agent',
            message: `Blocked callAction -> ${command.target}: ${securityCheck.error}`,
            timestamp: Date.now(),
          });
          const redactedVal = this.getRedactedValue(command.target, 'callAction', command.args);
          CommandAuditLogger.addEntry({
            commandId: command.commandId,
            type: 'callAction',
            target: command.target,
            value: redactedVal,
            success: false,
            error: securityCheck.error,
            timestamp: Date.now(),
          });
          this.send({
            type: 'commandAck',
            commandId: command.commandId,
            success: false,
            error: securityCheck.error,
          });
          return;
        }

        const lastDot = command.target.lastIndexOf('.');
        if (lastDot === -1) {
          const errMsg = 'Invalid target format. Expected "StoreName.actionName" or "ZustandStore#StoreName.actionName".';
          const redactedVal = this.getRedactedValue(command.target, 'callAction', command.args);
          CommandAuditLogger.addEntry({
            commandId: command.commandId,
            type: 'callAction',
            target: command.target,
            value: redactedVal,
            success: false,
            error: errMsg,
            timestamp: Date.now(),
          });
          this.send({
            type: 'commandAck',
            commandId: command.commandId,
            success: false,
            error: errMsg,
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
          const errMsg = `Store/Component "${componentId}" not found in registry.`;
          const redactedVal = this.getRedactedValue(command.target, 'callAction', command.args);
          CommandAuditLogger.addEntry({
            commandId: command.commandId,
            type: 'callAction',
            target: command.target,
            value: redactedVal,
            success: false,
            error: errMsg,
            timestamp: Date.now(),
          });
          this.send({
            type: 'commandAck',
            commandId: command.commandId,
            success: false,
            error: errMsg,
          });
          return;
        }

        const actionFn = entry.actions?.[actionName];
        if (typeof actionFn !== 'function') {
          const errMsg = `Action "${actionName}" not found or is not a function in "${componentId}".`;
          const redactedVal = this.getRedactedValue(command.target, 'callAction', command.args);
          CommandAuditLogger.addEntry({
            commandId: command.commandId,
            type: 'callAction',
            target: command.target,
            value: redactedVal,
            success: false,
            error: errMsg,
            timestamp: Date.now(),
          });
          this.send({
            type: 'commandAck',
            commandId: command.commandId,
            success: false,
            error: errMsg,
          });
          return;
        }

        const redactedVal = this.getRedactedValue(command.target, 'callAction', command.args);

        AgentLogger.addEntry({
          type: 'info',
          source: 'agent',
          message: `callAction -> ${command.target} (args: ${JSON.stringify(redactedVal)})`,
          timestamp: Date.now(),
        });

        try {
          const result = actionFn(...command.args);
          if (result instanceof Promise) {
            result.then(
              () => {
                CommandAuditLogger.addEntry({
                  commandId: command.commandId,
                  type: 'callAction',
                  target: command.target,
                  value: redactedVal,
                  success: true,
                  timestamp: Date.now(),
                });
                this.send({ type: 'commandAck', commandId: command.commandId, success: true });
              },
              (err: any) => {
                const errMsg = `Async action failed: ${err.message || err}`;
                CommandAuditLogger.addEntry({
                  commandId: command.commandId,
                  type: 'callAction',
                  target: command.target,
                  value: redactedVal,
                  success: false,
                  error: errMsg,
                  timestamp: Date.now(),
                });
                this.send({
                  type: 'commandAck',
                  commandId: command.commandId,
                  success: false,
                  error: errMsg,
                });
              }
            );
          } else {
            CommandAuditLogger.addEntry({
              commandId: command.commandId,
              type: 'callAction',
              target: command.target,
              value: redactedVal,
              success: true,
              timestamp: Date.now(),
            });
            this.send({ type: 'commandAck', commandId: command.commandId, success: true });
          }
        } catch (err: any) {
          const errMsg = `Action invocation failed: ${err.message || err}`;
          CommandAuditLogger.addEntry({
            commandId: command.commandId,
            type: 'callAction',
            target: command.target,
            value: redactedVal,
            success: false,
            error: errMsg,
            timestamp: Date.now(),
          });
          this.send({
            type: 'commandAck',
            commandId: command.commandId,
            success: false,
            error: errMsg,
          });
        }
        break;
      }

      case 'waitFor': {
        const { found, value } = this.getTargetValue(command.target);
        if (!found) {
          this.send({
            type: 'commandAck',
            commandId: command.commandId,
            success: false,
            error: `Target state slot "${command.target}" not found in registry.`,
          });
          return;
        }

        const op = command.condition.operator;
        const targetVal = command.condition.value;
        let isSatisfied = false;

        if (op === 'equals') {
          if (typeof targetVal === 'object' && targetVal !== null) {
            isSatisfied = JSON.stringify(value) === JSON.stringify(targetVal);
          } else {
            isSatisfied = value === targetVal;
          }
        } else if (op === 'truthy') {
          isSatisfied = !!value;
        } else if (op === 'falsy') {
          isSatisfied = !value;
        } else if (op === 'changed') {
          isSatisfied = false;
        }

        if (isSatisfied) {
          this.send({ type: 'commandAck', commandId: command.commandId, success: true });
          return;
        }

        const timeoutMs = command.timeoutMs ?? 5000;
        const timeoutTimer = setTimeout(() => {
          const watcher = this.activeWatchers.get(command.commandId);
          if (watcher) {
            this.activeWatchers.delete(command.commandId);
            this.send({
              type: 'commandAck',
              commandId: command.commandId,
              success: false,
              error: `Timeout waiting for condition on "${command.target}".`,
            });
          }
        }, timeoutMs);

        this.activeWatchers.set(command.commandId, {
          commandId: command.commandId,
          target: command.target,
          condition: command.condition,
          initialValue: value,
          timeoutTimer,
        });
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
