import asyncio
import json
import sys
from datetime import datetime
from typing import Dict, Any, Optional

# Global connection reference and latest registry cache
ACTIVE_CONNECTION = None
LATEST_REGISTRY: Dict[str, Any] = {}
COMMAND_FUTURE: Optional[asyncio.Future] = None
AUDIT_FUTURE: Optional[asyncio.Future] = None

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
        ack = await asyncio.wait_for(COMMAND_FUTURE, timeout=5.0)
        success = ack.get("success", False)
        if not success:
            print(f"{RED}[Failed] {ack.get('error', 'Unknown error')}{RESET}")
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
    global ACTIVE_CONNECTION, LATEST_REGISTRY, COMMAND_FUTURE, AUDIT_FUTURE
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

            elif msg_type == "auditLogSnapshot":
                if AUDIT_FUTURE and not AUDIT_FUTURE.done():
                    AUDIT_FUTURE.set_result(data)

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
    global AUDIT_FUTURE
    print(f"\n=======================================================")
    print(f"{CYAN}AUI Command Audit Log Playground Agent{RESET}")
    print("Commands:")
    print("  registry    - Print the active component registry schema")
    print("  audit       - Query the append-only command audit log from the browser")
    print("  fill        - Set username and SSN on App (SSN should be redacted)")
    print("  login       - Call Zustand store login action (Arguments should be redacted)")
    print("  click       - Dispatch click event on submit button")
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

        app_id = None
        for cid in LATEST_REGISTRY.keys():
          if cid.startswith("App#") or cid.startswith("App:"):
            app_id = cid

        if cmd_name == "registry":
            print(f"\n{CYAN}--- Active Bridge Registry ---{RESET}")
            for comp_id, comp in LATEST_REGISTRY.items():
                print(f"ID: {GREEN}{comp_id}{RESET}")
                print(f"  DisplayName: {comp.get('displayName')}")
                print(f"  State Slots:")
                for slot in comp.get("stateSlots", []):
                    sensitive_flag = f" {RED}[SENSITIVE]{RESET}" if slot.get("sensitive") else ""
                    print(f"    - {slot.get('key')} (hookIndex: {slot.get('hookIndex')}){sensitive_flag}")
                if comp.get("actions"):
                  print(f"  Actions:")
                  for action in comp.get("actions", []):
                    print(f"    - {action}")
            print(f"{CYAN}------------------------------{RESET}\n")

        elif cmd_name == "audit":
            AUDIT_FUTURE = asyncio.get_running_loop().create_future()
            await ACTIVE_CONNECTION.send(json.dumps({
                "type": "queryAuditLog",
                "commandId": "get-audit-snapshot"
            }))
            
            try:
                snapshot = await asyncio.wait_for(AUDIT_FUTURE, timeout=3.0)
                audit_log = snapshot.get("auditLog", [])
                print(f"\n{CYAN}--- Command Audit Log (Append-Only) ---{RESET}")
                if not audit_log:
                    print("Audit log is empty.")
                else:
                    for i, entry in enumerate(audit_log):
                        t = datetime.fromtimestamp(entry.get("timestamp", 0) / 1000).strftime('%H:%M:%S')
                        success_str = f"{GREEN}SUCCESS{RESET}" if entry.get("success") else f"{RED}FAILED{RESET}"
                        val_str = json.dumps(entry.get("value"))
                        err_str = f" | Error: {entry.get('error')}" if entry.get("error") else ""
                        print(f"[{i:02d}] [{t}] {success_str} | Command: {entry.get('type')} | Target: {entry.get('target')} | Value: {val_str}{err_str}")
                print(f"{CYAN}---------------------------------------{RESET}\n")
            except asyncio.TimeoutError:
                print(f"{RED}Failed to query command audit log snapshot (timeout).{RESET}")
            finally:
                AUDIT_FUTURE = None

        elif cmd_name == "fill":
            if not app_id:
                print(f"{RED}Error: App component not found in registry.{RESET}")
                continue
            print(f"Setting username and sensitive SSN on App ({app_id})...")
            
            # 1. Set username (non-sensitive)
            await execute_command({
                "type": "setState",
                "commandId": "set-username",
                "target": f"{app_id}.username",
                "value": "hacker_agent"
            })
            
            # 2. Set SSN (sensitive, should be redacted to [REDACTED])
            await execute_command({
                "type": "setState",
                "commandId": "set-ssn",
                "target": f"{app_id}.ssn",
                "value": "999-88-7777"
            })
            print(f"{GREEN}State mutation commands sent! Query the browser 'audit' to check redaction.{RESET}")

        elif cmd_name == "login":
            print("Invoking Zustand AuthStore.login action with credentials...")
            await execute_command({
                "type": "callAction",
                "commandId": "call-login",
                "target": "AuthStore.login",
                "args": ["admin", "supersecret123"]
            })
            print(f"{GREEN}Action command sent! Query 'audit' to check redaction of action arguments.{RESET}")

        elif cmd_name == "click":
            if not app_id:
                print(f"{RED}Error: App component not found in registry.{RESET}")
                continue
            print("Clicking submit button...")
            await execute_command({
                "type": "dispatchEvent",
                "commandId": "click-submit",
                "target": app_id,
                "event": "click",
                "payload": "#btn-submit"
            })
            print(f"{GREEN}Click dispatchEvent command completed.{RESET}")

        else:
            print(f"Unknown command: '{query}'. Try: 'registry', 'audit', 'fill', 'login', 'click'.")

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
