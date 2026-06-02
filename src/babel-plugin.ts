import { fileURLToPath } from 'url';
import { NodePath, PluginObj } from '@babel/core';
import * as t from '@babel/types';
import * as path from 'path';

// A map from component function node to the number of hook calls found inside it
const componentHookCounters = new WeakMap<t.Node, number>();

// Get library root path dynamically to detect library files
const currentFile = typeof import.meta !== 'undefined' && import.meta.url
  ? fileURLToPath(import.meta.url)
  : typeof __filename !== 'undefined'
  ? __filename
  : '';
const currentDir = currentFile ? path.dirname(currentFile) : '';
const libraryRoot = currentDir ? path.resolve(currentDir, '..') : '';

function getNextHookIndex(componentPath: NodePath<any>): number {
  const node = componentPath.node;
  const count = componentHookCounters.get(node) || 0;
  componentHookCounters.set(node, count + 1);
  return count;
}

function getComponentName(nodePath: NodePath<any>, filename: string | undefined): string {
  let currentPath: NodePath<any> | null = nodePath;
  while (currentPath) {
    if (
      currentPath.isFunctionDeclaration() ||
      currentPath.isFunctionExpression() ||
      currentPath.isArrowFunctionExpression()
    ) {
      // 1. Check FunctionDeclaration name
      if (currentPath.isFunctionDeclaration() && currentPath.node.id) {
        const name = currentPath.node.id.name;
        if (name && name[0] === name[0].toUpperCase()) {
          return name;
        }
      }

      // 2. Check variable declarator name if function is assigned to a variable
      const parent = currentPath.parentPath;
      if (parent && parent.isVariableDeclarator() && t.isIdentifier(parent.node.id)) {
        const name = parent.node.id.name;
        if (name && name[0] === name[0].toUpperCase()) {
          return name;
        }
      }

      // 3. Check if it's default export of anonymous function
      if (parent && parent.isExportDefaultDeclaration()) {
        if (filename) {
          const base = path.basename(filename, path.extname(filename));
          // Capitalize first letter
          return base[0].toUpperCase() + base.slice(1);
        }
        return 'AnonymousComponent';
      }
    }
    currentPath = currentPath.parentPath;
  }
  return 'UnknownComponent';
}

function getFunctionName(nodePath: NodePath<any>): string | null {
  if (nodePath.isFunctionDeclaration() && nodePath.node.id) {
    return nodePath.node.id.name;
  }
  const parent = nodePath.parentPath;
  if (parent && parent.isVariableDeclarator() && t.isIdentifier(parent.node.id)) {
    return parent.node.id.name;
  }
  return null;
}

interface PluginState {
  transformed: boolean;
  filename?: string;
  importsReactDOM?: boolean;
}

export default function reactAgentBridgeBabelPlugin(): PluginObj<PluginState> {
  return {
    name: 'react-agent-bridge-babel-plugin',
    visitor: {
      Program: {
        enter(programPath, state) {
          state.transformed = false;

          const filename = state.filename;
          if (filename) {
            const absolutePath = path.resolve(filename);
            const normalizedPath = absolutePath.replace(/\\/g, '/');

            // 1. Skip files in node_modules
            if (normalizedPath.includes('/node_modules/')) {
              programPath.skip();
              return;
            }

            // 2. Skip library source/dist files (any file inside libraryRoot but not in examples)
            if (libraryRoot) {
              const normalizedLibRoot = libraryRoot.replace(/\\/g, '/');
              const normalizedExamples = path.resolve(libraryRoot, 'examples').replace(/\\/g, '/');
              if (
                normalizedPath.startsWith(normalizedLibRoot) &&
                !normalizedPath.startsWith(normalizedExamples)
              ) {
                programPath.skip();
                return;
              }
            }
          }
        },
        exit(programPath, state) {
          if (state.transformed) {
            // Inject helper import at the top of the file:
            // import { useBridgeState as _useBridgeState } from 'react-agent-bridge';
            const importDecl = t.importDeclaration(
              [
                t.importSpecifier(
                  t.identifier('_useBridgeState'),
                  t.identifier('useBridgeState')
                ),
              ],
              t.stringLiteral('react-agent-bridge')
            );
            programPath.unshiftContainer('body', importDecl);
          }

          if (state.importsReactDOM) {
            // Inject `import 'react-agent-bridge';` at the top of the file
            // to ensure the fiber scanner is initialized before react-dom evaluates.
            const preflightImport = t.importDeclaration([], t.stringLiteral('react-agent-bridge'));
            programPath.unshiftContainer('body', preflightImport);
          }
        },
      },
      ImportDeclaration(importPath, state) {
        const source = importPath.node.source.value;
        if (source === 'react-dom' || source === 'react-dom/client' || source === 'react-dom/server') {
          state.importsReactDOM = true;
        }
      },
      CallExpression(callPath, state) {
        const { node } = callPath;
        let isUseState = false;

        // Detect useState(...)
        if (t.isIdentifier(node.callee, { name: 'useState' })) {
          const binding = callPath.scope.getBinding('useState');
          if (!binding) {
            isUseState = true;
          } else if (
            binding.kind === 'module' &&
            binding.path.parentPath?.isImportDeclaration() &&
            binding.path.parentPath.node.source.value === 'react'
          ) {
            isUseState = true;
          }
        }
        // Detect React.useState(...) or React.default.useState(...)
        else if (t.isMemberExpression(node.callee)) {
          const { object, property } = node.callee;
          if (t.isIdentifier(property, { name: 'useState' })) {
            if (t.isIdentifier(object, { name: 'React' })) {
              const binding = callPath.scope.getBinding('React');
              if (!binding) {
                isUseState = true;
              } else if (
                binding.kind === 'module' &&
                binding.path.parentPath?.isImportDeclaration() &&
                binding.path.parentPath.node.source.value === 'react'
              ) {
                isUseState = true;
              }
            }
          }
        }

        if (!isUseState) return;

        // Find enclosing component function path (capitalized or exported)
        let componentPath: NodePath<any> | null = callPath.findParent((p) => {
          if (
            p.isFunctionDeclaration() ||
            p.isFunctionExpression() ||
            p.isArrowFunctionExpression()
          ) {
            if (p.isFunctionDeclaration() && p.node.id) {
              const name = p.node.id.name;
              if (name && name[0] === name[0].toUpperCase()) return true;
            }
            const parent = p.parentPath;
            if (parent && parent.isVariableDeclarator() && t.isIdentifier(parent.node.id)) {
              const name = parent.node.id.name;
              if (name && name[0] === name[0].toUpperCase()) return true;
            }
            if (parent && parent.isExportDefaultDeclaration()) {
              return true;
            }
          }
          return false;
        });

        // Fallback to the closest function if no capitalized function is found
        if (!componentPath) {
          componentPath = callPath.findParent(
            (p) =>
              p.isFunctionDeclaration() ||
              p.isFunctionExpression() ||
              p.isArrowFunctionExpression()
          );
        }

        if (componentPath) {
          const funcName = getFunctionName(componentPath);
          if (
            funcName === 'useBridgeState' ||
            funcName === 'useBridgeRegistry' ||
            funcName === 'useBridgeStateImpl'
          ) {
            return;
          }
        }

        const componentName = componentPath
          ? getComponentName(componentPath, state.filename)
          : 'UnknownComponent';

        // Get the hook index within this component
        const hookIndex = componentPath
          ? getNextHookIndex(componentPath)
          : 0;

        // Determine state key/name from variable assignment
        let stateKey = `state_${hookIndex}`;
        const parent = callPath.parentPath;
        if (parent && parent.isVariableDeclarator()) {
          const idNode = parent.node.id;
          if (t.isArrayPattern(idNode)) {
            const firstEl = idNode.elements[0];
            if (t.isIdentifier(firstEl)) {
              stateKey = firstEl.name;
            }
          } else if (t.isIdentifier(idNode)) {
            stateKey = idNode.name;
          }
        }

        // Replace CallExpression with _useBridgeState("ComponentName", "stateKey", hookIndex, ...args)
        const transformedCall = t.callExpression(t.identifier('_useBridgeState'), [
          t.stringLiteral(componentName),
          t.stringLiteral(stateKey),
          t.numericLiteral(hookIndex),
          ...node.arguments,
        ]);

        callPath.replaceWith(transformedCall);
        state.transformed = true;
      },
    },
  };
}
