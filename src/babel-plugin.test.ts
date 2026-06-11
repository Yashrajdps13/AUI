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
      'use client';
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
      'use client';
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
      'use client';
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
      'use client';
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
      'use client';
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
      'use client';
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
      'use client';
      import { useState } from 'react';
      function Counter() {
        console.log(useState(0));
        return null;
      }
    `;
    const output = transform(code);
    expect(output).toContain('_useBridgeState("Counter", "state_0", 0, 0)');
  });

  it('should extract JSDoc description and pass it as metadata to _useBridgeState', () => {
    const code = `
      'use client';
      import { useState } from 'react';
      function MyComponent() {
        /** The current count of clicks */
        const [count, setCount] = useState(0);
        return null;
      }
    `;
    const output = transform(code);
    expect(output).toContain('_useBridgeState("MyComponent", "count", 0, 0, {');
    expect(output).toContain('description: "The current count of clicks"');
  });

  it('should parse @description or @desc tags inside JSDoc comment', () => {
    const code = `
      'use client';
      import { useState } from 'react';
      function Profile() {
        /**
         * @desc The username of the user
         * @default 'guest'
         */
        const [username, setUsername] = useState();
        return null;
      }
    `;
    const output = transform(code);
    expect(output).toContain('_useBridgeState("Profile", "username", 0, undefined, {');
    expect(output).toContain('description: "The username of the user"');
  });

  it('should parse @sensitive or @private tags to inject sensitive: true metadata', () => {
    const code1 = `
      'use client';
      import { useState } from 'react';
      function Profile() {
        /**
         * The password of the user
         * @sensitive
         */
        const [password, setPassword] = useState('secret');
        return null;
      }
    `;
    const output1 = transform(code1);
    expect(output1).toContain('_useBridgeState("Profile", "password", 0');
    expect(output1).toContain('description: "The password of the user"');
    expect(output1).toContain('sensitive: true');

    const code2 = `
      'use client';
      import { useState } from 'react';
      function MyCard() {
        /** @private */
        const [cardNumber, setCardNumber] = useState('');
        return null;
      }
    `;
    const output2 = transform(code2);
    expect(output2).toContain('_useBridgeState("MyCard", "cardNumber", 0');
    expect(output2).toContain('sensitive: true');
  });

  it('should auto-inject react-agent-bridge preflight import when react-dom is imported', () => {
    const code = `
      'use client';
      import React from 'react';
      import ReactDOM from 'react-dom/client';
      import App from './App';
    `;
    const output = transform(code);
    expect(output).toContain('import "react-agent-bridge";');
  });

  it('should skip files without "use client" directive (Next.js Server Components)', () => {
    const code = `
      import { useState } from 'react';
      function ServerComponent() {
        const [count, setCount] = useState(0);
        return null;
      }
    `;
    const output = transform(code);
    // Plugin must skip the file — no transformation, no injected imports
    expect(output).not.toContain('_useBridgeState');
    expect(output).not.toContain('react-agent-bridge');
  });

  it('should skip files with "use server" directive', () => {
    const code = `
      'use server';
      import { useState } from 'react';
      function ServerAction() {
        const [count, setCount] = useState(0);
        return null;
      }
    `;
    const output = transform(code);
    // 'use server' is not 'use client' — must be skipped
    expect(output).not.toContain('_useBridgeState');
    expect(output).not.toContain('react-agent-bridge');
  });
});
