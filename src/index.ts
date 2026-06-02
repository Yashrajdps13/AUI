export * from './types.js';
export * from './protocol.js';
export { BridgeStore, useBridgeRegistry } from './store.js';
export { useBridgeState } from './hook.js';
export { initFiberScanner } from './scanner.js';
export { AgentWebSocketManager } from './websocket.js';

import { initFiberScanner } from './scanner.js';
initFiberScanner();

