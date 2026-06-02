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
        ack = await asyncio.wait_for(COMMAND_FUTURE, timeout=3.0)
        return ack.get("success", False)
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
                print(f"\n{RED}[STREAMED ERROR LOG] [{t_str}] [Source: {entry.get('source')}] {entry.get('message')}{RESET}")
                if entry.get("stack"):
                    print(f"{RED}{entry.get('stack')}{RESET}")
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
    print(f"{CYAN}AUI Error Logging & Activity Ledger Playground{RESET}")
    print("Commands:")
    print("  ledger          - Query the circular log ledger from the browser")
    print("  error-submit    - Submit form with invalid email (causes validation error)")
    print("  error-render    - Click the button to throw an uncaught rendering error")
    print("  error-promise   - Click the button to throw an unhandled promise rejection")
    print("  exit / quit     - Shutdown agent")
    print(f"=======================================================\n")

    loop = asyncio.get_event_loop()
    while True:
        query = await loop.run_in_executor(None, lambda: input("Agent Query > ").strip())
        if not query:
            continue
        if query.lower() in ["exit", "quit"]:
            print("Shutting down agent...")
            sys.exit(0)

        if not ACTIVE_CONNECTION:
            print(f"{RED}Error: No React client connected. Please open the frontend in your browser.{RESET}")
            continue

        app_id = None
        for cid in LATEST_REGISTRY.keys():
            if cid.startswith("App#"):
                app_id = cid
                break

        if not app_id:
            print(f"{RED}Error: App component not found in registry.{RESET}")
            continue

        if query.lower() == "ledger":
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

        elif query.lower() == "error-submit":
            # 1. Fill email without @ (invalid format)
            print("Filling invalid email address...")
            await execute_command({
                "type": "setState",
                "commandId": "fill-email",
                "target": f"{app_id}.email",
                "value": "alice_invalid_email"
            })
            # 2. Fill feedback
            await execute_command({
                "type": "setState",
                "commandId": "fill-feedback",
                "target": f"{app_id}.feedback",
                "value": "Hello world from the agent!"
            })
            # 3. Click submit (triggers validation console.error in App.jsx)
            print("Clicking submit button...")
            await execute_command({
                "type": "dispatchEvent",
                "commandId": "click-submit",
                "target": app_id,
                "event": "click",
                "payload": "#btn-submit"
            })

        elif query.lower() == "error-render":
            # Click rendering exception button (causes App buggy component render error)
            print("Triggering component rendering exception...")
            await execute_command({
                "type": "dispatchEvent",
                "commandId": "click-crash",
                "target": app_id,
                "event": "click",
                "payload": "#btn-crash"
            })

        elif query.lower() == "error-promise":
            # Click unhandled promise rejection button
            print("Triggering unhandled promise rejection...")
            await execute_command({
                "type": "dispatchEvent",
                "commandId": "click-reject",
                "target": app_id,
                "event": "click",
                "payload": "#btn-reject"
            })

        else:
            print(f"Unknown command: '{query}'. Try: 'ledger', 'error-submit', 'error-render', or 'error-promise'.")

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
