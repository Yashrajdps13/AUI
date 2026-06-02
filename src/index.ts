export * from './types.js';
export * from './protocol.js';
export { BridgeStore, useBridgeRegistry, useIsAgentConnected } from './store.js';
export { useBridgeState, BridgeStateMetadata } from './hook.js';
export { initFiberScanner } from './scanner.js';
export { AgentWebSocketManager } from './websocket.js';
export { AgentLogger } from './logger.js';

import { initFiberScanner } from './scanner.js';
import { AgentLogger } from './logger.js';

initFiberScanner();
AgentLogger.init();

