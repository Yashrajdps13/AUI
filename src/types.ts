/**
 * Represents a single React Fiber Node.
 * React internals are version-sensitive. We define a loose structure to capture key fiber properties.
 */
export interface FiberNode {
  tag: number;
  type: any;
  key: string | number | null;
  child: FiberNode | null;
  sibling: FiberNode | null;
  return: FiberNode | null;
  memoizedState: any;
  memoizedProps: any;
  stateNode: any;
  [key: string]: any;
}

/**
 * Represents a single useState state hook slot in a component.
 */
export interface StateSlot {
  key: string;           // Key/name assigned to the state, e.g. "quantity"
  value: unknown;        // The current memoizedState value
  setter: Function;      // The actual React dispatcher/setter reference
  hookIndex: number;     // Index/position in the component's hook linked list
  description?: string;  // Optional developer-provided description of the state
  sensitive?: boolean;   // Optional flag indicating if the state contains sensitive data / PII
}

/**
 * Registry entry representing a mounted component.
 */
export interface ComponentEntry {
  id: string;                     // Stable ID: e.g. "CheckoutForm#3" (component name + tree position/index)
  displayName: string;            // The component's display name, preserved at build time
  fiberRef: FiberNode | null;            // Live reference to the component's Fiber node
  domRef: HTMLElement | null;     // Reference to the host DOM element if applicable
  stateSlots: StateSlot[];        // Linked hook state slots
  mountedAt: number;              // Timestamp when first mounted/registered
  route: string | null;           // Scoped route or URL path where mounted
}

/**
 * The runtime registry storing components by their stable IDs.
 */
export type BridgeRegistry = Map<string, ComponentEntry>;
