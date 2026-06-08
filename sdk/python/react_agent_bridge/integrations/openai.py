from typing import List


def get_openai_tools() -> List[dict]:
    """
    Returns OpenAI function definitions for all react-agent-bridge command tools.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "set_state",
                "description": "Sets the value of a useState hook state slot.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {"type": "string", "description": "ComponentID.stateKey (e.g. 'CheckoutForm.username')"},
                        "value": {"description": "The value to set"}
                    },
                    "required": ["target", "value"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "dispatch_event",
                "description": "Dispatches an event (click, change, focus) targeting a mounted component.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {"type": "string", "description": "ComponentID (e.g. 'CheckoutForm#1')"},
                        "event": {"type": "string", "enum": ["click", "change", "focus"]},
                        "payload": {"type": "string", "description": "Optional payload, e.g. CSS selector for click target"}
                    },
                    "required": ["target", "event"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "call_action",
                "description": "Invokes a registered store action handler on a component.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {"type": "string", "description": "ComponentID.actionName (e.g. 'AuthStore.login')"},
                        "args": {"type": "array", "items": {}, "description": "Ordered arguments list"}
                    },
                    "required": ["target", "args"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "wait_for",
                "description": "Blocks execution until a state slot matches a condition.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {"type": "string", "description": "ComponentID.stateKey"},
                        "operator": {"type": "string", "enum": ["equals", "truthy", "falsy", "changed"]},
                        "value": {"description": "Comparison value if using 'equals' operator"},
                        "timeout_ms": {"type": "integer", "default": 5000}
                    },
                    "required": ["target", "operator"]
                }
            }
        }
    ]


async def handle_tool_call(bridge, name: str, arguments: dict) -> dict:
    """
    Routes an OpenAI function tool call to the corresponding bridge method.
    """
    try:
        if name == "set_state":
            success = await bridge.set_state(arguments["target"], arguments["value"])
            return {"success": success}
        elif name == "dispatch_event":
            success = await bridge.dispatch_event(
                arguments["target"],
                arguments["event"],
                arguments.get("payload")
            )
            return {"success": success}
        elif name == "call_action":
            success = await bridge.call_action(arguments["target"], arguments["args"])
            return {"success": success}
        elif name == "wait_for":
            success = await bridge.wait_for(
                arguments["target"],
                arguments["operator"],
                arguments.get("value"),
                timeout_ms=arguments.get("timeout_ms", 5000)
            )
            return {"success": success}
        else:
            return {"error": f"Unknown tool call: {name}"}
    except Exception as e:
        return {"error": str(e)}
