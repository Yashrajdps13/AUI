// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { AgentLogger } from './logger.js';
import { AppLogEntry } from './protocol.js';

describe('AgentLogger', () => {
  beforeEach(() => {
    AgentLogger.clear();
  });

  afterEach(() => {
    AgentLogger.restore();
    AgentLogger.setListener(null);
  });

  it('should capture console.log, console.warn, and console.error into circular ledger', () => {
    AgentLogger.init();

    console.log('Test log message');
    console.warn('Test warn message');
    console.error('Test error message');

    const ledger = AgentLogger.getLedger();
    expect(ledger.length).toBe(3);

    expect(ledger[0].type).toBe('info');
    expect(ledger[0].message).toBe('Test log message');
    expect(ledger[0].source).toBe('console');

    expect(ledger[1].type).toBe('warn');
    expect(ledger[1].message).toBe('Test warn message');

    expect(ledger[2].type).toBe('error');
    expect(ledger[2].message).toBe('Test error message');
  });

  it('should notify the listener immediately when an error is logged', () => {
    AgentLogger.init();

    const listener = vi.fn();
    AgentLogger.setListener(listener);

    console.error('Crash happened');

    expect(listener).toHaveBeenCalledTimes(1);
    const entry = listener.mock.calls[0][0] as AppLogEntry;
    expect(entry.type).toBe('error');
    expect(entry.message).toBe('Crash happened');
  });

  it('should not notify the listener when info or warn logs are registered', () => {
    AgentLogger.init();

    const listener = vi.fn();
    AgentLogger.setListener(listener);

    console.log('Just info');
    console.warn('Just a warn');

    expect(listener).not.toHaveBeenCalled();
  });

  it('should rotate ledger and cap entries at 20', () => {
    AgentLogger.init();

    for (let i = 0; i < 25; i++) {
      console.log(`Log ${i}`);
    }

    const ledger = AgentLogger.getLedger();
    expect(ledger.length).toBe(20);
    expect(ledger[0].message).toBe('Log 5');
    expect(ledger[19].message).toBe('Log 24');
  });

  it('should capture runtime exceptions', () => {
    AgentLogger.init();

    const errorEvent = new ErrorEvent('error', {
      message: 'Uncaught TypeError: Cannot read property of null',
      error: new TypeError('Cannot read property of null'),
    });

    window.dispatchEvent(errorEvent);

    const ledger = AgentLogger.getLedger();
    const runtimeErrors = ledger.filter(e => e.source === 'runtime');
    expect(runtimeErrors.length).toBe(1);
    expect(runtimeErrors[0].type).toBe('error');
    expect(runtimeErrors[0].message).toBe('Uncaught TypeError: Cannot read property of null');
    expect(runtimeErrors[0].stack).toContain('TypeError');
  });

  it('should restore original console functions when restore is called', () => {
    const originalLog = console.log;
    AgentLogger.init();

    expect(console.log).not.toBe(originalLog);

    AgentLogger.restore();
    expect(console.log).toBe(originalLog);
  });
});
