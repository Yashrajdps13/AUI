from typing import List, Any, Optional, Literal, Union
from pydantic import BaseModel, Field


class SerializedStateSlot(BaseModel):
    key: str
    hookIndex: int
    description: Optional[str] = None
    sensitive: Optional[bool] = False
    writeable: Optional[str] = None


class InteractiveElement(BaseModel):
    selector: str
    tagName: str
    text: Optional[str] = None
    id: Optional[str] = None
    placeholder: Optional[str] = None
    disabled: Optional[bool] = False
    visible: Optional[bool] = True


class SerializedComponentEntry(BaseModel):
    id: str
    displayName: str
    mountedAt: int
    route: Optional[str] = None
    stateSlots: List[SerializedStateSlot] = Field(default_factory=list)
    interactiveElements: List[InteractiveElement] = Field(default_factory=list)
    actions: List[str] = Field(default_factory=list)


class AppLogEntry(BaseModel):
    type: Literal["info", "warn", "error"]
    source: Literal["console", "runtime", "unhandledrejection", "agent"]
    message: str
    timestamp: int
    stack: Optional[str] = None


class CommandAuditEntry(BaseModel):
    commandId: str
    type: Literal["setState", "dispatchEvent", "callAction"]
    target: str
    value: Any = None
    success: bool
    error: Optional[str] = None
    timestamp: int


# Bridge -> Agent message models
class RegistryDeltaMessage(BaseModel):
    type: Literal["registryDelta"] = "registryDelta"
    added: List[SerializedComponentEntry] = Field(default_factory=list)
    removed: List[str] = Field(default_factory=list)
    updated: List[SerializedComponentEntry] = Field(default_factory=list)


class StateSnapshotMessage(BaseModel):
    type: Literal["stateSnapshot"] = "stateSnapshot"
    target: str
    value: Any


class CommandAckMessage(BaseModel):
    type: Literal["commandAck"] = "commandAck"
    commandId: str
    success: bool
    error: Optional[str] = None


class RenderSettledMessage(BaseModel):
    type: Literal["renderSettled"] = "renderSettled"
    target: str


class AppLogMessage(BaseModel):
    type: Literal["appLog"] = "appLog"
    entry: AppLogEntry


class LedgerSnapshotMessage(BaseModel):
    type: Literal["ledgerSnapshot"] = "ledgerSnapshot"
    commandId: str
    ledger: List[AppLogEntry] = Field(default_factory=list)


class AuditLogSnapshotMessage(BaseModel):
    type: Literal["auditLogSnapshot"] = "auditLogSnapshot"
    commandId: str
    auditLog: List[CommandAuditEntry] = Field(default_factory=list)


class InteractionMessage(BaseModel):
    type: Literal["interaction"] = "interaction"
    componentId: str
    event: Literal["click", "change", "focus"]
    selector: str
    value: Optional[Any] = None


BridgeMessage = Union[
    RegistryDeltaMessage,
    StateSnapshotMessage,
    CommandAckMessage,
    RenderSettledMessage,
    AppLogMessage,
    LedgerSnapshotMessage,
    AuditLogSnapshotMessage,
    InteractionMessage,
]


# Helper function to parse raw bridge messages
def parse_bridge_message(data: dict) -> BridgeMessage:
    msg_type = data.get("type")
    if msg_type == "registryDelta":
        return RegistryDeltaMessage.model_validate(data)
    elif msg_type == "stateSnapshot":
        return StateSnapshotMessage.model_validate(data)
    elif msg_type == "commandAck":
        return CommandAckMessage.model_validate(data)
    elif msg_type == "renderSettled":
        return RenderSettledMessage.model_validate(data)
    elif msg_type == "appLog":
        return AppLogMessage.model_validate(data)
    elif msg_type == "ledgerSnapshot":
        return LedgerSnapshotMessage.model_validate(data)
    elif msg_type == "auditLogSnapshot":
        return AuditLogSnapshotMessage.model_validate(data)
    elif msg_type == "interaction":
        return InteractionMessage.model_validate(data)
    else:
        raise ValueError(f"Unknown message type: {msg_type}")
