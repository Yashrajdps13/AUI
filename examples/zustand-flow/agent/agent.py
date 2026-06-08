import asyncio
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load local environment variables
load_dotenv()

# Add local SDK path to sys.path before imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../sdk/python")))

from react_agent_bridge import ReactAgentBridge, AgentRunner, BridgeError

# Terminal text colors
RED = "\033[1;31m"
YELLOW = "\033[1;33m"
GREEN = "\033[1;32m"
CYAN = "\033[1;36m"
MAGENTA = "\033[1;35m"
RESET = "\033[0m"

# Initialize bridge server on port 8000
bridge = ReactAgentBridge(host="localhost", port=8000)
runner = AgentRunner(bridge)

def on_connect():
    print(f"\n{GREEN}[Bridge Connected] React application successfully linked!{RESET}")

def on_disconnect():
    print(f"\n{YELLOW}[Bridge Disconnected] React app closed the connection.{RESET}")

def on_state_update(target, val):
    print(f"\n{MAGENTA}[State Updated] {target} = {val}{RESET}")
    print("Agent Query > ", end="", flush=True)

def on_app_log(entry):
    t_str = datetime.fromtimestamp(entry.timestamp / 1000).strftime('%H:%M:%S')
    msg_color = RED if entry.type == "error" else (YELLOW if entry.type == "warn" else GREEN)
    print(f"\n{msg_color}[STREAMED LOG] [{t_str}] [Source: {entry.source}] {entry.message}{RESET}")
    if entry.stack:
        print(f"{msg_color}{entry.stack}{RESET}")
    print("Agent Query > ", end="", flush=True)

bridge.add_listener("connect", on_connect)
bridge.add_listener("disconnect", on_disconnect)
bridge.add_listener("state_update", on_state_update)
bridge.add_listener("log", on_app_log)


# ==========================================
# INTERACTIVE CLI LOOP
# ==========================================
async def cli_loop():
    print(f"\n=======================================================")
    print(f"{CYAN}AUI Zustand Global State & Action Controller{RESET}")
    print("Commands:")
    print("  registry            - Print the current component and store registry")
    print("  ledger              - Query the circular log ledger from the browser")
    print("  login <user> <tok>  - Call the Zustand UserStore.login action via callAction")
    print("  logout              - Call the Zustand UserStore.logout action via callAction")
    print("  increment           - Call the Zustand UserStore.increment action via callAction")
    print("  set-username <val>  - Direct state mutation using setState on UserStore.username")
    print("  set-token <val>     - Direct state mutation using setState on UserStore.token")
    print("  exit / quit         - Shutdown agent")
    print(f"=======================================================\n")

    loop = asyncio.get_event_loop()
    while True:
        query = await loop.run_in_executor(None, lambda: input("Agent Query > ").strip())
        if not query:
            continue
        
        parts = query.split()
        cmd_name = parts[0].lower()

        if cmd_name in ["exit", "quit"]:
            print("Shutting down agent...")
            await bridge.stop()
            sys.exit(0)

        if not bridge.connection:
            print(f"{RED}Error: No React client connected. Please open the frontend in your browser.{RESET}")
            continue

        if cmd_name == "registry":
            print(f"\n{CYAN}--- Active Bridge Registry ---{RESET}")
            for comp in bridge.graph.get_mounted_components():
                print(f"ID: {GREEN}{comp.id}{RESET}")
                print(f"  DisplayName: {comp.display_name}")
                print(f"  State Slots:")
                for slot in comp.state_slots.values():
                    sensitive_flag = f" {RED}[SENSITIVE]{RESET}" if slot.sensitive else ""
                    print(f"    - {slot.key} (hookIndex: {slot.hook_index}){sensitive_flag}")
                if comp.actions:
                    print(f"  Callable Actions:")
                    for action in comp.actions:
                        print(f"    - {action}")
            print(f"{CYAN}------------------------------{RESET}\n")

        elif cmd_name == "ledger":
            try:
                ledger = await bridge.query_ledger(timeout=3.0)
                print(f"\n{CYAN}--- Circular Log Ledger Snapshot (Browser Flight Flight Recorder) ---{RESET}")
                if not ledger:
                    print("Ledger is empty.")
                else:
                    for i, log in enumerate(ledger):
                        t = datetime.fromtimestamp(log.get("timestamp", 0) / 1000).strftime('%H:%M:%S')
                        log_type = log.get("type").upper()
                        color = RED if log_type == "ERROR" else (YELLOW if log_type == "WARN" else GREEN)
                        print(f"[{i:02d}] [{t}] {color}[{log_type}]{RESET} [Source: {log.get('source')}] {log.get('message')}")
                print(f"{CYAN}---------------------------------------------------------------{RESET}\n")
            except Exception as e:
                print(f"{RED}Failed to query ledger snapshot: {e}{RESET}")

        elif cmd_name == "login":
            if len(parts) < 3:
                print(f"{RED}Usage: login <username> <token>{RESET}")
                continue
            username = parts[1]
            token = parts[2]
            print(f"Invoking UserStore.login(username='{username}', token='{token}')...")
            try:
                success = await bridge.call_action("UserStore.login", [username, token])
                if success:
                    print(f"{GREEN}Login action completed successfully.{RESET}")
            except BridgeError as e:
                print(f"{RED}[Command Failed] {e}{RESET}")

        elif cmd_name == "logout":
            print("Invoking UserStore.logout()...")
            try:
                success = await bridge.call_action("UserStore.logout", [])
                if success:
                    print(f"{GREEN}Logout action completed successfully.{RESET}")
            except BridgeError as e:
                print(f"{RED}[Command Failed] {e}{RESET}")

        elif cmd_name == "increment":
            print("Invoking UserStore.increment()...")
            try:
                success = await bridge.call_action("UserStore.increment", [])
                if success:
                    print(f"{GREEN}Increment action completed successfully.{RESET}")
            except BridgeError as e:
                print(f"{RED}[Command Failed] {e}{RESET}")

        elif cmd_name == "set-username":
            if len(parts) < 2:
                print(f"{RED}Usage: set-username <value>{RESET}")
                continue
            val = parts[1]
            print(f"Setting UserStore.username to '{val}'...")
            try:
                success = await bridge.set_state("ZustandStore#UserStore.username", val)
                if success:
                    print(f"{GREEN}Username updated successfully.{RESET}")
            except BridgeError as e:
                print(f"{RED}[Command Failed] {e}{RESET}")

        elif cmd_name == "set-token":
            if len(parts) < 2:
                print(f"{RED}Usage: set-token <value>{RESET}")
                continue
            val = parts[1]
            print(f"Setting UserStore.token to '{val}'...")
            try:
                success = await bridge.set_state("ZustandStore#UserStore.token", val)
                if success:
                    print(f"{GREEN}Token updated successfully.{RESET}")
            except BridgeError as e:
                print(f"{RED}[Command Failed] {e}{RESET}")

        else:
            print(f"Unknown command: '{query}'. Try: 'registry', 'ledger', 'login', 'logout', 'increment', 'set-username', 'set-token'.")


async def main():
    await bridge.start()
    await cli_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down server.")
