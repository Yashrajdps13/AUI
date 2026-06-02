import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# Load local environment variables
load_dotenv()

# Global connection reference and latest registry cache
ACTIVE_CONNECTION = None
LATEST_REGISTRY: Dict[str, Any] = {}
COMMAND_FUTURE: Optional[asyncio.Future] = None
LEDGER_FUTURE: Optional[asyncio.Future] = None

# Terminal text colors
RED = "\033[1;31m"
YELLOW = "\033[1;33m"
GREEN = "\033[1;32m"
CYAN = "\033[1;36m"
MAGENTA = "\033[1;35m"
RESET = "\033[0m"

async def execute_command(cmd: Dict[str, Any]) -> bool:
    global ACTIVE_CONNECTION, COMMAND_FUTURE
    if not ACTIVE_CONNECTION:
        print(f"{RED}Error: No React client connected.{RESET}")
        return False

    COMMAND_FUTURE = asyncio.get_running_loop().create_future()
    await ACTIVE_CONNECTION.send(json.dumps(cmd))
    
    try:
        ack = await asyncio.wait_for(COMMAND_FUTURE, timeout=6.0) # slightly longer timeout for async loads
        success = ack.get("success", False)
        if not success:
            print(f"{RED}[Command Failed] {ack.get('error', 'Unknown error')}{RESET}")
        return success
    except asyncio.TimeoutError:
        print(f"{RED}[Error] Command timed out waiting for Ack.{RESET}")
        return False
    finally:
        COMMAND_FUTURE = None

# ==========================================
# WEBSOCKET SERVER IMPLEMENTATION
# ==========================================
import websockets

async def handle_ws(websocket):
    global ACTIVE_CONNECTION, LATEST_REGISTRY, COMMAND_FUTURE, LEDGER_FUTURE
    print(f"\n{GREEN}[Bridge Connected] React application successfully linked!{RESET}")
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

            elif msg_type == "commandAck":
                if COMMAND_FUTURE and not COMMAND_FUTURE.done():
                    COMMAND_FUTURE.set_result(data)

            elif msg_type == "appLog":
                entry = data.get("entry", {})
                t_str = datetime.fromtimestamp(entry.get("timestamp", 0) / 1000).strftime('%H:%M:%S')
                # Format logs
                msg_color = RED if entry.get("type") == "error" else (YELLOW if entry.get("type") == "warn" else GREEN)
                print(f"\n{msg_color}[STREAMED LOG] [{t_str}] [Source: {entry.get('source')}] {entry.get('message')}{RESET}")
                if entry.get("stack"):
                    print(f"{msg_color}{entry.get('stack')}{RESET}")
                print("Agent Query > ", end="", flush=True)

            elif msg_type == "ledgerSnapshot":
                if LEDGER_FUTURE and not LEDGER_FUTURE.done():
                    LEDGER_FUTURE.set_result(data)

    except websockets.exceptions.ConnectionClosedOK:
        print(f"\n{YELLOW}[Bridge Disconnected] React app closed the connection.{RESET}")
    except Exception as e:
        print(f"\n{RED}[Error] Connection crashed: {e}{RESET}")
    finally:
        ACTIVE_CONNECTION = None
        LATEST_REGISTRY.clear()

async def start_server():
    server = await websockets.serve(handle_ws, "localhost", 8000)
    print(f"{CYAN}WebSocket Server running at ws://localhost:8000{RESET}")
    await server.wait_closed()

# ==========================================
# INTERACTIVE CLI LOOP
# ==========================================
async def cli_loop():
    global LEDGER_FUTURE
    print(f"\n=======================================================")
    print(f"{CYAN}AUI waitFor Condition Handshake Controller{RESET}")
    print("Commands:")
    print("  registry    - Print the current component and state registry")
    print("  ledger      - Query the circular log ledger from the browser")
    print("  load        - Click load button and wait for async completion using waitFor")
    print("  reset       - Click the reset button to clear the state")
    print("  exit / quit - Shutdown agent")
    print(f"=======================================================\n")

    loop = asyncio.get_event_loop()
    while True:
        query = await loop.run_in_executor(None, lambda: input("Agent Query > ").strip())
        if not query:
            continue
        
        cmd_name = query.lower()

        if cmd_name in ["exit", "quit"]:
            print("Shutting down agent...")
            sys.exit(0)

        if not ACTIVE_CONNECTION:
            print(f"{RED}Error: No React client connected. Please open the frontend in your browser.{RESET}")
            continue

        if cmd_name == "registry":
            print(f"\n{CYAN}--- Active Bridge Registry ---{RESET}")
            for comp_id, comp in LATEST_REGISTRY.items():
                print(f"ID: {GREEN}{comp_id}{RESET}")
                print(f"  DisplayName: {comp.get('displayName')}")
                print(f"  State Slots:")
                for slot in comp.get("stateSlots", []):
                    print(f"    - {slot.get('key')} (hookIndex: {slot.get('hookIndex')})")
            print(f"{CYAN}------------------------------{RESET}\n")

        elif cmd_name == "ledger":
            LEDGER_FUTURE = asyncio.get_running_loop().create_future()
            await ACTIVE_CONNECTION.send(json.dumps({
                "type": "queryLedger",
                "commandId": "get-ledger-snapshot"
            }))
            
            try:
                snapshot = await asyncio.wait_for(LEDGER_FUTURE, timeout=3.0)
                ledger = snapshot.get("ledger", [])
                print(f"\n{CYAN}--- Circular Log Ledger Snapshot (Browser Flight Recorder) ---{RESET}")
                if not ledger:
                    print("Ledger is empty.")
                else:
                    for i, log in enumerate(ledger):
                        t = datetime.fromtimestamp(log.get("timestamp", 0) / 1000).strftime('%H:%M:%S')
                        log_type = log.get("type").upper()
                        color = RED if log_type == "ERROR" else (YELLOW if log_type == "WARN" else GREEN)
                        print(f"[{i:02d}] [{t}] {color}[{log_type}]{RESET} [Source: {log.get('source')}] {log.get('message')}")
                print(f"{CYAN}---------------------------------------------------------------{RESET}\n")
            except asyncio.TimeoutError:
                print(f"{RED}Failed to query ledger snapshot (timeout).{RESET}")
            finally:
                LEDGER_FUTURE = None

        elif cmd_name == "load":
            app_id = None
            for cid in LATEST_REGISTRY.keys():
                if cid.startswith("App#"):
                    app_id = cid
                    break

            if not app_id:
                print(f"{RED}Error: App component not found in registry.{RESET}")
                continue

            print(f"\n{CYAN}[Step 1] Triggering load simulation by clicking #btn-load...{RESET}")
            click_success = await execute_command({
                "type": "dispatchEvent",
                "commandId": "click-load",
                "target": app_id,
                "event": "click",
                "payload": "#btn-load"
            })
            
            if not click_success:
                print(f"{RED}Failed to click load button.{RESET}")
                continue

            print(f"{CYAN}[Step 2] Sending 'waitFor' to check when isLoading becomes True...{RESET}")
            wait_loading_success = await execute_command({
                "type": "waitFor",
                "commandId": "wait-for-loading-true",
                "target": f"{app_id}.isLoading",
                "condition": {
                    "operator": "truthy"
                },
                "timeoutMs": 2000
            })

            if not wait_loading_success:
                print(f"{RED}Timed out waiting for loading spinner to start.{RESET}")
                continue
            
            print(f"{GREEN}[OK] Loading start detected by bridge. App is now in loading state.{RESET}")
            print(f"{CYAN}[Step 3] Sending 'waitFor' to await isLoading becoming False (resolving load)...{RESET}")
            
            # Start timer to measure delay
            start_time = datetime.now()

            wait_complete_success = await execute_command({
                "type": "waitFor",
                "commandId": "wait-for-loading-false",
                "target": f"{app_id}.isLoading",
                "condition": {
                    "operator": "falsy"
                },
                "timeoutMs": 5000
            })

            if not wait_complete_success:
                print(f"{RED}Timed out waiting for profile load completion.{RESET}")
                continue

            elapsed = (datetime.now() - start_time).total_seconds()
            print(f"{GREEN}[OK] Await condition satisfied! Load completed in {elapsed:.2f} seconds.{RESET}")
            print(f"{GREEN}Agent successfully completed the handshake!{RESET}\n")

        elif cmd_name == "reset":
            app_id = None
            for cid in LATEST_REGISTRY.keys():
                if cid.startswith("App#"):
                    app_id = cid
                    break

            if not app_id:
                print(f"{RED}Error: App component not found in registry.{RESET}")
                continue

            print("Resetting profile...")
            await execute_command({
                "type": "dispatchEvent",
                "commandId": "click-reset",
                "target": app_id,
                "event": "click",
                "payload": "#btn-reset"
            })

        else:
            print(f"Unknown command: '{query}'. Try: 'registry', 'ledger', 'load', 'reset'.")

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
