import asyncio
import json
import logging
import os
import sys
from datetime import datetime

# Add local SDK path to sys.path before imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../sdk/python")))

from react_agent_bridge import ReactAgentBridge, AgentRunner, BridgeError

# Terminal text colors
RED = "\033[1;31m"
YELLOW = "\033[1;33m"
GREEN = "\033[1;32m"
CYAN = "\033[1;36m"
RESET = "\033[0m"

# Global configuration
PLANNER_MODEL = os.environ.get("PLANNER_MODEL", "ollama/qwen2.5:7b")

# Initialize bridge server with LiteLLMAdapter
bridge = ReactAgentBridge(host="localhost", port=8000)

def on_connect():
    print(f"\n{GREEN}[Bridge Connected] React application successfully linked!{RESET}")

def on_disconnect():
    print(f"\n{YELLOW}[Bridge Disconnected] React app closed the connection.{RESET}")

bridge.add_listener("connect", on_connect)
bridge.add_listener("disconnect", on_disconnect)

business_context = """CRITICAL RULES FOR COMMAND SELECTION:
- Always prefer dispatchEvent click commands for UI-based actions (such as clicking buttons).
- Only use setState for simple user inputs/text fields (like username, ssn/password)."""

runner = AgentRunner(
    bridge=bridge,
    model=PLANNER_MODEL,
    business_context=business_context,
    max_steps=20
)

# ==========================================
# INTERACTIVE CLI LOOP
# ==========================================
async def cli_loop():
    print(f"\n=======================================================")
    print(f"{CYAN}AUI Command Audit Log Playground Agent (SDK version){RESET}")
    print("Commands:")
    print("  registry    - Print the active component registry schema")
    print("  audit       - Query the append-only command audit log from the browser")
    print("  fill        - Set username and SSN on App (SSN should be redacted)")
    print("  login       - Call Zustand store login action (Arguments should be redacted)")
    print("  click       - Dispatch click event on submit button")
    print("  Or enter any natural language query for the planner...")
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

        app_id = None
        for comp in bridge.graph.get_mounted_components():
            if comp.id.startswith("App#") or comp.id.startswith("App:"):
                app_id = comp.id

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
                    print(f"  Actions:")
                    for action in comp.actions:
                        print(f"    - {action}")
            print(f"{CYAN}------------------------------{RESET}\n")

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
                print(f"{RED}Failed to query command audit log: {e}{RESET}")

        elif cmd_name == "fill":
            if not app_id:
                print(f"{RED}Error: App component not found in registry.{RESET}")
                continue
            print(f"Setting username and sensitive SSN on App ({app_id})...")
            try:
                await bridge.set_state(f"{app_id}.username", "hacker_agent")
                await bridge.set_state(f"{app_id}.ssn", "999-88-7777")
                print(f"{GREEN}State mutation commands sent! Query the browser 'audit' to check redaction.{RESET}")
            except BridgeError as e:
                print(f"{RED}[Failed] {e}{RESET}")

        elif cmd_name == "login":
            print("Invoking Zustand AuthStore.login action with credentials...")
            try:
                await bridge.call_action("AuthStore.login", ["admin", "supersecret123"])
                print(f"{GREEN}Action command sent! Query 'audit' to check redaction of action arguments.{RESET}")
            except BridgeError as e:
                print(f"{RED}[Failed] {e}{RESET}")

        elif cmd_name == "click":
            if not app_id:
                print(f"{RED}Error: App component not found in registry.{RESET}")
                continue
            print("Clicking submit button...")
            try:
                await bridge.dispatch_event(app_id, "click", "#btn-submit")
                print(f"{GREEN}Click dispatchEvent command completed.{RESET}")
            except BridgeError as e:
                print(f"{RED}[Failed] {e}{RESET}")

        else:
            await runner.execute(query)

async def main():
    await bridge.start()
    await cli_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down server.")
