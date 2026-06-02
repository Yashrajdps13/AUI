// @vitest-environment jsdom
import { describe, it, expect, beforeAll, afterAll, vi } from 'vitest';
import { WebSocketServer } from 'ws';
import WebSocket from 'ws';
import { AgentWebSocketManager } from './websocket.js';
import { BridgeStore } from './store.js';
import { ComponentEntry } from './types.js';
import { AgentLogger } from './logger.js';

// Configure the manager to use the ws library WebSocket client implementation in Node
AgentWebSocketManager.WebSocketClass = WebSocket;

describe('AgentWebSocketManager', () => {
  let wss: WebSocketServer;
  let port: number;
  let serverSocket: any = null;
  const messagesReceived: any[] = [];

  beforeAll(async () => {
    // Spin up local mock WS server on a random available port
    wss = new WebSocketServer({ port: 0 });
    await new Promise<void>((resolve) => {
      wss.on('listening', () => {
        const address = wss.address();
        if (typeof address === 'object' && address !== null) {
          port = address.port;
        }
        resolve();
      });
    });

    wss.on('connection', (ws) => {
      serverSocket = ws;
      ws.on('message', (data) => {
        try {
          messagesReceived.push(JSON.parse(data.toString()));
        } catch (err) {
          console.error(err);
        }
      });
    });
  });

  afterAll(async () => {
    AgentWebSocketManager.disconnect();
    wss.close();
  });

  it('should connect to the server and synchronize initial registry', async () => {
    BridgeStore.clear();

    const dummyComponent: Omit<ComponentEntry, 'id'> = {
      displayName: 'Card',
      fiberRef: null,
      domRef: null,
      stateSlots: [
        { key: 'expanded', value: false, setter: () => {}, hookIndex: 0 }
      ],
      mountedAt: Date.now(),
      route: '/dashboard'
    };
    BridgeStore.registerComponent('Card#1', dummyComponent);

    // Connect
    AgentWebSocketManager.connect(`ws://localhost:${port}`);

    // Wait for the registryDelta message
    await new Promise<void>((resolve) => {
      const check = () => {
        const deltaMsg = messagesReceived.find((m) => m.type === 'registryDelta');
        if (deltaMsg) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    const delta = messagesReceived.find((m) => m.type === 'registryDelta');
    expect(delta).toBeDefined();
    expect(delta.added.length).toBe(1);
    expect(delta.added[0].id).toBe('Card#1');
    expect(delta.added[0].displayName).toBe('Card');
    expect(delta.added[0].stateSlots[0].key).toBe('expanded');
  });

  it('should support subscription and push values on changes', async () => {
    messagesReceived.length = 0;

    // Send subscribe command from server to client
    serverSocket.send(JSON.stringify({
      type: 'subscribe',
      commandId: 'cmd-1',
      target: 'Card#1'
    }));

    // Wait for command Ack and initial stateSnapshot
    await new Promise<void>((resolve) => {
      const check = () => {
        const ack = messagesReceived.find((m) => m.type === 'commandAck' && m.commandId === 'cmd-1');
        const snapshot = messagesReceived.find((m) => m.type === 'stateSnapshot');
        if (ack && snapshot) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    const snapshot = messagesReceived.find((m) => m.type === 'stateSnapshot');
    expect(snapshot.target).toBe('Card#1.expanded');
    expect(snapshot.value).toBe(false);

    // Trigger state change in store
    messagesReceived.length = 0;
    BridgeStore.updateStateSlotValue('Card#1', 'expanded', true);

    // Wait for the new value snapshot
    await new Promise<void>((resolve) => {
      const check = () => {
        const updatedSnapshot = messagesReceived.find((m) => m.type === 'stateSnapshot');
        if (updatedSnapshot) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    const updatedSnapshot = messagesReceived.find((m) => m.type === 'stateSnapshot');
    expect(updatedSnapshot.value).toBe(true);
  });

  it('should handle queryState commands from the agent', async () => {
    messagesReceived.length = 0;

    serverSocket.send(JSON.stringify({
      type: 'queryState',
      commandId: 'cmd-2',
      target: 'Card#1.expanded'
    }));

    await new Promise<void>((resolve) => {
      const check = () => {
        const ack = messagesReceived.find((m) => m.type === 'commandAck' && m.commandId === 'cmd-2');
        const snapshot = messagesReceived.find((m) => m.type === 'stateSnapshot' && m.target === 'Card#1.expanded');
        if (ack && snapshot) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    const snapshot = messagesReceived.find((m) => m.type === 'stateSnapshot');
    expect(snapshot.value).toBe(true);
  });

  it('should handle setState commands by invoking setters', async () => {
    messagesReceived.length = 0;
    const mockSetter = vi.fn();

    BridgeStore.registerComponent('Card#1', {
      displayName: 'Card',
      fiberRef: null,
      domRef: null,
      stateSlots: [
        { key: 'expanded', value: true, setter: mockSetter, hookIndex: 0 }
      ],
      mountedAt: Date.now(),
      route: '/dashboard'
    });

    serverSocket.send(JSON.stringify({
      type: 'setState',
      commandId: 'cmd-3',
      target: 'Card#1.expanded',
      value: false
    }));

    await new Promise<void>((resolve) => {
      const check = () => {
        const ack = messagesReceived.find((m) => m.type === 'commandAck' && m.commandId === 'cmd-3');
        if (ack) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    expect(mockSetter).toHaveBeenCalledWith(false);
  });

  it('should redact sensitive state values to [REDACTED] in all WebSocket communications and logs', async () => {
    messagesReceived.length = 0;
    const mockPinSetter = vi.fn();
    const pinComponent: Omit<ComponentEntry, 'id'> = {
      displayName: 'SecretCard',
      fiberRef: null,
      domRef: null,
      stateSlots: [
        { key: 'pin', value: '1234', setter: mockPinSetter, hookIndex: 0, sensitive: true }
      ],
      mountedAt: Date.now(),
      route: '/secret'
    };

    BridgeStore.registerComponent('SecretCard#1', pinComponent);

    // 1. Verify registry delta serializes sensitive flag
    (AgentWebSocketManager as any).syncRegistryAndSubscriptions(true);
    await new Promise<void>((resolve) => {
      const check = () => {
        const delta = messagesReceived.find((m) => m.type === 'registryDelta' && m.added.some((c: any) => c.id === 'SecretCard#1'));
        if (delta) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    const delta = messagesReceived.find((m) => m.type === 'registryDelta' && m.added.some((c: any) => c.id === 'SecretCard#1'));
    const secretComp = delta.added.find((c: any) => c.id === 'SecretCard#1');
    expect(secretComp.stateSlots[0].sensitive).toBe(true);

    // 2. Verify state query is redacted
    messagesReceived.length = 0;
    serverSocket.send(JSON.stringify({
      type: 'queryState',
      commandId: 'cmd-pin-query',
      target: 'SecretCard#1.pin'
    }));

    await new Promise<void>((resolve) => {
      const check = () => {
        const ack = messagesReceived.find((m) => m.type === 'commandAck' && m.commandId === 'cmd-pin-query');
        if (ack) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    const querySnapshot = messagesReceived.find((m) => m.type === 'stateSnapshot' && m.target === 'SecretCard#1.pin');
    expect(querySnapshot.value).toBe('[REDACTED]');

    // 3. Verify subscription is redacted
    messagesReceived.length = 0;
    serverSocket.send(JSON.stringify({
      type: 'subscribe',
      commandId: 'cmd-pin-sub',
      target: 'SecretCard#1'
    }));

    await new Promise<void>((resolve) => {
      const check = () => {
        const ack = messagesReceived.find((m) => m.type === 'commandAck' && m.commandId === 'cmd-pin-sub');
        if (ack) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    const subSnapshot = messagesReceived.find((m) => m.type === 'stateSnapshot' && m.target === 'SecretCard#1.pin');
    expect(subSnapshot.value).toBe('[REDACTED]');

    // 4. Verify live update keeps the real value in React store
    BridgeStore.updateStateSlotValue('SecretCard#1', 'pin', '4321');
    const updatedEntry = BridgeStore.getSnapshot().get('SecretCard#1');
    expect(updatedEntry?.stateSlots[0].value).toBe('4321');

    // 5. Verify queryState after update still returns [REDACTED]
    messagesReceived.length = 0;
    serverSocket.send(JSON.stringify({
      type: 'queryState',
      commandId: 'cmd-pin-query-2',
      target: 'SecretCard#1.pin'
    }));

    await new Promise<void>((resolve) => {
      const check = () => {
        const ack = messagesReceived.find((m) => m.type === 'commandAck' && m.commandId === 'cmd-pin-query-2');
        if (ack) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    const querySnapshot2 = messagesReceived.find((m) => m.type === 'stateSnapshot' && m.target === 'SecretCard#1.pin');
    expect(querySnapshot2.value).toBe('[REDACTED]');

    // 6. Verify setState logging is redacted in AgentLogger
    messagesReceived.length = 0;
    serverSocket.send(JSON.stringify({
      type: 'setState',
      commandId: 'cmd-pin-set',
      target: 'SecretCard#1.pin',
      value: '9999'
    }));

    await new Promise<void>((resolve) => {
      const check = () => {
        const ack = messagesReceived.find((m) => m.type === 'commandAck' && m.commandId === 'cmd-pin-set');
        if (ack) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    expect(mockPinSetter).toHaveBeenCalledWith('9999');
    
    const ledger = AgentLogger.getLedger();
    const setEntry = ledger[ledger.length - 1];
    expect(setEntry.message).toContain('[REDACTED]');
    expect(setEntry.message).not.toContain('9999');
  });

  it('should extract interactiveElements with disabled and visible properties, and send renderSettled', async () => {
    messagesReceived.length = 0;
    
    const container = document.createElement('div');
    container.id = 'container-root';
    
    const activeBtn = document.createElement('button');
    activeBtn.id = 'btn-active';
    activeBtn.innerText = 'Click me';
    
    const disabledBtn = document.createElement('button');
    disabledBtn.id = 'btn-disabled';
    disabledBtn.disabled = true;
    disabledBtn.innerText = 'Disabled';
    
    const hiddenDiv = document.createElement('div');
    hiddenDiv.style.display = 'none';
    
    const hiddenBtn = document.createElement('button');
    hiddenBtn.id = 'btn-hidden';
    hiddenBtn.innerText = 'Hidden';
    
    hiddenDiv.appendChild(hiddenBtn);
    container.appendChild(activeBtn);
    container.appendChild(disabledBtn);
    container.appendChild(hiddenDiv);
    
    document.body.appendChild(container);
    
    BridgeStore.registerComponent('App#123', {
      displayName: 'App',
      fiberRef: null,
      domRef: container,
      stateSlots: [],
      mountedAt: Date.now(),
      route: '/'
    });
    
    (AgentWebSocketManager as any).syncRegistryAndSubscriptions(true);
    
    await new Promise<void>((resolve) => {
      const check = () => {
        const deltaMsg = messagesReceived.find((m) => m.type === 'registryDelta');
        if (deltaMsg) resolve();
        else setTimeout(check, 50);
      };
      check();
    });
    
    const delta = messagesReceived.find((m) => m.type === 'registryDelta');
    expect(delta).toBeDefined();
    
    const appComp = delta.added.find((c: any) => c.id === 'App#123');
    expect(appComp).toBeDefined();
    expect(appComp.interactiveElements).toBeDefined();
    
    const activeEl = appComp.interactiveElements.find((el: any) => el.id === 'btn-active');
    expect(activeEl).toBeDefined();
    expect(activeEl.disabled).toBeUndefined();
    expect(activeEl.visible).toBe(true);
    
    const disabledEl = appComp.interactiveElements.find((el: any) => el.id === 'btn-disabled');
    expect(disabledEl).toBeDefined();
    expect(disabledEl.disabled).toBe(true);
    
    const hiddenEl = appComp.interactiveElements.find((el: any) => el.id === 'btn-hidden');
    expect(hiddenEl).toBeDefined();
    expect(hiddenEl.visible).toBe(false);
    
    messagesReceived.length = 0;
    AgentWebSocketManager.onRenderSettled('container-root');
    
    await new Promise<void>((resolve) => {
      const check = () => {
        const settledMsg = messagesReceived.find((m) => m.type === 'renderSettled');
        if (settledMsg) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    expect(messagesReceived[0]).toEqual({
      type: 'renderSettled',
      target: 'container-root'
    });
    
    document.body.removeChild(container);
  });

  it('should handle callAction command and execute store actions', async () => {
    messagesReceived.length = 0;
    const actionSpy = vi.fn();
    
    BridgeStore.registerComponent('ZustandStore#Auth', {
      displayName: 'ZustandStore#Auth',
      fiberRef: null,
      domRef: null,
      stateSlots: [],
      mountedAt: Date.now(),
      route: '/',
      actions: {
        login: actionSpy,
      },
    });

    serverSocket.send(JSON.stringify({
      type: 'callAction',
      commandId: 'cmd-call-1',
      target: 'Auth.login',
      args: ['user123', 'pass123'],
    }));

    await new Promise<void>((resolve) => {
      const check = () => {
        const ack = messagesReceived.find((m) => m.type === 'commandAck' && m.commandId === 'cmd-call-1');
        if (ack) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    expect(actionSpy).toHaveBeenCalledWith('user123', 'pass123');
    const ack = messagesReceived.find((m) => m.type === 'commandAck' && m.commandId === 'cmd-call-1');
    expect(ack.success).toBe(true);
  });
});
