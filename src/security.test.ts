// @vitest-environment jsdom
import { describe, it, expect, beforeAll, afterAll, beforeEach, vi } from 'vitest';
import { WebSocketServer } from 'ws';
import WebSocket from 'ws';
import { AgentWebSocketManager } from './websocket.js';
import { BridgeStore } from './store.js';
import { AgentLogger } from './logger.js';

AgentWebSocketManager.WebSocketClass = WebSocket;

describe('Write-Side Security Scoping', () => {
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

  beforeEach(() => {
    AgentWebSocketManager.disconnect();
    BridgeStore.clear();
    AgentLogger.clear();
    messagesReceived.length = 0;
    serverSocket = null;
  });

  it('allows mutations on components in allowedTargets, but blocks others', async () => {
    // 1. Register allowed and restricted components
    BridgeStore.registerComponent('App#1', {
      displayName: 'App',
      fiberRef: null,
      domRef: null,
      stateSlots: [
        { key: 'notes', value: '', setter: () => {}, hookIndex: 0 }
      ],
      mountedAt: Date.now(),
      route: '/'
    });

    BridgeStore.registerComponent('AdminPanel#2', {
      displayName: 'AdminPanel',
      fiberRef: null,
      domRef: null,
      stateSlots: [
        { key: 'escalate', value: false, setter: () => {}, hookIndex: 0 }
      ],
      mountedAt: Date.now(),
      route: '/'
    });

    // Connect with allowedTargets scope
    AgentWebSocketManager.connect(`ws://localhost:${port}`, {
      writeScope: {
        allowedTargets: ['App']
      }
    });

    await new Promise<void>((resolve) => {
      const check = () => {
        if (serverSocket && serverSocket.readyState === 1) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    // Try allowed target
    serverSocket.send(JSON.stringify({
      type: 'setState',
      commandId: 'cmd-allow-state',
      target: 'App#1.notes',
      value: 'Hello World'
    }));

    // Try blocked target
    serverSocket.send(JSON.stringify({
      type: 'setState',
      commandId: 'cmd-block-state',
      target: 'AdminPanel#2.escalate',
      value: true
    }));

    // Wait for both command acks
    await new Promise<void>((resolve) => {
      const check = () => {
        const hasAllowAck = messagesReceived.some((m) => m.commandId === 'cmd-allow-state');
        const hasBlockAck = messagesReceived.some((m) => m.commandId === 'cmd-block-state');
        if (hasAllowAck && hasBlockAck) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    const allowAck = messagesReceived.find((m) => m.commandId === 'cmd-allow-state');
    const blockAck = messagesReceived.find((m) => m.commandId === 'cmd-block-state');

    expect(allowAck.success).toBe(true);
    expect(blockAck.success).toBe(false);
    expect(blockAck.error).toContain('is not allowed under the current security scope');

    // Verify warning exists in the logger ledger
    const ledger = AgentLogger.getLedger();
    const blockedLog = ledger.find((log) => log.type === 'warn' && log.message.includes('Blocked setState'));
    expect(blockedLog).toBeDefined();
  });

  it('allows actions in allowedActions, but blocks others', async () => {
    const actionSpy = vi.fn();
    BridgeStore.registerComponent('ZustandStore#UserStore', {
      displayName: 'ZustandStore#UserStore',
      fiberRef: null,
      domRef: null,
      stateSlots: [],
      mountedAt: Date.now(),
      route: '/',
      actions: {
        login: actionSpy,
        escalate: actionSpy
      }
    });

    AgentWebSocketManager.connect(`ws://localhost:${port}`, {
      writeScope: {
        allowedActions: ['UserStore.login']
      }
    });

    await new Promise<void>((resolve) => {
      const check = () => {
        if (serverSocket && serverSocket.readyState === 1) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    // Try allowed action
    serverSocket.send(JSON.stringify({
      type: 'callAction',
      commandId: 'cmd-allow-action',
      target: 'UserStore.login',
      args: []
    }));

    // Try blocked action
    serverSocket.send(JSON.stringify({
      type: 'callAction',
      commandId: 'cmd-block-action',
      target: 'UserStore.escalate',
      args: []
    }));

    await new Promise<void>((resolve) => {
      const check = () => {
        const hasAllow = messagesReceived.some((m) => m.commandId === 'cmd-allow-action');
        const hasBlock = messagesReceived.some((m) => m.commandId === 'cmd-block-action');
        if (hasAllow && hasBlock) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    const allowAck = messagesReceived.find((m) => m.commandId === 'cmd-allow-action');
    const blockAck = messagesReceived.find((m) => m.commandId === 'cmd-block-action');

    expect(allowAck.success).toBe(true);
    expect(blockAck.success).toBe(false);
    expect(blockAck.error).toContain('is not allowed under the current security scope');
  });

  it('blocks writes on routes not included in allowedRoutes', async () => {
    BridgeStore.registerComponent('App#1', {
      displayName: 'App',
      fiberRef: null,
      domRef: null,
      stateSlots: [
        { key: 'notes', value: '', setter: () => {}, hookIndex: 0 }
      ],
      mountedAt: Date.now(),
      route: '/checkout'
    });

    AgentWebSocketManager.connect(`ws://localhost:${port}`, {
      writeScope: {
        allowedRoutes: ['/profile']
      }
    });

    await new Promise<void>((resolve) => {
      const check = () => {
        if (serverSocket && serverSocket.readyState === 1) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    // Set route in window.location manually
    delete (window as any).location;
    window.location = { pathname: '/checkout' } as any;

    // Try write on blocked route
    serverSocket.send(JSON.stringify({
      type: 'setState',
      commandId: 'cmd-block-route',
      target: 'App#1.notes',
      value: 'Hi'
    }));

    await new Promise<void>((resolve) => {
      const check = () => {
        const ack = messagesReceived.find((m) => m.commandId === 'cmd-block-route');
        if (ack) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    const ack = messagesReceived.find((m) => m.commandId === 'cmd-block-route');
    expect(ack.success).toBe(false);
    expect(ack.error).toContain('route "/checkout" is not allowed');
  });
});
