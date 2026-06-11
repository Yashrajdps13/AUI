export * from './types.js';
export * from './protocol.js';
export { BridgeStore, useBridgeRegistry, useIsAgentConnected, useAgentStatus } from './store.js';
export { useBridgeState, BridgeStateMetadata } from './hook.js';
export { initFiberScanner } from './scanner.js';
export { AgentWebSocketManager, WriteSecurityScope } from './websocket.js';
export { AgentLogger, CommandAuditLogger } from './logger.js';
export { bridgeZustand, BridgeZustandOptions } from './zustand.js';
export { registerContext } from './context.js';

import { initFiberScanner } from './scanner.js';
import { AgentLogger } from './logger.js';
import { initUrlContext } from './context.js';

initFiberScanner();
AgentLogger.init();
initUrlContext();

