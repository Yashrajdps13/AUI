from typing import List, Any, Optional, Literal


def get_langchain_tools(bridge) -> List[Any]:
    """
    Returns a list of LangChain StructuredTools mapped to react-agent-bridge operations.
    Requires langchain-core package to be installed.
    """
    try:
        from langchain_core.tools import StructuredTool
        from pydantic import BaseModel, Field
    except ImportError:
        raise ImportError(
            "langchain-core is required to use get_langchain_tools. "
            "Please install it using: pip install langchain-core"
        )

    # 1. setState input schema
    class SetStateSchema(BaseModel):
        target: str = Field(description="ComponentID.stateKey, e.g. 'CheckoutForm.username'")
        value: Any = Field(description="The new value to assign to the React state slot")

    async def aset_state(target: str, value: Any) -> str:
        try:
            success = await bridge.set_state(target, value)
            return "State set successfully." if success else "Failed to set state."
        except Exception as e:
            return f"Error: {e}"

    # 2. dispatchEvent input schema
    class DispatchEventSchema(BaseModel):
        target: str = Field(description="ComponentID, e.g. 'CheckoutForm#1'")
        event: Literal["click", "change", "focus"] = Field(description="Event type to dispatch")
        payload: Optional[str] = Field(None, description="Optional payload, e.g. CSS selector for click target")

    async def adispatch_event(target: str, event: str, payload: Optional[str] = None) -> str:
        try:
            success = await bridge.dispatch_event(target, event, payload)
            return "Event dispatched successfully." if success else "Failed to dispatch event."
        except Exception as e:
            return f"Error: {e}"

    # 3. callAction input schema
    class CallActionSchema(BaseModel):
        target: str = Field(description="ComponentID.actionName, e.g. 'AuthStore.login'")
        args: List[Any] = Field(description="List of arguments to pass to the Zustand/Redux store action")

    async def acall_action(target: str, args: List[Any]) -> str:
        try:
            success = await bridge.call_action(target, args)
            return "Action called successfully." if success else "Failed to call action."
        except Exception as e:
            return f"Error: {e}"

    # 4. waitFor input schema
    class WaitForSchema(BaseModel):
        target: str = Field(description="ComponentID.stateKey")
        operator: Literal["equals", "truthy", "falsy", "changed"] = Field(description="Comparison criteria")
        value: Optional[Any] = Field(None, description="Value to match if operator is equals")
        timeout_ms: Optional[int] = Field(5000, description="Condition wait timeout in milliseconds")

    async def await_for(target: str, operator: str, value: Optional[Any] = None, timeout_ms: int = 5000) -> str:
        try:
            success = await bridge.wait_for(target, operator, value, timeout_ms=timeout_ms)
            return "Condition met." if success else "Timeout waiting for condition."
        except Exception as e:
            return f"Error: {e}"

    return [
        StructuredTool.from_function(
            coroutine=aset_state,
            name="set_state",
            description="Mutate a React state slot directly (non-collection only).",
            args_schema=SetStateSchema
        ),
        StructuredTool.from_function(
            coroutine=adispatch_event,
            name="dispatch_event",
            description="Trigger an interactive action like click, change, or focus.",
            args_schema=DispatchEventSchema
        ),
        StructuredTool.from_function(
            coroutine=acall_action,
            name="call_action",
            description="Invoke a registered Zustand/Redux action handler.",
            args_schema=CallActionSchema
        ),
        StructuredTool.from_function(
            coroutine=await_for,
            name="wait_for",
            description="Wait for a state slot condition to be met.",
            args_schema=WaitForSchema
        ),
    ]
