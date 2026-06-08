import asyncio
import os
import sys

# Add local SDK path to sys.path before imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../sdk/python")))

from react_agent_bridge import ReactAgentBridge, AgentRunner

# Terminal text colors
RED = "\033[1;31m"
YELLOW = "\033[1;33m"
GREEN = "\033[1;32m"
CYAN = "\033[1;36m"
RESET = "\033[0m"

# Global configuration
PLANNER_MODEL = os.environ.get("PLANNER_MODEL", "ollama/qwen2.5:7b")

# Initialize bridge server on port 8000
bridge = ReactAgentBridge(host="localhost", port=8000)

def on_connect():
    print(f"\n{GREEN}[Bridge Connected] React application successfully linked!{RESET}")

def on_disconnect():
    print(f"\n{YELLOW}[Bridge Disconnected] React app closed the connection.{RESET}")

bridge.add_listener("connect", on_connect)
bridge.add_listener("disconnect", on_disconnect)

business_context = """CRITICAL RULES FOR COMMAND SELECTION:
- For any dispatchEvent command, the "target" field MUST ALWAYS be the Component ID (e.g. "SecurityPanel#r5"). The "payload" field MUST contain the CSS selector string of the element (e.g. "#tab-security" or "#btn-save-security"). NEVER put a CSS selector string in the "target" field.
- Always prefer dispatchEvent click commands for UI-based actions (such as clicking navigation tab buttons like '#tab-security', '#tab-controls', '#tab-status').
- Switching tabs changes the active component registry! Remember that components like 'SecurityPanel' or 'ControlsPanel' will only mount and show their state slots AFTER you click their corresponding tab button.
- Only use setState for inputs (like apiSecret, securityPin, newDevice)."""

runner = AgentRunner(
    bridge=bridge,
    model=PLANNER_MODEL,
    business_context=business_context,
    max_steps=20
)

async def cli_loop():
    print(f"\n=======================================================")
    print(f"{CYAN}AUI Smart Routing & Status Signal Agent{RESET}")
    print("Example Queries:")
    print("  1. Switch to Device Controls, add Smart Thermostat, adjust speed to 75")
    print("  2. Go to Security Settings, set PIN to 1234, save settings")
    print("  3. Navigate to Agent Status tab")
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

        await runner.execute(query)

async def main():
    await bridge.start()
    print("Waiting for browser React application connection on port 8000...")
    await cli_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down server.")
