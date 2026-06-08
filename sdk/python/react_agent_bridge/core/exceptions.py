class BridgeError(Exception):
    """Base exception class for all react-agent-bridge errors."""
    pass


class ConnectionLostError(BridgeError):
    """Raised when the WebSocket connection is dropped unexpectedly."""
    pass


class CommandTimeoutError(BridgeError):
    """Raised when a command fails to receive an acknowledgement within the timeout."""
    pass


class CommandFailedError(BridgeError):
    """Raised when the bridge rejects a command (success=False)."""
    def __init__(self, message: str, error_type: str = "UNKNOWN_ERROR"):
        super().__init__(message)
        self.error_type = error_type


class RuleViolationError(BridgeError):
    """Raised when a command violates a core rule or custom business constraint."""
    def __init__(self, message: str, violation_details: dict = None):
        super().__init__(message)
        self.violation_details = violation_details or {}


class ConstraintCompilationError(BridgeError):
    """Raised when a plain English business logic constraint fails to compile into an executable rule."""
    pass
