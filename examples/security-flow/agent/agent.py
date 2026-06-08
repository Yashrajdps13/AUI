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

def on_app_log(entry):
    t_str = datetime.fromtimestamp(entry.timestamp / 1000).strftime('%H:%M:%S')
    msg_color = RED if entry.type == "error" else (YELLOW if entry.type == "warn" else GREEN)
    print(f"\n{msg_color}[STREAMED LOG] [{t_str}] [Source: {entry.source}] {entry.message}{RESET}")
    if entry.stack:
        print(f"{msg_color}{entry.stack}{RESET}")
    print("Agent Query > ", end="", flush=True)

bridge.add_listener("connect", on_connect)
bridge.add_listener("disconnect", on_disconnect)
bridge.add_listener("log", on_app_log)


# ==========================================
# INTERACTIVE CLI LOOP
# ==========================================
async def cli_loop():
    print(f"\n=======================================================")
    print(f"{CYAN}AUI Write-Side Security Scoping Playground{RESET}")
    print("Commands:")
    print("  registry    - Print the active component registry schema")
    print("  ledger      - Query the circular log ledger from the browser")
    print("  audit       - Query the append-only command audit log from the browser")
    print("  fill        - Set email and notes on FormComponent (Allowed Targets)")
    print("  escalate    - Attempt to toggle admin or click escalate on AdminPanel (Blocked Target)")
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
            await bridge.stop()
            sys.exit(0)

        if not bridge.connection:
            print(f"{RED}Error: No React client connected. Please open the frontend in your browser.{RESET}")
            continue

        form_id = None
        admin_id = None
        for comp in bridge.graph.get_mounted_components():
            if comp.id.startswith("FormComponent#"):
                form_id = comp.id
            elif comp.id.startswith("AdminPanel#"):
                admin_id = comp.id

        if cmd_name == "registry":
            print(f"\n{CYAN}--- Active Bridge Registry ---{RESET}")
            for comp in bridge.graph.get_mounted_components():
                print(f"ID: {GREEN}{comp.id}{RESET}")
                print(f"  DisplayName: {comp.display_name}")
                print(f"  State Slots:")
                for slot in comp.state_slots.values():
                    sensitive_flag = f" {RED}[SENSITIVE]{RESET}" if slot.sensitive else ""
                    print(f"    - {slot.key} (hookIndex: {slot.hook_index}){sensitive_flag}")
            print(f"{CYAN}------------------------------{RESET}\n")

        elif cmd_name == "ledger":
            try:
                ledger = await bridge.query_ledger(timeout=3.0)
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
            except Exception as e:
                print(f"{RED}Failed to query ledger snapshot: {e}{RESET}")

        elif cmd_name == "audit":
            try:
                audit_log = await bridge.query_audit_log(timeout=3.0)
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
            except Exception as e:
                print(f"{RED}Failed to query command audit log snapshot: {e}{RESET}")

        elif cmd_name == "fill":
            if not form_id:
                print(f"{RED}Error: FormComponent not found in registry.{RESET}")
                continue
            print(f"Filling email and notes on allowlisted FormComponent ({form_id})...")
            try:
                success_email = await bridge.set_state(f"{form_id}.email", "guest_user@example.com")
                success_notes = await bridge.set_state(f"{form_id}.notes", "This write should succeed.")
                if success_email and success_notes:
                    print(f"{GREEN}Public form fields modified successfully!{RESET}")
            except BridgeError as e:
                print(f"{RED}[Blocked/Failed] {e}{RESET}")

        elif cmd_name == "escalate":
            if not admin_id:
                print(f"{RED}Error: AdminPanel component not found in registry.{RESET}")
                continue

            print(f"\n{YELLOW}[Attempt 1] Attempting to set isAdmin to True via setState...{RESET}")
            try:
                await bridge.set_state(f"{admin_id}.isAdmin", True)
            except BridgeError as e:
                print(f"{RED}[Blocked/Failed] {e}{RESET}")

            print(f"\n{YELLOW}[Attempt 2] Attempting to trigger elevate click event on #btn-escalate...{RESET}")
            try:
                await bridge.dispatch_event(admin_id, "click", "#btn-escalate")
            except BridgeError as e:
                print(f"{RED}[Blocked/Failed] {e}{RESET}")
            print(f"{YELLOW}Check logs or query the browser 'ledger' to audit the blocked mutation alerts.{RESET}\n")

        else:
            print(f"Unknown command: '{query}'. Try: 'registry', 'ledger', 'fill', 'escalate'.")


async def main():
    await bridge.start()
    await cli_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down server.")
