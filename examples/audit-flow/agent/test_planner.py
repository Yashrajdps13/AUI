import asyncio
import os
import sys
import logging

# Add local SDK path to sys.path before imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../sdk/python")))

from react_agent_bridge import ReactAgentBridge, GoalDirectedPlanner, Goal, GoalCondition, LiteLLMAdapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("litellm").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Terminal text colors
RED = "\033[1;31m"
GREEN = "\033[1;32m"
CYAN = "\033[1;36m"
RESET = "\033[0m"



async def main():
    # 1. Retrieve model from environment, defaulting to ollama/qwen2.5:7b
    model = os.environ.get("PLANNER_MODEL", "ollama/qwen2.5:7b")
    
    # 2. Verify GEMINI_API_KEY is present only if running a Gemini model
    if "gemini" in model.lower() and not os.environ.get("GEMINI_API_KEY") and not os.environ.get("LITELLM_API_KEY"):
        print(f"{RED}Error: GEMINI_API_KEY or LITELLM_API_KEY must be set when using a Gemini model ({model}).{RESET}")
        sys.exit(1)

    print(f"{CYAN}Starting ReactAgentBridge server at ws://localhost:8000 using model '{model}'...{RESET}")
    adapter = LiteLLMAdapter(model=model)
    bridge = ReactAgentBridge(host="localhost", port=8000, llm_adapter=adapter)
    await bridge.start()
    
    print(f"{CYAN}Waiting for browser React application connection...{RESET}")
    await bridge.wait_for_client()
    
    # 2. Retrieve the mounted App ID
    app_id = None
    for comp in bridge.graph.get_mounted_components():
        if comp.display_name == "App":
            app_id = comp.id
            
    if not app_id:
        print(f"{RED}Error: 'App' component not detected in mounted registry.{RESET}")
        await bridge.stop()
        sys.exit(1)
        
    # 3. Instantiate GoalDirectedPlanner (wires LiteLLMAdapter internally)
    planner = GoalDirectedPlanner(bridge)
    
    # 4. Prompt for a natural language query or use the default one
    print(f"\nEnter a natural language query for the planner (e.g. 'Login with username agent_john, password test123')")
    loop = asyncio.get_event_loop()
    query = await loop.run_in_executor(None, lambda: input("Planner Query [Login with username agent_john, password test123] > ").strip())
    if not query:
        query = "Login with username agent_john, password test123"

    print(f"\n{CYAN}--- Goal Intake Phase ---{RESET}")
    print(f"Compiling user query: '{query}'...")
    try:
        goal = await planner.intake(query)
        print(f"{GREEN}Successfully compiled Goal!{RESET}")
        print(f"  Description: {goal.description}")
        print(f"  Success Conditions:")
        for cond in goal.success_conditions:
            print(f"    - {cond.target} {cond.operator} {cond.value}")
        print(f"  Failure Conditions:")
        for cond in goal.failure_conditions:
            print(f"    - {cond.target} {cond.operator} {cond.value}")
    except Exception as e:
        print(f"\n{RED}[Error] Failed to compile goal via intake: {e}{RESET}")
        await bridge.stop()
        sys.exit(1)
    
    print(f"\n{CYAN}Executing Goal: {goal.description}{RESET}")
    try:
        result = await planner.execute(goal)
        if result.success:
            print(f"\n{GREEN}[Success] Goal accomplished! Steps taken: {result.steps_executed}{RESET}")
        else:
            print(f"\n{RED}[Failed] Planner loop finished without satisfying conditions. Error: {result.error_message}{RESET}")
    except Exception as e:
        print(f"\n{RED}[Error] Planner execution encountered exception: {e}{RESET}")
    finally:
        await bridge.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down planner test.")
