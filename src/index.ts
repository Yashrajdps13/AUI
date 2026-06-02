export * from './types.js';
export * from './protocol.js';
export { BridgeStore, useBridgeRegistry, useIsAgentConnected } from './store.js';
export { useBridgeState, BridgeStateMetadata } from './hook.js';
export { initFiberScanner } from './scanner.js';
export { AgentWebSocketManager } from './websocket.js';

import { initFiberScanner } from './scanner.js';
initFiberScanner();

