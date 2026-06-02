import { AppLogEntry } from './protocol.js';

type LogListener = (entry: AppLogEntry) => void;

class AgentLoggerImpl {
  private ledger: AppLogEntry[] = [];
  private maxLedgerSize = 20;
  private isInitialized = false;
  private listener: LogListener | null = null;

  // Store original console methods
  private originalLog: typeof console.log = typeof console !== 'undefined' ? console.log : () => {};
  private originalWarn: typeof console.warn = typeof console !== 'undefined' ? console.warn : () => {};
  private originalError: typeof console.error = typeof console !== 'undefined' ? console.error : () => {};

  private errorHandler = (event: ErrorEvent) => {
    const entry: AppLogEntry = {
      type: 'error',
      source: 'runtime',
      message: event.message || 'Uncaught runtime error',
      timestamp: Date.now(),
      stack: event.error?.stack,
    };
    this.addEntry(entry, true);
  };

  private rejectionHandler = (event: PromiseRejectionEvent) => {
    const reason = event.reason;
    const message = reason instanceof Error ? reason.message : String(reason);
    const stack = reason instanceof Error ? reason.stack : undefined;
    
    const entry: AppLogEntry = {
      type: 'error',
      source: 'unhandledrejection',
      message: `Unhandled Promise Rejection: ${message}`,
      timestamp: Date.now(),
      stack,
    };
    this.addEntry(entry, true);
  };

  /**
   * Initializes the logger hooks for uncaught errors and console channels.
   * Runs exactly once and is safe to execute in non-browser environments.
   */
  init(): void {
    if (this.isInitialized || typeof window === 'undefined') return;
    this.isInitialized = true;

    // 1. Intercept uncaught runtime exceptions
    window.addEventListener('error', this.errorHandler);

    // 2. Intercept unhandled promise rejections
    window.addEventListener('unhandledrejection', this.rejectionHandler);

    // 3. Patch console.error
    console.error = (...args: any[]) => {
      // Execute original console behavior first
      this.originalError.apply(console, args);
      
      const message = args.map(arg => typeof arg === 'object' ? this.safeStringify(arg) : String(arg)).join(' ');
      const entry: AppLogEntry = {
        type: 'error',
        source: 'console',
        message,
        timestamp: Date.now(),
      };
      this.addEntry(entry, true);
    };

    // 4. Patch console.warn
    console.warn = (...args: any[]) => {
      this.originalWarn.apply(console, args);
      
      const message = args.map(arg => typeof arg === 'object' ? this.safeStringify(arg) : String(arg)).join(' ');
      const entry: AppLogEntry = {
        type: 'warn',
        source: 'console',
        message,
        timestamp: Date.now(),
      };
      this.addEntry(entry, false); // do not stream warning by default
    };

    // 5. Patch console.log
    console.log = (...args: any[]) => {
      this.originalLog.apply(console, args);
      
      const message = args.map(arg => typeof arg === 'object' ? this.safeStringify(arg) : String(arg)).join(' ');
      const entry: AppLogEntry = {
        type: 'info',
        source: 'console',
        message,
        timestamp: Date.now(),
      };
      this.addEntry(entry, false); // do not stream info log by default
    };
  }

  /**
   * Sets the active listener to stream immediate messages (e.g. error alerts).
   */
  setListener(listener: LogListener | null): void {
    this.listener = listener;
  }

  /**
   * Appends an entry to the circular ledger buffer.
   */
  addEntry(entry: AppLogEntry, streamImmediate = false): void {
    this.ledger.push(entry);
    if (this.ledger.length > this.maxLedgerSize) {
      this.ledger.shift();
    }

    if (streamImmediate && this.listener) {
      try {
        this.listener(entry);
      } catch (err) {
        this.originalError.call(console, 'Failed to invoke Agent Logger listener:', err);
      }
    }
  }

  /**
   * Retrieves the current ledger snapshot.
   */
  getLedger(): AppLogEntry[] {
    return [...this.ledger];
  }

  /**
   * Clears the current logs ledger history.
   */
  clear(): void {
    this.ledger = [];
  }

  /**
   * Restores original console channel methods.
   */
  restore(): void {
    if (!this.isInitialized) return;
    this.isInitialized = false;

    if (typeof window !== 'undefined') {
      window.removeEventListener('error', this.errorHandler);
      window.removeEventListener('unhandledrejection', this.rejectionHandler);
    }

    if (typeof console !== 'undefined') {
      console.log = this.originalLog;
      console.warn = this.originalWarn;
      console.error = this.originalError;
    }
  }

  private safeStringify(obj: any): string {
    try {
      return JSON.stringify(obj);
    } catch {
      return '[Circular or Unserializable Object]';
    }
  }
}

export const AgentLogger = new AgentLoggerImpl();
