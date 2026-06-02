/**
 * Serialized representation of a single useState state hook slot.
 * Strips out the actual React dispatcher and live value (values are queried/subscribed on-demand).
 */
export interface SerializedStateSlot {
  key: string;
  hookIndex: number;
  description?: string;
}

/**
 * Serialized representation of a component.
 * Strips out the internal FiberNode, Host HTML DOM node, and Dispatcher function references.
 */
export interface SerializedComponentEntry {
  id: string;
  displayName: string;
  mountedAt: number;
  route: string | null;
  stateSlots: SerializedStateSlot[];
  interactiveElements?: {
    selector: string;
    tagName: string;
    text?: string;
    id?: string;
    placeholder?: string;
    disabled?: boolean;
    visible?: boolean;
  }[];
}

/**
 * Commands received from the Agent (Agent -> Bridge).
 */
export type AgentCommand =
  | { type: 'setState'; commandId: string; target: string; value: unknown }
  | { type: 'dispatchEvent'; commandId: string; target: string; event: 'click' | 'change' | 'focus'; payload?: unknown }
  | { type: 'queryState'; commandId: string; target: string }
  | { type: 'getRegistry'; commandId: string }
  | { type: 'subscribe'; commandId: string; target: string }
  | { type: 'unsubscribe'; commandId: string; target: string };

/**
 * Messages sent to the Agent (Bridge -> Agent).
 */
export type BridgeMessage =
  | { type: 'registryDelta'; added: SerializedComponentEntry[]; removed: string[]; updated: SerializedComponentEntry[] }
  | { type: 'stateSnapshot'; target: string; value: unknown }
  | { type: 'commandAck'; commandId: string; success: boolean; error?: string }
  | { type: 'renderSettled'; target: string };
