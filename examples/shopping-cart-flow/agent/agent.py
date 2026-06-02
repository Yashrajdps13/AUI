import asyncio
import json
import os
import sys
from typing import Dict, Any, List, TypedDict, Optional
from dotenv import load_dotenv

# Load local environment variables
load_dotenv()

# Global connection reference and latest registry cache
ACTIVE_CONNECTION = None
LATEST_REGISTRY: Dict[str, Any] = {}
LATEST_VALUES: Dict[str, Any] = {}
COMMAND_FUTURE: Optional[asyncio.Future] = None
COMMAND_ACK_STATUS: Dict[str, Any] = {}

class AgentState(TypedDict):
    query: str
    registry: Dict[str, Any]
    values: Dict[str, Any]
    commands: List[Dict[str, Any]]
    status: str
    error: Optional[str]

# ==========================================
# RULE-BASED PLANNER (No API Key Fallback)
# ==========================================
def rule_based_planner(query: str, registry: Dict[str, Any]) -> List[Dict[str, Any]]:
    query_lower = query.lower()
    commands = []

    # Find the App component ID from the registry
    app_id = None
    for cid in registry.keys():
      if cid.startswith("App#"):
        app_id = cid
        break
    
    if not app_id:
        return [{"error": "Root 'App' component not found in registry yet."}]

    # Interpret queries
    if "add" in query_lower:
        # Check which product
        prod_id = None
        if "apple" in query_lower:
            prod_id = "prod-apple"
        elif "banana" in query_lower:
            prod_id = "prod-banana"
        elif "orange" in query_lower:
            prod_id = "prod-orange"

        if prod_id:
            commands.append({
                "type": "dispatchEvent",
                "commandId": "cmd-add-prod",
                "target": app_id,
                "event": "click",
                "payload": f"#btn-{prod_id}"
            })
        else:
            commands.append({"error": "Unknown product. Try 'add apple', 'add banana', or 'add orange'."})

    elif "set name" in query_lower or "fill name" in query_lower:
        # Extract name (e.g. "set name to John Doe")
        name = "John Doe"
        if "to " in query_lower:
            name = query.split("to ")[-1].strip()
        commands.append({
            "type": "setState",
            "commandId": "cmd-set-name",
            "target": f"{app_id}.fullName",
            "value": name
        })

    elif "set email" in query_lower or "fill email" in query_lower:
        # Extract email
        email = "customer@example.com"
        if "to " in query_lower:
            email = query.split("to ")[-1].strip()
        commands.append({
            "type": "setState",
            "commandId": "cmd-set-email",
            "target": f"{app_id}.email",
            "value": email
        })

    elif "coupon" in query_lower or "apply" in query_lower:
        # Set coupon state and click apply
        coupon = "SAVE10"
        if "coupon " in query_lower:
            coupon = query.split("coupon ")[-1].strip()
        
        commands.append({
            "type": "setState",
            "commandId": "cmd-set-coupon",
            "target": f"{app_id}.coupon",
            "value": coupon
        })
        commands.append({
            "type": "dispatchEvent",
            "commandId": "cmd-apply-coupon",
            "target": app_id,
            "event": "click",
            "payload": "#btn-apply-coupon"
        })

    elif "checkout" in query_lower or "proceed" in query_lower or "shipping" in query_lower:
        commands.append({
            "type": "dispatchEvent",
            "commandId": "cmd-go-checkout",
            "target": app_id,
            "event": "click",
            "payload": "#btn-go-to-checkout"
        })

    elif "place order" in query_lower or "submit" in query_lower or "complete" in query_lower:
        commands.append({
            "type": "dispatchEvent",
            "commandId": "cmd-place-order",
            "target": app_id,
            "event": "click",
            "payload": "#btn-submit-order"
        })

    elif "reset" in query_lower or "start over" in query_lower or "again" in query_lower:
        commands.append({
            "type": "dispatchEvent",
            "commandId": "cmd-reset",
            "target": app_id,
            "event": "click",
            "payload": "#btn-start-over"
        })
    else:
        commands.append({"error": "Query not matched by rule planner. Try: 'add apple', 'set name to Alice', 'set email to alice@example.com', 'coupon SAVE10', 'checkout', or 'place order'."})

    return commands

# ==========================================
# LANGGRAPH AGENT IMPLEMENTATION
# ==========================================
def has_llm_credentials() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))

# Lazy imports for LangChain to let CLI fallback run instantly without libraries installed
def get_llm_planner_node():
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import SystemMessage, HumanMessage
        
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)

        def plan_node(state: AgentState) -> Dict[str, Any]:
            registry_str = json.dumps(state["registry"], indent=2)
            values_str = json.dumps(state["values"], indent=2)
            
            system_prompt = f"""
You are an AI browser controller that operates a React application state via a WebSocket Bridge.
You receive a component registry schema showing components, their state slots, and their live interactive DOM elements (buttons, inputs, links, etc.):
---
REGISTRY SCHEMA:
{registry_str}
---
CURRENT STATE VALUES (Subscribed):
{values_str}
---

Your goal is to parse the user's natural language request and output a JSON array of commands to execute.

Available commands:
1. State assignment:
   {{"type": "setState", "commandId": "unique-id", "target": "ComponentID.stateKey", "value": val}}
2. DOM interactions (events):
   {{"type": "dispatchEvent", "commandId": "unique-id", "target": "ComponentID", "event": "click" | "focus" | "change", "payload": "selector-string-or-value"}}

CRITICAL RULES FOR COMMAND SELECTION:
- The components in the REGISTRY SCHEMA contain an `interactiveElements` list, which lists DOM elements that can be interacted with, along with their `selector`, `text` content, and `id`.
- When performing a click event (like clicking a product, coupon button, checkout, or place order button), select the appropriate element from the component's `interactiveElements` list, and use its `selector` (e.g. "#btn-submit-order") as the `payload` for `dispatchEvent`.
- ALWAYS prefer `dispatchEvent` click commands for UI-based actions (such as adding products, navigating steps, clicking buttons, or applying coupons).
  - Example: To add an organic apple, DO NOT set the `cart` state directly. Instead, click the button using a dispatchEvent with target "App#...", event "click", and payload "#btn-prod-apple".
- ONLY use `setState` for simple user inputs/text fields (like `fullName`, `email`, `coupon`) that are typically modified by typing.
- NEVER use `setState` to write directly to complex state structures like lists or objects (e.g. `cart`) as that bypasses application logic and triggers crashes.

Note: If you want to click a button inside a component (e.g. App component), send a dispatchEvent to that component and specify its selector in the payload.
Example: to click "#btn-prod-apple" inside "App#_r_0_", use target: "App#_r_0_", event: "click", payload: "#btn-prod-apple".

Respond ONLY with a valid JSON array of commands. No markdown blocks, no formatting.
Example Response:
[
  {{"type": "setState", "commandId": "cmd-1", "target": "App#_r_0_.fullName", "value": "Jane"}}
]
"""
            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=state["query"])
            ])
            
            try:
                # Strip out potential markdown formatting codeblocks if the LLM emitted them
                content = response.content.strip()
                if content.startswith("```json"):
                    content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
                commands = json.loads(content.strip())
                return {"commands": commands, "status": "planned"}
            except Exception as e:
                return {"commands": [], "status": "failed", "error": f"LLM parsing failed: {e}. Output was: {response.content}"}
        
        return plan_node
    except ImportError:
        # Fallback if package not installed
        def plan_fallback(state: AgentState) -> Dict[str, Any]:
            return {"commands": rule_based_planner(state["query"], state["registry"]), "status": "planned"}
        return plan_fallback

def plan_actions(state: AgentState) -> Dict[str, Any]:
    if has_llm_credentials():
        node = get_llm_planner_node()
        return node(state)
    else:
        # Rule-based fallback
        commands = rule_based_planner(state["query"], state["registry"])
        return {"commands": commands, "status": "planned"}

async def execute_actions(state: AgentState) -> Dict[str, Any]:
    global ACTIVE_CONNECTION, COMMAND_FUTURE, COMMAND_ACK_STATUS
    
    if not ACTIVE_CONNECTION:
        return {"status": "failed", "error": "No active WebSocket connection from React app."}

    commands = state["commands"]
    success_count = 0
    
    for cmd in commands:
        if "error" in cmd:
            print(f"Plan error: {cmd['error']}")
            continue
            
        cmd_id = cmd.get("commandId", "cmd-default")
        
        # Setup future to wait for command acknowledgment
        COMMAND_FUTURE = asyncio.get_running_loop().create_future()
        
        # Send command over websocket
        print(f"Sending command to bridge: {cmd['type']} -> {cmd.get('target')}")
        await ACTIVE_CONNECTION.send(json.dumps(cmd))
        
        # Wait for acknowledgment (with 5-second timeout)
        try:
            ack = await asyncio.wait_for(COMMAND_FUTURE, timeout=5.0)
            if ack.get("success"):
                success_count += 1
            else:
                print(f"Command failed: {ack.get('error')}")
        except asyncio.TimeoutError:
            print(f"Command timed out waiting for Ack.")
        finally:
            COMMAND_FUTURE = None

    return {"status": "executed" if success_count == len(commands) else "partially_executed"}

# Build LangGraph Workflow
from langgraph.graph import StateGraph, END

workflow = StateGraph(AgentState)
workflow.add_node("plan", plan_actions)
workflow.add_node("execute", execute_actions)

workflow.set_entry_point("plan")
workflow.add_conditional_edges(
    "plan",
    lambda state: "execute" if state["status"] == "planned" and state["commands"] and "error" not in state["commands"][0] else END,
    {
        "execute": "execute",
        END: END
    }
)
workflow.add_edge("execute", END)
graph = workflow.compile()

# ==========================================
# WEBSOCKET SERVER IMPLEMENTATION
# ==========================================
import websockets

async def handle_ws(websocket):
    global ACTIVE_CONNECTION, LATEST_REGISTRY, LATEST_VALUES, COMMAND_FUTURE
    print("\n[Bridge Connected] React application successfully linked!")
    ACTIVE_CONNECTION = websocket

    # Request the full registry schema on connection
    await websocket.send(json.dumps({
        "type": "getRegistry",
        "commandId": "initial-sync"
    }))

    try:
        async for message in websocket:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "registryDelta":
                # Apply deltas to local cache
                for comp in data.get("added", []):
                    LATEST_REGISTRY[comp["id"]] = comp
                for comp in data.get("updated", []):
                    LATEST_REGISTRY[comp["id"]] = comp
                for comp_id in data.get("removed", []):
                    LATEST_REGISTRY.pop(comp_id, None)
                
                print(f"\n[Registry Updated] Active components: {list(LATEST_REGISTRY.keys())}")
                
                # Automatically subscribe to the main App component for state updates
                for cid in LATEST_REGISTRY.keys():
                    if cid.startswith("App#") and cid not in LATEST_VALUES:
                        await websocket.send(json.dumps({
                            "type": "subscribe",
                            "commandId": "auto-sub",
                            "target": cid
                        }))

            elif msg_type == "stateSnapshot":
                target = data.get("target")
                val = data.get("value")
                LATEST_VALUES[target] = val
                print(f"[State Synced] {target} = {val}")

            elif msg_type == "commandAck":
                cmd_id = data.get("commandId")
                if COMMAND_FUTURE and not COMMAND_FUTURE.done():
                    COMMAND_FUTURE.set_result(data)

    except websockets.exceptions.ConnectionClosedOK:
        print("\n[Bridge Disconnected] React app closed the connection.")
    except Exception as e:
        print(f"\n[Error] Connection crashed: {e}")
    finally:
        ACTIVE_CONNECTION = None
        LATEST_REGISTRY.clear()
        LATEST_VALUES.clear()

async def start_server():
    server = await websockets.serve(handle_ws, "localhost", 8000)
    print("WebSocket Server running at ws://localhost:8000")
    await server.wait_closed()

# ==========================================
# INTERACTIVE CLI LOOP
# ==========================================
async def cli_loop():
    print("\n=======================================================")
    print("react-agent-bridge LangGraph CLI Controller")
    if has_llm_credentials():
        print("Model Mode: Gemini 2.5 Flash LLM Planner active.")
    else:
        print("Model Mode: Local Rule-based Planner active (No Gemini key found).")
    print("Commands available: add apple, set name to Alice, checkout, etc.")
    print("=======================================================\n")

    loop = asyncio.get_event_loop()
    while True:
        # Prompt user input asynchronously
        query = await loop.run_in_executor(None, lambda: input("Agent Query > ").strip())
        if not query:
            continue
        if query.lower() in ["exit", "quit"]:
            print("Shutting down agent...")
            sys.exit(0)

        if not ACTIVE_CONNECTION:
            print("Error: No React client connected. Please open the sample frontend in your browser.")
            continue

        # Build initial LangGraph state
        state: AgentState = {
            "query": query,
            "registry": LATEST_REGISTRY,
            "values": LATEST_VALUES,
            "commands": [],
            "status": "init",
            "error": None
        }

        # Run the workflow
        result = await graph.ainvoke(state)
        
        print(f"Result Status: {result['status']}")
        if result.get("error"):
            print(f"Error: {result['error']}")

async def main():
    # Run both the WS server and the CLI loop concurrently
    await asyncio.gather(
        start_server(),
        cli_loop()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down server.")
