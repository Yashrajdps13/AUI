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
- For any dispatchEvent command, the "target" field MUST ALWAYS be the Component ID (e.g. "App#r8"). The "payload" field MUST contain the CSS selector string of the element (e.g. "#btn-unlock", "#btn-run-diag", or "#pin-input"). NEVER put a CSS selector string in the "target" field.
- To unlock the console: you MUST first set the state of "App#r8.pinInput" to "7788" using setState, AND then dispatch a click event to "App#r8" with payload "#btn-unlock". You cannot change settings or run diagnostics if you don't click "#btn-unlock" to unlock the console first.
- Read state slot descriptions carefully. For example, to unlock configurations, look at the description of isUnlocked or pinInput to find instructions (e.g. what PIN to enter).
- To input text or PIN, prefer using setState for "pinInput", "ipAddress", "apiSecret", etc.
- To execute actions like clicking "Unlock Console" or "Run Diagnostics", dispatch a click event to the target Component ID with the button's selector as the payload.
- If you start diagnostics, the system status slot (e.g. 'diagnosticStatus') will enter a 'running' phase. You must wait for it to finish!"""

runner = AgentRunner(
    bridge=bridge,
    model=PLANNER_MODEL,
    business_context=business_context,
    max_steps=20
)

async def cli_loop():
    print(f"\n=======================================================")
    print(f"{CYAN}AUI Smart Device Dashboard Agent Console{RESET}")
    print("Example Queries:")
    print("  1. Unlock settings using PIN 7788, set critical alert threshold to 85, change mode to boost, and run self-test")
    print("  2. Enter the PIN code 7788 and click the unlock button")
    print("  3. Set operational mode to maintain and set IP to 192.168.1.50")
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
