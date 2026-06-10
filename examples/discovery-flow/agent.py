import asyncio
import os
import sys
import logging
from dotenv import load_dotenv

# Load local environment variables
load_dotenv()

# Add local SDK path to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../sdk/python")))

from react_agent_bridge import ReactAgentBridge, AgentRunner, BridgeError

# Colors for terminal
RED = "\033[1;31m"
YELLOW = "\033[1;33m"
GREEN = "\033[1;32m"
CYAN = "\033[1;36m"
MAGENTA = "\033[1;35m"
RESET = "\033[0m"

# Initialize bridge
bridge = ReactAgentBridge(host="localhost", port=8000)

async def run_discovery():
    print(f"\n{CYAN}=======================================================")
    print("Starting Passive Discovery Mode Server...")
    print("Open http://localhost:5173 in your browser.")
    print("Perform a full registration flow (Step 1 -> Step 2 -> Step 3 -> Pay).")
    print("Do this 3 or more times to collect sessions.")
    print(f"Press Ctrl+C to stop recording and generate context.{RESET}")
    print(f"{CYAN}=======================================================\n")
    
    await bridge.start()
    session = bridge.discover(
        output_path="./agent-context.md",
        db_path="./discovery.db",
        min_sessions=3,
        inference_interval_hours=24.0
    )
    
    try:
        await session.run_until_interrupted()
    except (KeyboardInterrupt, asyncio.CancelledError):
        print(f"\n{YELLOW}Stopping recording session...{RESET}")
    finally:
        print(f"{GREEN}Generating agent-context.md based on collected corpus...{RESET}")
        result = await session.generate()
        print(result.report)
        await bridge.stop()

async def run_agent():
    print(f"\n{CYAN}=======================================================")
    print("Starting Automated Agent Runner...")
    print("This will execute a query and compile traces.")
    print("Make sure the frontend is open at http://localhost:5173.")
    print(f"=======================================================\n")
    
    # Check if agent-context.md exists
    if not os.path.exists("./agent-context.md"):
        print(f"{YELLOW}Warning: agent-context.md not found. Running without pre-inferred glossary.{RESET}")
    
    runner = AgentRunner(bridge, db_path="./discovery.db")
    await bridge.start()
    
    print("Waiting for browser React connection...")
    await bridge.wait_for_client()
    print(f"{GREEN}Connected! Running registration flow...{RESET}")
    
    query = "Register a Standard Pass for John Doe with email john@test.com, select Networking Dinner, then pay and submit using card 5555666677778888"
    
    try:
        # First execution (LLM planning)
        print(f"\n{YELLOW}--- RUN 1: Direct LLM Planning Execution ---{RESET}")
        res1 = await runner.execute(query)
        print(f"Run 1 completed with status: {res1.get('status')}")
        print(f"LLM Calls Made: {res1.get('llm_calls_made', 0)}")
        
        # Reset state on UI manually or via wait
        print(f"\n{CYAN}Please click the 'Reset Form' button in the browser UI, then press Enter to execute Run 2.{RESET}")
        await asyncio.get_event_loop().run_in_executor(None, input)
        
        # Second execution (Replaying via Golden Trace - Zero LLM Calls)
        print(f"\n{YELLOW}--- RUN 2: Replaying via Golden Trace (Accelerated) ---{RESET}")
        res2 = await runner.execute(query)
        print(f"Run 2 completed with status: {res2.get('status')}")
        print(f"LLM Calls Made: {res2.get('llm_calls_made', 0)}")
        
        if res2.get('llm_calls_made', 1) == 0:
            print(f"\n{GREEN}Success! Golden Trace Replay executed with 0 LLM calls!{RESET}")
        else:
            print(f"\n{RED}Golden Trace did not replay. Check preconditions and constraints.{RESET}")
            
    except Exception as e:
        print(f"{RED}Agent runner encountered an error: {e}{RESET}")
    finally:
        await bridge.stop()

def main():
    print(f"{CYAN}Welcome to TechConf Registration Hub Discovery Playground!{RESET}")
    print("Select an operation mode:")
    print("  1. Run passive discovery server (Record sessions and build agent-context.md)")
    print("  2. Run automated agent runner (Execute goals and observe Golden Trace replay)")
    print("  3. Exit")
    
    choice = input("Select option (1-3): ").strip()
    if choice == '1':
        asyncio.run(run_discovery())
    elif choice == '2':
        asyncio.run(run_agent())
    else:
        print("Goodbye!")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    main()
