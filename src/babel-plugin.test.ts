import { describe, it, expect } from 'vitest';
import { transformSync } from '@babel/core';
import reactAgentBridgeBabelPlugin from './babel-plugin.js';

function transform(code: string, filename?: string): string {
  const result = transformSync(code, {
    filename,
    plugins: [reactAgentBridgeBabelPlugin],
    babelrc: false,
    configFile: false,
  });
  return result?.code || '';
}

describe('Babel Plugin', () => {
  it('should transform direct useState call and inject helper import', () => {
    const code = `
      import { useState } from 'react';
      function MyComponent() {
        const [count, setCount] = useState(0);
        return null;
      }
    `;
    const output = transform(code);
    expect(output).toContain('import { useBridgeState as _useBridgeState } from "react-agent-bridge";');
    expect(output).toContain('_useBridgeState("MyComponent", "count", 0, 0)');
  });

  it('should transform React.useState call', () => {
    const code = `
      import React from 'react';
      function MyComponent() {
        const [text, setText] = React.useState("hello");
        return null;
      }
    `;
    const output = transform(code);
    expect(output).toContain('import { useBridgeState as _useBridgeState } from "react-agent-bridge";');
    expect(output).toContain('_useBridgeState("MyComponent", "text", 0, "hello")');
  });

  it('should count multiple hooks correctly within same component', () => {
    const code = `
      import { useState } from 'react';
      function Dashboard() {
        const [user, setUser] = useState(null);
        const [loading, setLoading] = useState(true);
        const [error, setError] = useState(undefined);
        return null;
      }
    `;
    const output = transform(code);
    expect(output).toContain('_useBridgeState("Dashboard", "user", 0, null)');
    expect(output).toContain('_useBridgeState("Dashboard", "loading", 1, true)');
    expect(output).toContain('_useBridgeState("Dashboard", "error", 2, undefined)');
  });

  it('should resolve component name from arrow function variable declaration', () => {
    const code = `
      import { useState } from 'react';
      const ArrowCounter = () => {
        const [count, setCount] = useState(0);
        return null;
      };
    `;
    const output = transform(code);
    expect(output).toContain('_useBridgeState("ArrowCounter", "count", 0, 0)');
  });

  it('should resolve component name from default anonymous export using filename', () => {
    const code = `
      import { useState } from 'react';
      export default function() {
        const [items, setItems] = useState([]);
        return null;
      }
    `;
    const output = transform(code, '/path/to/my-custom-view.tsx');
    expect(output).toContain('_useBridgeState("My-custom-view", "items", 0, [])');
  });

  it('should generate fallback state keys if destructuring is not used', () => {
    const code = `
      import { useState } from 'react';
      function Counter() {
        const stateArray = useState(0);
        return null;
      }
    `;
    const output = transform(code);
    expect(output).toContain('_useBridgeState("Counter", "stateArray", 0, 0)');
  });

  it('should fallback to state_index if not assigned directly to variable', () => {
    const code = `
      import { useState } from 'react';
      function Counter() {
        console.log(useState(0));
        return null;
      }
    `;
    const output = transform(code);
    expect(output).toContain('_useBridgeState("Counter", "state_0", 0, 0)');
  });

  it('should auto-inject react-agent-bridge preflight import when react-dom is imported', () => {
    const code = `
      import React from 'react';
      import ReactDOM from 'react-dom/client';
      import App from './App';
    `;
    const output = transform(code);
    expect(output).toContain('import "react-agent-bridge";');
  });
});
