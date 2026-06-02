// @vitest-environment jsdom
import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { WebSocketServer } from 'ws';
import WebSocket from 'ws';
import { AgentWebSocketManager } from './websocket.js';
import { BridgeStore } from './store.js';

AgentWebSocketManager.WebSocketClass = WebSocket;

describe('waitFor condition command', () => {
  let wss: WebSocketServer;
  let port: number;
  let serverSocket: any = null;
  const messagesReceived: any[] = [];

  beforeAll(async () => {
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

  it('resolves immediately if condition is satisfied at command start', async () => {
    BridgeStore.clear();
    messagesReceived.length = 0;

    // Register a mock component with a state slot
    BridgeStore.registerComponent('App#1', {
      displayName: 'App',
      fiberRef: null,
      domRef: null,
      stateSlots: [
        { key: 'status', value: 'idle', setter: () => {}, hookIndex: 0 }
      ],
      mountedAt: Date.now(),
      route: '/'
    });

    // Connect WebSocket
    AgentWebSocketManager.connect(`ws://localhost:${port}`);

    // Wait for connection to open
    await new Promise<void>((resolve) => {
      const check = () => {
        if (serverSocket && serverSocket.readyState === 1) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    // Send a waitFor status === "idle" which is already true
    serverSocket.send(JSON.stringify({
      type: 'waitFor',
      commandId: 'cmd-wait-1',
      target: 'App#1.status',
      condition: {
        operator: 'equals',
        value: 'idle'
      }
    }));

    // Wait for command Ack
    await new Promise<void>((resolve) => {
      const check = () => {
        const ack = messagesReceived.find((m) => m.type === 'commandAck' && m.commandId === 'cmd-wait-1');
        if (ack) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    const ack = messagesReceived.find((m) => m.type === 'commandAck' && m.commandId === 'cmd-wait-1');
    expect(ack.success).toBe(true);
  });

  it('awaits and resolves when condition is satisfied after state update', async () => {
    messagesReceived.length = 0;

    // Send a waitFor status === "loaded" which is currently "idle"
    serverSocket.send(JSON.stringify({
      type: 'waitFor',
      commandId: 'cmd-wait-2',
      target: 'App#1.status',
      condition: {
        operator: 'equals',
        value: 'loaded'
      }
    }));

    // Wait short time to ensure it hasn't resolved prematurely
    await new Promise((r) => setTimeout(r, 100));
    expect(messagesReceived.some((m) => m.commandId === 'cmd-wait-2')).toBe(false);

    // Update state to "loaded"
    BridgeStore.updateStateSlotValue('App#1', 'status', 'loaded');

    // Wait for command Ack
    await new Promise<void>((resolve) => {
      const check = () => {
        const ack = messagesReceived.find((m) => m.type === 'commandAck' && m.commandId === 'cmd-wait-2');
        if (ack) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    const ack = messagesReceived.find((m) => m.type === 'commandAck' && m.commandId === 'cmd-wait-2');
    expect(ack.success).toBe(true);
  });

  it('supports truthy, falsy, and changed operators', async () => {
    // Register another component state slot
    BridgeStore.registerComponent('App#1', {
      displayName: 'App',
      fiberRef: null,
      domRef: null,
      stateSlots: [
        { key: 'loading', value: true, setter: () => {}, hookIndex: 0 },
        { key: 'count', value: 10, setter: () => {}, hookIndex: 1 }
      ],
      mountedAt: Date.now(),
      route: '/'
    });

    messagesReceived.length = 0;

    // 1. Wait for loading to become falsy
    serverSocket.send(JSON.stringify({
      type: 'waitFor',
      commandId: 'cmd-wait-falsy',
      target: 'App#1.loading',
      condition: { operator: 'falsy' }
    }));

    // 2. Wait for count to change
    serverSocket.send(JSON.stringify({
      type: 'waitFor',
      commandId: 'cmd-wait-changed',
      target: 'App#1.count',
      condition: { operator: 'changed' }
    }));

    await new Promise((r) => setTimeout(r, 100));
    const hasAcks = messagesReceived.some((m) => m.commandId === 'cmd-wait-falsy' || m.commandId === 'cmd-wait-changed');
    expect(hasAcks).toBe(false);

    // Update values
    BridgeStore.updateStateSlotValue('App#1', 'loading', false);
    BridgeStore.updateStateSlotValue('App#1', 'count', 11);

    // Wait for both acks
    await new Promise<void>((resolve) => {
      const check = () => {
        const ackFalsy = messagesReceived.find((m) => m.commandId === 'cmd-wait-falsy');
        const ackChanged = messagesReceived.find((m) => m.commandId === 'cmd-wait-changed');
        if (ackFalsy && ackChanged) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    const ackFalsy = messagesReceived.find((m) => m.commandId === 'cmd-wait-falsy');
    const ackChanged = messagesReceived.find((m) => m.commandId === 'cmd-wait-changed');
    expect(ackFalsy.success).toBe(true);
    expect(ackChanged.success).toBe(true);
  });

  it('fails with timeout error if condition is not met in time', async () => {
    messagesReceived.length = 0;

    serverSocket.send(JSON.stringify({
      type: 'waitFor',
      commandId: 'cmd-wait-timeout',
      target: 'App#1.count',
      condition: {
        operator: 'equals',
        value: 100
      },
      timeoutMs: 150
    }));

    // Wait for the timeout
    await new Promise<void>((resolve) => {
      const check = () => {
        const ack = messagesReceived.find((m) => m.commandId === 'cmd-wait-timeout');
        if (ack) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    const ack = messagesReceived.find((m) => m.commandId === 'cmd-wait-timeout');
    expect(ack.success).toBe(false);
    expect(ack.error).toContain('Timeout');
  });
});
