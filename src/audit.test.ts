// @vitest-environment jsdom
import { describe, it, expect, beforeAll, afterAll, beforeEach, vi } from 'vitest';
import { WebSocketServer } from 'ws';
import WebSocket from 'ws';
import { AgentWebSocketManager } from './websocket.js';
import { BridgeStore } from './store.js';
import { ComponentEntry } from './types.js';
import { CommandAuditLogger } from './logger.js';

// Configure the manager to use the ws library WebSocket client implementation in Node
AgentWebSocketManager.WebSocketClass = WebSocket;

describe('CommandAuditLogger & queryAuditLog Command', () => {
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

    // Connect
    AgentWebSocketManager.connect(`ws://localhost:${port}`);
    
    // Wait for connection to establish
    await new Promise<void>((resolve) => {
      const check = () => {
        if (serverSocket) resolve();
        else setTimeout(check, 50);
      };
      check();
    });
  });

  afterAll(async () => {
    AgentWebSocketManager.disconnect();
    wss.close();
  });

  beforeEach(() => {
    CommandAuditLogger.clear();
    BridgeStore.clear();
    messagesReceived.length = 0;
  });

  it('should log a successful setState command and redact sensitive state values', async () => {
    const mockEmailSetter = vi.fn();
    const mockPassSetter = vi.fn();

    const dummyComponent: Omit<ComponentEntry, 'id'> = {
      displayName: 'AuthForm',
      fiberRef: null,
      domRef: null,
      stateSlots: [
        { key: 'email', value: 'user@example.com', setter: mockEmailSetter, hookIndex: 0 },
        { key: 'password', value: 'secret123', setter: mockPassSetter, hookIndex: 1, sensitive: true }
      ],
      mountedAt: Date.now(),
      route: '/'
    };
    BridgeStore.registerComponent('AuthForm#1', dummyComponent);

    // 1. setState on non-sensitive state
    serverSocket.send(JSON.stringify({
      type: 'setState',
      commandId: 'cmd-set-email',
      target: 'AuthForm#1.email',
      value: 'new@example.com'
    }));

    await new Promise<void>((resolve) => {
      const check = () => {
        const ack = messagesReceived.find((m) => m.type === 'commandAck' && m.commandId === 'cmd-set-email');
        if (ack) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    expect(mockEmailSetter).toHaveBeenCalledWith('new@example.com');
    let auditLog = CommandAuditLogger.getAuditLog();
    expect(auditLog.length).toBe(1);
    expect(auditLog[0]).toMatchObject({
      commandId: 'cmd-set-email',
      type: 'setState',
      target: 'AuthForm#1.email',
      value: 'new@example.com',
      success: true
    });

    // 2. setState on sensitive state (should be redacted)
    serverSocket.send(JSON.stringify({
      type: 'setState',
      commandId: 'cmd-set-pass',
      target: 'AuthForm#1.password',
      value: 'super_secret'
    }));

    await new Promise<void>((resolve) => {
      const check = () => {
        const ack = messagesReceived.find((m) => m.type === 'commandAck' && m.commandId === 'cmd-set-pass');
        if (ack) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    expect(mockPassSetter).toHaveBeenCalledWith('super_secret');
    auditLog = CommandAuditLogger.getAuditLog();
    expect(auditLog.length).toBe(2);
    expect(auditLog[1]).toMatchObject({
      commandId: 'cmd-set-pass',
      type: 'setState',
      target: 'AuthForm#1.password',
      value: '[REDACTED]',
      success: true
    });
  });

  it('should log a failed setState command (invalid target or syntax)', async () => {
    // 1. Invalid target format
    serverSocket.send(JSON.stringify({
      type: 'setState',
      commandId: 'cmd-set-invalid-format',
      target: 'AuthForm#1',
      value: 'new@example.com'
    }));

    await new Promise<void>((resolve) => {
      const check = () => {
        const ack = messagesReceived.find((m) => m.type === 'commandAck' && m.commandId === 'cmd-set-invalid-format');
        if (ack) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    let auditLog = CommandAuditLogger.getAuditLog();
    expect(auditLog.length).toBe(1);
    expect(auditLog[0]).toMatchObject({
      commandId: 'cmd-set-invalid-format',
      type: 'setState',
      target: 'AuthForm#1',
      value: 'new@example.com',
      success: false
    });
    expect(auditLog[0].error).toContain('Invalid target path format');

    // 2. Target state not found
    const dummyComponent: Omit<ComponentEntry, 'id'> = {
      displayName: 'AuthForm',
      fiberRef: null,
      domRef: null,
      stateSlots: [],
      mountedAt: Date.now(),
      route: '/'
    };
    BridgeStore.registerComponent('AuthForm#1', dummyComponent);

    serverSocket.send(JSON.stringify({
      type: 'setState',
      commandId: 'cmd-set-not-found',
      target: 'AuthForm#1.email',
      value: 'new@example.com'
    }));

    await new Promise<void>((resolve) => {
      const check = () => {
        const ack = messagesReceived.find((m) => m.type === 'commandAck' && m.commandId === 'cmd-set-not-found');
        if (ack) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    auditLog = CommandAuditLogger.getAuditLog();
    expect(auditLog.length).toBe(2);
    expect(auditLog[1]).toMatchObject({
      commandId: 'cmd-set-not-found',
      type: 'setState',
      target: 'AuthForm#1.email',
      value: 'new@example.com',
      success: false
    });
    expect(auditLog[1].error).toContain('not found');
  });

  it('should log dispatchEvent commands and redact sensitive target elements', async () => {
    const container = document.createElement('div');
    const normalInput = document.createElement('input');
    normalInput.id = 'normal-input';
    const passInput = document.createElement('input');
    passInput.type = 'password';
    passInput.id = 'password-input';

    container.appendChild(normalInput);
    container.appendChild(passInput);
    document.body.appendChild(container);

    const dummyComponent: Omit<ComponentEntry, 'id'> = {
      displayName: 'Form',
      fiberRef: null,
      domRef: container,
      stateSlots: [],
      mountedAt: Date.now(),
      route: '/'
    };
    BridgeStore.registerComponent('Form#1', dummyComponent);

    // 1. dispatchEvent on non-sensitive input
    serverSocket.send(JSON.stringify({
      type: 'dispatchEvent',
      commandId: 'cmd-dispatch-normal',
      target: 'Form#1',
      event: 'change',
      payload: { selector: '#normal-input', value: 'hello' }
    }));

    await new Promise<void>((resolve) => {
      const check = () => {
        const ack = messagesReceived.find((m) => m.type === 'commandAck' && m.commandId === 'cmd-dispatch-normal');
        if (ack) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    let auditLog = CommandAuditLogger.getAuditLog();
    expect(auditLog.length).toBe(1);
    expect(auditLog[0]).toMatchObject({
      commandId: 'cmd-dispatch-normal',
      type: 'dispatchEvent',
      target: 'Form#1.change',
      value: { selector: '#normal-input', value: 'hello' },
      success: true
    });

    // 2. dispatchEvent on sensitive (password) input
    serverSocket.send(JSON.stringify({
      type: 'dispatchEvent',
      commandId: 'cmd-dispatch-sensitive',
      target: 'Form#1',
      event: 'change',
      payload: { selector: '#password-input', value: 'my_password' }
    }));

    await new Promise<void>((resolve) => {
      const check = () => {
        const ack = messagesReceived.find((m) => m.type === 'commandAck' && m.commandId === 'cmd-dispatch-sensitive');
        if (ack) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    auditLog = CommandAuditLogger.getAuditLog();
    expect(auditLog.length).toBe(2);
    expect(auditLog[1]).toMatchObject({
      commandId: 'cmd-dispatch-sensitive',
      type: 'dispatchEvent',
      target: 'Form#1.change',
      value: '[REDACTED]',
      success: true
    });

    document.body.removeChild(container);
  });

  it('should log callAction commands and handle both sync and async actions (resolving / rejecting)', async () => {
    const mockSyncAction = vi.fn().mockReturnValue('sync-result');
    
    // An async action that resolves
    const mockAsyncResolve = vi.fn().mockImplementation(() => {
      return new Promise<string>((resolve) => setTimeout(() => resolve('resolved-val'), 100));
    });

    // An async action that rejects
    const mockAsyncReject = vi.fn().mockImplementation(() => {
      return new Promise<string>((_, reject) => setTimeout(() => reject(new Error('async-error')), 100));
    });

    const dummyStore: Omit<ComponentEntry, 'id'> = {
      displayName: 'ZustandStore#Auth',
      fiberRef: null,
      domRef: null,
      stateSlots: [
        { key: 'token', value: 't1', setter: () => {}, hookIndex: 0, sensitive: true }
      ],
      mountedAt: Date.now(),
      route: '/',
      actions: {
        syncAction: mockSyncAction,
        asyncResolve: mockAsyncResolve,
        asyncReject: mockAsyncReject
      }
    };
    BridgeStore.registerComponent('ZustandStore#Auth', dummyStore);

    // 1. Call sync action
    serverSocket.send(JSON.stringify({
      type: 'callAction',
      commandId: 'cmd-action-sync',
      target: 'Auth.syncAction',
      args: ['arg1', 123]
    }));

    await new Promise<void>((resolve) => {
      const check = () => {
        const ack = messagesReceived.find((m) => m.type === 'commandAck' && m.commandId === 'cmd-action-sync');
        if (ack) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    expect(mockSyncAction).toHaveBeenCalledWith('arg1', 123);
    let auditLog = CommandAuditLogger.getAuditLog();
    expect(auditLog.length).toBe(1);
    expect(auditLog[0]).toMatchObject({
      commandId: 'cmd-action-sync',
      type: 'callAction',
      target: 'Auth.syncAction',
      value: ['arg1', 123],
      success: true
    });

    // 2. Call async resolve action
    serverSocket.send(JSON.stringify({
      type: 'callAction',
      commandId: 'cmd-action-async-resolve',
      target: 'Auth.asyncResolve',
      args: []
    }));

    await new Promise<void>((resolve) => {
      const check = () => {
        const ack = messagesReceived.find((m) => m.type === 'commandAck' && m.commandId === 'cmd-action-async-resolve' && m.success === true);
        if (ack) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    auditLog = CommandAuditLogger.getAuditLog();
    expect(auditLog.length).toBe(2);
    expect(auditLog[1]).toMatchObject({
      commandId: 'cmd-action-async-resolve',
      type: 'callAction',
      target: 'Auth.asyncResolve',
      value: [],
      success: true
    });

    // 3. Call async reject action
    serverSocket.send(JSON.stringify({
      type: 'callAction',
      commandId: 'cmd-action-async-reject',
      target: 'Auth.asyncReject',
      args: []
    }));

    await new Promise<void>((resolve) => {
      const check = () => {
        const ack = messagesReceived.find((m) => m.type === 'commandAck' && m.commandId === 'cmd-action-async-reject' && m.success === false);
        if (ack) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    auditLog = CommandAuditLogger.getAuditLog();
    expect(auditLog.length).toBe(3);
    expect(auditLog[2]).toMatchObject({
      commandId: 'cmd-action-async-reject',
      type: 'callAction',
      target: 'Auth.asyncReject',
      value: [],
      success: false
    });
    expect(auditLog[2].error).toContain('async-error');

    // 4. Call action with sensitive name/args (should be redacted)
    serverSocket.send(JSON.stringify({
      type: 'callAction',
      commandId: 'cmd-action-sensitive',
      target: 'Auth.login', // has sensitive word login
      args: ['admin', 'super_secret']
    }));

    // Register login action first to make it call
    dummyStore.actions!.login = vi.fn();
    BridgeStore.registerComponent('ZustandStore#Auth', dummyStore);

    await new Promise<void>((resolve) => {
      const check = () => {
        const ack = messagesReceived.find((m) => m.type === 'commandAck' && m.commandId === 'cmd-action-sensitive');
        if (ack) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    auditLog = CommandAuditLogger.getAuditLog();
    expect(auditLog.length).toBe(4);
    expect(auditLog[3]).toMatchObject({
      commandId: 'cmd-action-sensitive',
      type: 'callAction',
      target: 'Auth.login',
      value: '[REDACTED]',
      success: true
    });
  });

  it('should clear command audit log explicitly and grow indefinitely (not circular)', () => {
    // Audit log should not be circular
    for (let i = 0; i < 30; i++) {
      CommandAuditLogger.addEntry({
        commandId: `cmd-${i}`,
        type: 'setState',
        target: 'Comp.val',
        value: i,
        success: true,
        timestamp: Date.now()
      });
    }

    expect(CommandAuditLogger.getAuditLog().length).toBe(30);

    CommandAuditLogger.clear();
    expect(CommandAuditLogger.getAuditLog().length).toBe(0);
  });

  it('should allow querying the audit log snapshot via queryAuditLog command', async () => {
    CommandAuditLogger.addEntry({
      commandId: 'cmd-custom-1',
      type: 'setState',
      target: 'Counter.value',
      value: 10,
      success: true,
      timestamp: Date.now()
    });

    serverSocket.send(JSON.stringify({
      type: 'queryAuditLog',
      commandId: 'cmd-query-audit'
    }));

    await new Promise<void>((resolve) => {
      const check = () => {
        const snapshot = messagesReceived.find((m) => m.type === 'auditLogSnapshot' && m.commandId === 'cmd-query-audit');
        if (snapshot) resolve();
        else setTimeout(check, 50);
      };
      check();
    });

    const snapshot = messagesReceived.find((m) => m.type === 'auditLogSnapshot' && m.commandId === 'cmd-query-audit');
    expect(snapshot).toBeDefined();
    expect(snapshot.auditLog.length).toBe(1);
    expect(snapshot.auditLog[0]).toMatchObject({
      commandId: 'cmd-custom-1',
      type: 'setState',
      target: 'Counter.value',
      value: 10,
      success: true
    });
  });
});
