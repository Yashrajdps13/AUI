import { BridgeStore } from './store.js';
import { StateSlot } from './types.js';

interface RegisterContextOptions {
  pollIntervalMs?: number;
  sensitive?: boolean;
}

const customContextsMap = new Map<string, {
  getter: () => any;
  pollIntervalMs: number;
  sensitive: boolean;
  lastValue: any;
  timer: any;
}>();

/**
 * Calculates current URL context values.
 */
function getUrlContextValues() {
  if (typeof window === 'undefined') {
    return {
      pathname: '',
      href: '',
      search: '',
      queryParams: {},
      hash: '',
    };
  }

  const queryParams: Record<string, string> = {};
  try {
    const params = new URLSearchParams(window.location.search);
    params.forEach((value, key) => {
      queryParams[key] = value;
    });
  } catch (e) {
    // ignore
  }

  return {
    pathname: window.location.pathname,
    href: window.location.href,
    search: window.location.search,
    queryParams,
    hash: window.location.hash,
  };
}

/**
 * Updates the mandatory URL context entry in BridgeStore.
 */
export function updateUrlContext(): void {
  if (typeof window === 'undefined') return;

  const newValues = getUrlContextValues();
  
  // Update slot values in BridgeStore
  BridgeStore.updateStateSlotValue('__context__#env', 'pathname', newValues.pathname);
  BridgeStore.updateStateSlotValue('__context__#env', 'href', newValues.href);
  BridgeStore.updateStateSlotValue('__context__#env', 'search', newValues.search);
  BridgeStore.updateStateSlotValue('__context__#env', 'queryParams', newValues.queryParams);
  BridgeStore.updateStateSlotValue('__context__#env', 'hash', newValues.hash);

  // Keep route synced
  const existing = BridgeStore.getSnapshot().get('__context__#env');
  if (existing) {
    BridgeStore.registerComponent('__context__#env', {
      ...existing,
      route: newValues.pathname,
    });
  }
}

/**
 * Initializes the mandatory URL context.
 */
export function initUrlContext(): void {
  if (typeof window === 'undefined') return;

  const initialValues = getUrlContextValues();

  const slots: StateSlot[] = [
    {
      key: 'pathname',
      value: initialValues.pathname,
      setter: () => {},
      hookIndex: 0,
    },
    {
      key: 'href',
      value: initialValues.href,
      setter: () => {},
      hookIndex: 1,
    },
    {
      key: 'search',
      value: initialValues.search,
      setter: () => {},
      hookIndex: 2,
    },
    {
      key: 'queryParams',
      value: initialValues.queryParams,
      setter: () => {},
      hookIndex: 3,
    },
    {
      key: 'hash',
      value: initialValues.hash,
      setter: () => {},
      hookIndex: 4,
    },
  ];

  BridgeStore.registerComponent('__context__#env', {
    displayName: 'BrowserContext',
    fiberRef: null,
    domRef: null,
    stateSlots: slots,
    mountedAt: Date.now(),
    route: initialValues.pathname,
  });

  // Listen for history / navigation changes
  window.addEventListener('popstate', updateUrlContext);

  const origPushState = window.history.pushState;
  window.history.pushState = function (...args) {
    const res = origPushState.apply(this, args);
    updateUrlContext();
    return res;
  };

  const origReplaceState = window.history.replaceState;
  window.history.replaceState = function (...args) {
    const res = origReplaceState.apply(this, args);
    updateUrlContext();
    return res;
  };
}

/**
 * Registers custom developer-defined context.
 */
export function registerContext(
  name: string,
  getter: () => any,
  options?: RegisterContextOptions
): void {
  if (typeof window === 'undefined') return;

  const pollIntervalMs = options?.pollIntervalMs ?? 1000;
  const sensitive = options?.sensitive ?? false;

  // Calculate initial value
  let initialValue: any;
  try {
    initialValue = getter();
  } catch (e) {
    initialValue = undefined;
  }

  // Clear existing context slot registration with same name if any
  if (customContextsMap.has(name)) {
    const existing = customContextsMap.get(name)!;
    clearInterval(existing.timer);
    customContextsMap.delete(name);
  }

  // Set up polling
  const runPoll = () => {
    let currentVal: any;
    try {
      currentVal = getter();
    } catch (e) {
      currentVal = undefined;
    }
    const record = customContextsMap.get(name);
    if (!record) return;

    if (JSON.stringify(record.lastValue) !== JSON.stringify(currentVal)) {
      record.lastValue = currentVal;
      BridgeStore.updateStateSlotValue('__context__#custom', name, currentVal);
    }
  };

  const timer = setInterval(runPoll, pollIntervalMs);

  customContextsMap.set(name, {
    getter,
    pollIntervalMs,
    sensitive,
    lastValue: initialValue,
    timer,
  });

  // Re-register AppContext with all current slots
  const registry = BridgeStore.getSnapshot();
  const existingEntry = registry.get('__context__#custom');

  const slots: StateSlot[] = Array.from(customContextsMap.entries()).map(([key, val], idx) => {
    return {
      key,
      value: val.lastValue,
      setter: () => {},
      hookIndex: idx,
      sensitive: val.sensitive,
    };
  });

  BridgeStore.registerComponent('__context__#custom', {
    displayName: 'AppContext',
    fiberRef: null,
    domRef: null,
    stateSlots: slots,
    mountedAt: existingEntry ? existingEntry.mountedAt : Date.now(),
    route: window.location.pathname,
  });
}
