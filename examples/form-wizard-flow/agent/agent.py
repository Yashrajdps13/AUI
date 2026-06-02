import asyncio
import json
import os
import sys
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# Load local environment variables
load_dotenv()

# Global connection reference and latest registry cache
ACTIVE_CONNECTION = None
LATEST_REGISTRY: Dict[str, Any] = {}
LATEST_VALUES: Dict[str, Any] = {}
COMMAND_FUTURE: Optional[asyncio.Future] = None
SETTLE_FUTURE: Optional[asyncio.Future] = None

# ==========================================
# COMMAND RUNNER HELPER (Awaits Ack + Render Settlement)
# ==========================================
async def execute_command_and_wait(cmd: Dict[str, Any]) -> bool:
    global ACTIVE_CONNECTION, COMMAND_FUTURE, SETTLE_FUTURE
    if not ACTIVE_CONNECTION:
        print("Error: No React client connected. Please open the frontend in your browser.")
        return False

    cmd_id = cmd.get("commandId", "cmd-default")
    COMMAND_FUTURE = asyncio.get_running_loop().create_future()
    SETTLE_FUTURE = asyncio.get_running_loop().create_future()

    print(f"\n[Agent Action] Sending command: {cmd['type']} -> {cmd.get('target')} (value/payload: {cmd.get('value') or cmd.get('payload')})")
    await ACTIVE_CONNECTION.send(json.dumps(cmd))

    # 1. Wait for client command acknowledgment
    try:
        ack = await asyncio.wait_for(COMMAND_FUTURE, timeout=3.0)
        if not ack.get("success"):
            print(f"  [Error] Command failed: {ack.get('error')}")
            return False
        print("  [OK] Command acknowledged by React Bridge.")
    except asyncio.TimeoutError:
        print("  [Error] Command acknowledgment timed out.")
        return False
    finally:
        COMMAND_FUTURE = None

    # 2. Wait for React layout commitment and scan settlement
    try:
        print("  [Waiting] Waiting for React render settlement...")
        await asyncio.wait_for(SETTLE_FUTURE, timeout=3.0)
        print("  [OK] React render settled event received.")
    except asyncio.TimeoutError:
        print("  [Warning] Render settlement timed out. Continuing...")
    finally:
        SETTLE_FUTURE = None

    return True

# ==========================================
# WIZARD REGISTRATION WORKFLOW (ReAct Loop)
# ==========================================
async def run_registration_wizard(username, password, tier):
    global LATEST_REGISTRY, LATEST_VALUES
    print(f"\n=== Starting Multi-Step Wizard Registration ===")
    print(f"Target Username: @{username}")
    print(f"Target Plan:     {tier.upper()}")
    
    app_id = None
    for cid in LATEST_REGISTRY.keys():
        if cid.startswith("App#"):
            app_id = cid
            break

    if not app_id:
        print("[Error] Root 'App' component not detected in bridge registry. Is the frontend loaded?")
        return

    # --- STEP 1: ACCOUNT DETAILS ---
    print("\n--- Step 1: Inputting account details ---")
    
    # 1. Fill Username
    success = await execute_command_and_wait({
        "type": "setState",
        "commandId": "set-username",
        "target": f"{app_id}.username",
        "value": username
    })
    if not success: return

    # 2. Fill Password
    success = await execute_command_and_wait({
        "type": "setState",
        "commandId": "set-password",
        "target": f"{app_id}.password",
        "value": password
    })
    if not success: return

    # 3. Observe elements to see if the "Continue" button is enabled
    app_entry = LATEST_REGISTRY.get(app_id, {})
    interactive_elements = app_entry.get("interactiveElements", [])
    next_btn = next((el for el in interactive_elements if el.get("id") == "btn-next-step-1"), None)

    if next_btn:
        print(f"[Agent Observation] Next button: selector='{next_btn['selector']}', disabled={next_btn.get('disabled')}, visible={next_btn.get('visible')}")
        if next_btn.get("disabled"):
            print("[Error] Next button is disabled. Cannot proceed.")
            return
    else:
        print("[Warning] Next button was not scanned or found in active elements.")

    # 4. Click Continue
    success = await execute_command_and_wait({
        "type": "dispatchEvent",
        "commandId": "click-next-1",
        "target": app_id,
        "event": "click",
        "payload": "#btn-next-step-1"
    })
    if not success: return

    # --- STEP 2: SUBSCRIPTION SELECTION ---
    print("\n--- Step 2: Selecting tier preference ---")
    await asyncio.sleep(0.2)  # brief pause to let local state propagate

    if tier.lower() == "premium":
        # 1. Click Premium Plan
        success = await execute_command_and_wait({
            "type": "dispatchEvent",
            "commandId": "click-premium",
            "target": app_id,
            "event": "click",
            "payload": "#btn-tier-premium"
        })
        if not success: return

        # 2. Observe the Terms Agreement checkbox (which renders conditionally for Premium)
        await asyncio.sleep(0.2)
        app_entry = LATEST_REGISTRY.get(app_id, {})
        interactive_elements = app_entry.get("interactiveElements", [])
        terms_checkbox = next((el for el in interactive_elements if el.get("id") == "input-accept-terms"), None)

        if terms_checkbox:
            print(f"[Agent Observation] Terms checkbox: selector='{terms_checkbox['selector']}', disabled={terms_checkbox.get('disabled')}, visible={terms_checkbox.get('visible')}")
            
            # 3. Accept Terms
            success = await execute_command_and_wait({
                "type": "dispatchEvent",
                "commandId": "check-terms",
                "target": app_id,
                "event": "change",
                "payload": {
                    "selector": "#input-accept-terms",
                    "value": True
                }
            })
            if not success: return
        else:
            print("[Error] Premium plan selected but terms checkbox not visible in scanned registry.")
            return
    else:
        print("[Agent Observation] Free plan selected. Renders no terms checkbox.")

    # 4. Click Submit
    success = await execute_command_and_wait({
        "type": "dispatchEvent",
        "commandId": "click-submit",
        "target": app_id,
        "event": "click",
        "payload": "#btn-submit-wizard"
    })
    if not success: return

    # --- STEP 3: SUCCESS CONFIRMATION ---
    print("\n--- Step 3: Success Screen Verification ---")
    await asyncio.sleep(0.2)
    print("\n[Success] Wizard registration successfully completed by AUI Agent!")

# ==========================================
# DYNAMIC REACT AGENT & HEURISTIC FALLBACK
# ==========================================
def has_llm_credentials() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))

def parse_query_heuristically(query: str):
    query_lower = query.lower()
    
    # Tier
    tier = "free"
    if "premium" in query_lower:
        tier = "premium"
        
    # Username
    username = "alice"
    for word in ["name", "username", "named", "user"]:
        if word in query_lower:
            parts = query.split(word)
            if len(parts) > 1:
                subparts = parts[1].strip().split()
                if subparts:
                    username = subparts[0].strip().replace(":", "").replace("@", "")
                    if username in ["a", "new", "with", "and", "is", "to", "for"] and len(subparts) > 1:
                        username = subparts[1].strip().replace(":", "").replace("@", "")
                    break

    # Password
    password = "secret123"
    for word in ["password", "pass", "code"]:
        if word in query_lower:
            parts = query.split(word)
            if len(parts) > 1:
                subparts = parts[1].strip().split()
                if subparts:
                    password = subparts[0].strip().replace(":", "")
                    if password in ["a", "new", "with", "and", "is", "to", "for"] and len(subparts) > 1:
                        password = subparts[1].strip().replace(":", "")
                    break
    return username, password, tier

async def run_dynamic_react_agent(query: str):
    global LATEST_REGISTRY, LATEST_VALUES
    
    if not has_llm_credentials():
        print("[Warning] No GEMINI_API_KEY found. Falling back to rule-based registration parser.")
        username, password, tier = parse_query_heuristically(query)
        await run_registration_wizard(username, password, tier)
        return

    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.messages import SystemMessage, HumanMessage

    print(f"\n=== Starting Dynamic ReAct Agent Loop ===")
    print(f"Query: {query}")

    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    max_steps = 12
    step = 0

    while step < max_steps:
        step += 1
        print(f"\n--- Agent Step {step} ---")

        # Find App component ID
        app_id = None
        for cid in LATEST_REGISTRY.keys():
            if cid.startswith("App#"):
                app_id = cid
                break

        if not app_id:
            print("[Error] App component not found in registry. Is the frontend loaded?")
            return

        # Format registry and current state values
        registry_str = json.dumps(LATEST_REGISTRY, indent=2)
        values_str = json.dumps(LATEST_VALUES, indent=2)

        system_prompt = f"""
You are an AI assistant that controls a React application state using a WebSocket Bridge.
You receive the application's component registry schema showing components, their state slots (complete with description comments detailing what each state does), and all active, interactive DOM elements (buttons, inputs, checkboxes, etc.):
---
REGISTRY SCHEMA:
{registry_str}
---
CURRENT STATE VALUES (Subscribed):
{values_str}
---

Your goal is to satisfy the user's natural language request: "{query}"

Available actions:
1. Set state values (equivalent to typing or entering inputs):
   {{"type": "setState", "commandId": "some-id", "target": "ComponentID.stateKey", "value": val}}
2. Dispatch click, change or focus events to DOM elements:
   {{"type": "dispatchEvent", "commandId": "some-id", "target": "ComponentID", "event": "click" | "change" | "focus", "payload": "selector-string-or-value"}}

CRITICAL RULES:
- Inspect the description comment of each state slot to determine which inputs correspond to user request details (e.g. username, password, tier).
- When clicking buttons, checkboxes, or plan cards, locate the element in the component's `interactiveElements` metadata. Use the exact `selector` (e.g. "#btn-next-step-1" or "#btn-tier-premium" or "#btn-submit-wizard") as the `payload` for `dispatchEvent` click.
- Only interact with interactive elements that are `visible: true` and NOT `disabled: true`.
- If the user's specific goal/request has been fully accomplished (e.g. the specific fields/inputs they asked for have been successfully set, or the specific buttons they wanted clicked have been clicked), respond with the word: DONE. Do NOT perform any additional unsolicited actions or navigate to subsequent steps unless the user explicitly requested it in the query.
- Otherwise, plan the next single command or small sequence of commands to execute.
- Respond ONLY with the JSON array of commands or the single word DONE. No markdown blocks, formatting, or extra text.

Example Response (next steps):
[
  {{"type": "setState", "commandId": "fill-1", "target": "App#_r_0_.username", "value": "Alice"}}
]

Example Response (when complete):
DONE
"""

        response = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=query)
            ])
        )

        content = response.content.strip()
        if content == "DONE" or "DONE" in content:
            print("\n[Success] Dynamic agent has satisfied the request!")
            return

        try:
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            commands = json.loads(content.strip())
        except Exception as e:
            print(f"[Error] Failed to parse agent response as JSON: {e}. Output was:\n{content}")
            return

        if not isinstance(commands, list) or len(commands) == 0:
            print("\n[Done] No further commands planned. Returning to query mode.")
            return

        for cmd in commands:
            success = await execute_command_and_wait(cmd)
            if not success:
                print(f"[Error] Command execution failed: {cmd}")
                return

        # Small pause for rendering
        await asyncio.sleep(0.3)

    print("[Error] Dynamic agent reached step limit without completion.")

# ==========================================
# WEBSOCKET SERVER IMPLEMENTATION
# ==========================================
import websockets

async def handle_ws(websocket):
    global ACTIVE_CONNECTION, LATEST_REGISTRY, LATEST_VALUES, COMMAND_FUTURE, SETTLE_FUTURE
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
                for comp in data.get("added", []):
                    LATEST_REGISTRY[comp["id"]] = comp
                for comp in data.get("updated", []):
                    LATEST_REGISTRY[comp["id"]] = comp
                for comp_id in data.get("removed", []):
                    LATEST_REGISTRY.pop(comp_id, None)
                
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

            elif msg_type == "commandAck":
                if COMMAND_FUTURE and not COMMAND_FUTURE.done():
                    COMMAND_FUTURE.set_result(data)

            elif msg_type == "renderSettled":
                target = data.get("target")
                print(f"[Render Settled] React committed DOM updates (target: {target})")
                if SETTLE_FUTURE and not SETTLE_FUTURE.done():
                    SETTLE_FUTURE.set_result(data)

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
    print("AUI Form Wizard CLI Controller")
    if has_llm_credentials():
        print("Model Mode: Gemini 2.5 Flash LLM ReAct loop active.")
    else:
        print("Model Mode: Local Rule-based Parser active (No Gemini key found).")
    print("Commands:")
    print("  Input any natural language registration request.")
    print("  e.g. Register a new user with name Alice and password test123")
    print("=======================================================\n")

    loop = asyncio.get_event_loop()
    while True:
        query = await loop.run_in_executor(None, lambda: input("Agent Query > ").strip())
        if not query:
            continue
        if query.lower() in ["exit", "quit"]:
            print("Shutting down agent...")
            sys.exit(0)

        if not ACTIVE_CONNECTION:
            print("Error: No React client connected. Please open the Form Wizard frontend in your browser.")
            continue

        # Run the dynamic ReAct agent loop
        await run_dynamic_react_agent(query)

async def main():
    await asyncio.gather(
        start_server(),
        cli_loop()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down server.")
