import { BridgeStore } from './store.js';
import { AgentWebSocketManager } from './websocket.js';

/**
 * Traverses up the type structure of a Fiber node to resolve its readable name.
 */
export function getFiberName(fiber: any): string {
  const type = fiber.type;
  if (!type) return 'Unknown';
  if (typeof type === 'string') return type; // standard HTML tag
  if (typeof type === 'function') {
    return type.displayName || type.name || 'Anonymous';
  }
  // Handle React memo, forwardRef, providers, etc.
  if (type.$$typeof) {
    if (type.type) {
      return getFiberName({ type: type.type });
    }
    if (typeof type.$$typeof === 'symbol') {
      return type.$$typeof.description || 'Special';
    }
    return 'Special';
  }
  return 'Unknown';
}

const USE_ID_PATTERN = /^[:_]r[\w-]*[:_]$/;

/**
 * Searches a component's hook list (memoizedState) for a useId generated value.
 */
export function extractInstanceId(fiber: any): string | null {
  let hook = fiber.memoizedState;
  while (hook) {
    const val = hook.memoizedState;
    if (typeof val === 'string' && USE_ID_PATTERN.test(val)) {
      return val.replace(/:/g, '');
    }
    // Fallback: search within arrays if the structure differs
    if (Array.isArray(val)) {
      for (const item of val) {
        if (typeof item === 'string' && USE_ID_PATTERN.test(item)) {
          return item.replace(/:/g, '');
        }
      }
    }
    hook = hook.next;
  }
  return null;
}

/**
 * Depth-first search to find the first descendant Host HTML Element.
 */
export function findDomNode(fiber: any): HTMLElement | null {
  if (!fiber) return null;
  if (fiber.stateNode instanceof HTMLElement) {
    return fiber.stateNode;
  }
  let child = fiber.child;
  while (child) {
    const dom = findDomNode(child);
    if (dom) return dom;
    child = child.sibling;
  }
  return null;
}

/**
 * Scans the active current Fiber tree and correlates it to the Bridge registry.
 */
export function scanFiberTree(rootFiber: any, route: string | null): void {
  const traverse = (fiber: any, parentPath: string) => {
    if (!fiber) return;

    const name = getFiberName(fiber);
    const key = fiber.key !== null && fiber.key !== undefined ? `:${fiber.key}` : '';
    const index = fiber.index ?? 0;
    const currentPath = `${parentPath}/${name}${key}[${index}]`;

    // Only inspect functional components
    if (typeof fiber.type === 'function') {
      const instanceId = extractInstanceId(fiber);
      if (instanceId) {
        const tempId = `${name}#${instanceId}`;
        const entry = BridgeStore.getSnapshot().get(tempId);

        if (entry) {
          const domRef = findDomNode(fiber);
          // Enrich the component entry in the store
          BridgeStore.updateFiberAndDomRef(tempId, fiber, domRef, route);
        }
      }
    }

    let child = fiber.child;
    while (child) {
      traverse(child, currentPath);
      child = child.sibling;
    }
  };

  traverse(rootFiber, '');
}

/**
 * Safely registers a renderer and wraps its onCommitFiberRoot hook.
 */
function patchRenderer(_renderer: any): void {
  const hook = (window as any).__REACT_DEVTOOLS_GLOBAL_HOOK__;
  if (!hook) return;

  const originalOnCommitFiberRoot = hook.onCommitFiberRoot;
  hook.onCommitFiberRoot = function (rendererId: any, root: any, priorityLevel: any) {
    if (originalOnCommitFiberRoot) {
      originalOnCommitFiberRoot.call(this, rendererId, root, priorityLevel);
    }

    if (root && root.current) {
      const route = typeof window !== 'undefined' ? window.location.pathname : null;
      scanFiberTree(root.current, route);
      
      const targetId = root.containerInfo?.id || 'root';
      AgentWebSocketManager.onRenderSettled(targetId);
    }
  };
}

/**
 * Initializes the React Fiber Tree Scanner by hooking into React DevTools Global Hook.
 * SSR-safe. Must be called before React mounts.
 */
export function initFiberScanner(): void {
  if (typeof window === 'undefined') return;

  // Initialize global hook container if DevTools extension is not active
  if (!(window as any).__REACT_DEVTOOLS_GLOBAL_HOOK__) {
    (window as any).__REACT_DEVTOOLS_GLOBAL_HOOK__ = {
      renderers: new Map(),
      supportsFiber: true,
      inject: function (renderer: any) {
        const id = Math.random();
        (this.renderers as Map<any, any>).set(id, renderer);
        patchRenderer(renderer);
        return id;
      },
      onCommitFiberRoot: function () {},
      onCommitFiberUnmount: function () {},
    };
  } else {
    const hook = (window as any).__REACT_DEVTOOLS_GLOBAL_HOOK__;

    const originalInject = hook.inject;
    hook.inject = function (renderer: any) {
      const id = originalInject.call(this, renderer);
      patchRenderer(renderer);
      return id;
    };

    // If renderers are already injected (e.g. scanner initialized after React)
    if (hook.renderers) {
      for (const renderer of hook.renderers.values()) {
        patchRenderer(renderer);
      }
    }
  }
}
