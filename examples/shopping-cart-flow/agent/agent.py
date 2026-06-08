import asyncio
import json
import os
import sys
from dotenv import load_dotenv

# Load local environment variables
load_dotenv()

# Add local SDK path to sys.path before imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../sdk/python")))

from react_agent_bridge import ReactAgentBridge, AgentRunner, AgentState

# Initialize bridge server on port 8000
bridge = ReactAgentBridge(host="localhost", port=8000)

def on_connect():
    print("\n[Bridge Connected] React application successfully linked!")

def on_disconnect():
    print("\n[Bridge Disconnected] React app closed the connection.")

bridge.add_listener("connect", on_connect)
bridge.add_listener("disconnect", on_disconnect)


# ==========================================
# RULE-BASED PLANNER (No API Key Fallback)
# ==========================================
def rule_based_planner(query: str, registry: dict) -> list:
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


def has_llm_credentials() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def plan_actions_callback(state: AgentState) -> dict:
    if not has_llm_credentials():
        # Fallback to local rule-based planner if credentials are not configured
        commands = rule_based_planner(state["query"], state["registry"])
        return {"commands": commands, "status": "planned"}
    return None  # Fall back to standard LiteLLMAgent planning


business_context = """CRITICAL RULES FOR COMMAND SELECTION:
- The components in the REGISTRY SCHEMA contain an `interactiveElements` list, which lists DOM elements that can be interacted with, along with their `selector`, `text` content, and `id`.
- When performing a click event (like clicking a product, coupon button, checkout, or place order button), select the appropriate element from the component's `interactiveElements` list, and use its `selector` (e.g. "#btn-submit-order") as the `payload` for `dispatchEvent`.
- ALWAYS prefer `dispatchEvent` click commands for UI-based actions (such as adding products, navigating steps, clicking buttons, or applying coupons).
  - Example: To add an organic apple, DO NOT set the `cart` state directly. Instead, click the button using a dispatchEvent with target "App#...", event "click", and payload "#btn-prod-apple".
- ONLY use `setState` for simple user inputs/text fields (like `fullName`, `email`, `coupon`) that are typically modified by typing.
- NEVER use `setState` to write directly to complex state structures like lists or objects (e.g. `cart`) as that bypasses application logic and triggers crashes.

Note: If you want to click a button inside a component (e.g. App component), send a dispatchEvent to that component and specify its selector in the payload.
Example: to click "#btn-prod-apple" inside "App#_r_0_", use target: "App#_r_0_", event: "click", payload: "#btn-prod-apple"."""

runner = AgentRunner(
    bridge=bridge,
    model="gemini/gemini-2.5-flash" if has_llm_credentials() else "ollama/qwen2.5:7b",
    business_context=business_context,
    planner_fn=plan_actions_callback,
    max_steps=20
)

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
        query = await loop.run_in_executor(None, lambda: input("Agent Query > ").strip())
        if not query:
            continue
        if query.lower() in ["exit", "quit"]:
            print("Shutting down agent...")
            await bridge.stop()
            sys.exit(0)

        await runner.execute(query)


async def main():
    await bridge.start()
    await cli_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down server.")
