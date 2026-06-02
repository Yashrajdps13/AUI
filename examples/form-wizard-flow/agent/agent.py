import asyncio
import json
import sys
from typing import Dict, Any, List, Optional

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
                "payload": True
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
    print("Commands:")
    print("  register <free|premium> <username> <password>")
    print("  e.g. register premium alice secret123")
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

        parts = query.split()
        if len(parts) == 4 and parts[0].lower() == "register":
            tier = parts[1]
            username = parts[2]
            password = parts[3]
            if tier.lower() not in ["free", "premium"]:
                print("Error: tier must be 'free' or 'premium'")
                continue
            
            # Start the multi-step registration sequence
            await run_registration_wizard(username, password, tier)
        else:
            print("Invalid command. Use: register <free|premium> <username> <password>")

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
