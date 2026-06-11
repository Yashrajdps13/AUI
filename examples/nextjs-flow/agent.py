#!/usr/bin/env python
"""
================================================================================
React Agent Bridge — Next.js App Router Direct API Walkthrough
================================================================================

This walkthrough demonstrates the core capabilities of the react-agent-bridge
WebSocket API with Next.js App Router. It runs a fully deterministic, hardcoded
interaction flow (navigating pages, mutating state, checking writeable rules,
and retrieving ledgers) directly using the ReactAgentBridge API.

NO LLM CONFIGURATION IS REQUIRED TO RUN THIS WALKTHROUGH.

TO RUN:
1. Start the Next.js Frontend:
   cd examples/nextjs-flow
   npm run dev

2. Run this script in a separate terminal:
   python agent.py
"""

import asyncio
import sys
import time
from typing import Optional

from react_agent_bridge.core.client import ReactAgentBridge
from react_agent_bridge.core.exceptions import RuleViolationError

# Color formatting for terminal outputs
GREEN = "\033[1;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[1;36m"
MAGENTA = "\033[1;35m"
RED = "\033[1;31m"
RESET = "\033[0m"


async def async_input(prompt: str = "") -> str:
    return await asyncio.get_event_loop().run_in_executor(None, input, prompt)


async def prompt_step(step_name: str, description: str):
    import os
    print(f"\n{MAGENTA}>>> Walkthrough Step: {step_name}{RESET}")
    print(f"    Description: {CYAN}{description}{RESET}")
    if os.environ.get("NON_INTERACTIVE") == "1" or "--non-interactive" in sys.argv:
        print("    [Non-interactive mode] Proceeding automatically...")
        await asyncio.sleep(0.5)
        return
    await async_input("    Press [Enter] to execute this step...")


def get_first_registered_component(bridge: ReactAgentBridge, display_name: str) -> Optional[str]:
    """Helper to find the first mounted component ID by display name."""
    components = bridge.graph.get_mounted_components()
    for comp in components:
        if comp.display_name == display_name:
            return comp.id
    return None


async def wait_for_pathname(bridge: ReactAgentBridge, target_path: str, timeout: float = 5.0) -> bool:
    """Helper to poll and wait for the pathname to change in the state graph."""
    start = time.time()
    while time.time() - start < timeout:
        env_pathname = bridge.graph.get_slot_value("__context__#env.pathname")
        if env_pathname == target_path:
            return True
        await asyncio.sleep(0.1)
    return False


async def wait_for_component_mounted(bridge: ReactAgentBridge, display_name: str, timeout: float = 5.0) -> bool:
    """Helper to poll and wait for a component to mount in the registry."""
    start = time.time()
    while time.time() - start < timeout:
        if get_first_registered_component(bridge, display_name) is not None:
            return True
        await asyncio.sleep(0.1)
    return False


async def main():
    print("================================================================================")
    print("      Starting react-agent-bridge Deterministic Next.js Walkthrough")
    print("================================================================================\n")

    host = "localhost"
    port = 8000

    # -------------------------------------------------------------
    # CONNECTION
    # -------------------------------------------------------------
    bridge = ReactAgentBridge(host=host, port=port)
    await bridge.start()
    print(f"Connecting to React application on ws://{host}:{port}...")
    print(f"{YELLOW}[TIP] Make sure your dev server is running (npm run dev) and http://localhost:3000 is open in your browser!{RESET}")
    
    try:
        # Blocks until browser tab links with bridge
        await asyncio.wait_for(bridge.wait_for_client(), timeout=30.0)
        print(f"{GREEN}[SUCCESS] React application linked successfully!{RESET}")
        
        # Wait a short moment for registry deltas to sync
        await asyncio.sleep(1.5)
        
    except asyncio.TimeoutError:
        print(f"\n{RED}[ERROR] Connection timed out. Did you open http://localhost:3000 in your browser?{RESET}")
        await bridge.stop()
        sys.exit(1)

    try:
        # Print active route
        pathname = bridge.graph.get_slot_value("__context__#env.pathname") or "/"
        print(f"\nInitial State:")
        print(f"  Current Route Pathname: {GREEN}{pathname}{RESET}")
        print(f"  Active Components:     {GREEN}{len(bridge.graph.get_mounted_components())}{RESET}")

        # Resolve HomePage ID dynamically
        homepage_id = get_first_registered_component(bridge, "HomePage")
        if not homepage_id:
            print(f"{RED}[ERROR] HomePage component not found in registry.{RESET}")
            await bridge.stop()
            return

        # -------------------------------------------------------------
        # STEP 1: Navigate to Counter Page
        # -------------------------------------------------------------
        await prompt_step(
            "Navigate to /counter Page",
            "Dispatches a click event on `#link-counter` via the `HomePage` Client Component. "
            "This routes the Next.js application to the Counter page."
        )
        
        print("Sending click event for `#link-counter`...")
        # HomePage wraps the main landing view, so we target it to dispatch the click
        await bridge.dispatch_event(homepage_id, "click", "#link-counter")
        
        print("Waiting for page transition...")
        if await wait_for_pathname(bridge, "/counter"):
            print(f"{GREEN}[SUCCESS] Page transitioned! Pathname: /counter{RESET}")
        else:
            print(f"{YELLOW}[WARNING] Pathname did not update in time. Current pathname: {bridge.graph.get_slot_value('__context__#env.pathname')}{RESET}")

        print("Waiting for CounterClient component to register...")
        if await wait_for_component_mounted(bridge, "CounterClient"):
            counter_id = get_first_registered_component(bridge, "CounterClient")
            print(f"{GREEN}[SUCCESS] CounterClient registered with ID: {counter_id}{RESET}")
        else:
            print(f"{RED}[ERROR] CounterClient component failed to mount/register.{RESET}")
            return

        # -------------------------------------------------------------
        # STEP 2: Increment Counter
        # -------------------------------------------------------------
        await prompt_step(
            "Increment Counter Value",
            "Dispatches 5 sequential click events on `#counter-increment` to modify the `count` state slot in real-time."
        )
        
        counter_id = get_first_registered_component(bridge, "CounterClient")
        initial_val = bridge.graph.get_slot_value(f"{counter_id}.count") or 0
        print(f"Initial Counter State: {CYAN}{initial_val}{RESET}")
        
        for i in range(1, 6):
            print(f"  Dispatching click #{i} on `#counter-increment`...")
            await bridge.dispatch_event(counter_id, "click", "#counter-increment")
            await asyncio.sleep(0.3)  # Wait for React to render and update the local graph cache
            current_val = bridge.graph.get_slot_value(f"{counter_id}.count")
            print(f"  Current Counter State: {GREEN}{current_val}{RESET}")

        final_val = bridge.graph.get_slot_value(f"{counter_id}.count")
        print(f"{GREEN}[SUCCESS] Final Counter Value: {final_val} (Increased from {initial_val}){RESET}")

        # -------------------------------------------------------------
        # STEP 3: Navigate back to Home Page
        # -------------------------------------------------------------
        await prompt_step(
            "Navigate back to HomePage",
            "Dispatches a click event on `#link-home` to return to the root route."
        )
        
        # Resolve CounterPage ID dynamically
        print("Waiting for CounterPage component to register...")
        if await wait_for_component_mounted(bridge, "CounterPage"):
            counter_page_id = get_first_registered_component(bridge, "CounterPage")
        else:
            print(f"{RED}[ERROR] CounterPage component failed to mount/register.{RESET}")
            return

        print("Sending click event for `#link-home`...")
        await bridge.dispatch_event(counter_page_id, "click", "#link-home")
        
        print("Waiting for page transition...")
        if await wait_for_pathname(bridge, "/"):
            print(f"{GREEN}[SUCCESS] Page transitioned! Pathname: /{RESET}")
        else:
            print(f"{YELLOW}[WARNING] Pathname did not update. Current: {bridge.graph.get_slot_value('__context__#env.pathname')}{RESET}")

        # -------------------------------------------------------------
        # STEP 4: Navigate to Read-only Page
        # -------------------------------------------------------------
        await prompt_step(
            "Navigate to /readonly Page",
            "Dispatches a click event on `#link-readonly` to open the read-only slider page."
        )
        
        # Resolve HomePage ID dynamically again since it remounts on return
        print("Waiting for HomePage component to register...")
        if await wait_for_component_mounted(bridge, "HomePage"):
            homepage_id = get_first_registered_component(bridge, "HomePage")
        else:
            print(f"{RED}[ERROR] HomePage component failed to mount/register.{RESET}")
            return

        print("Sending click event for `#link-readonly`...")
        await bridge.dispatch_event(homepage_id, "click", "#link-readonly")
        
        print("Waiting for page transition...")
        if await wait_for_pathname(bridge, "/readonly"):
            print(f"{GREEN}[SUCCESS] Page transitioned! Pathname: /readonly{RESET}")
        else:
            print(f"{YELLOW}[WARNING] Pathname did not update. Current: {bridge.graph.get_slot_value('__context__#env.pathname')}{RESET}")

        print("Waiting for ReadonlyRateClient component to register...")
        if await wait_for_component_mounted(bridge, "ReadonlyRateClient"):
            readonly_id = get_first_registered_component(bridge, "ReadonlyRateClient")
            print(f"{GREEN}[SUCCESS] ReadonlyRateClient registered with ID: {readonly_id}{RESET}")
        else:
            print(f"{RED}[ERROR] ReadonlyRateClient component failed to mount/register.{RESET}")
            return

        # -------------------------------------------------------------
        # STEP 5: Verify Write-Protection Rule Enforcement
        # -------------------------------------------------------------
        await prompt_step(
            "Verify Write-Protection Safety Rule",
            "Attempts a direct `setState` call on the read-only slot `efficiencyRate`. "
            "This operation should be blocked immediately on the backend by the Rules Engine."
        )
        
        readonly_id = get_first_registered_component(bridge, "ReadonlyRateClient")
        rate_val = bridge.graph.get_slot_value(f"{readonly_id}.efficiencyRate")
        print(f"Read-only efficiencyRate is currently: {CYAN}{rate_val}%{RESET}")
        print("Attempting to write direct state mutation value = 99 to `efficiencyRate`...")
        
        try:
            await bridge.set_state(f"{readonly_id}.efficiencyRate", 99)
            print(f"{RED}[FAILURE] Direct mutation of write-protected slot succeeded. This should not happen!{RESET}")
        except RuleViolationError as e:
            print(f"{GREEN}[SUCCESS] Direct mutation blocked by Rules Engine!{RESET}")
            print(f"  Violation Details: {YELLOW}{e}{RESET}")

        # -------------------------------------------------------------
        # STEP 6: Navigate back to Home Page
        # -------------------------------------------------------------
        await prompt_step(
            "Navigate back to HomePage",
            "Dispatches a click event on `#link-home` to return to the root route."
        )
        
        # Resolve ReadonlyPage ID dynamically
        print("Waiting for ReadonlyPage component to register...")
        if await wait_for_component_mounted(bridge, "ReadonlyPage"):
            readonly_page_id = get_first_registered_component(bridge, "ReadonlyPage")
        else:
            print(f"{RED}[ERROR] ReadonlyPage component failed to mount/register.{RESET}")
            return

        print("Sending click event for `#link-home`...")
        await bridge.dispatch_event(readonly_page_id, "click", "#link-home")
        
        print("Waiting for page transition...")
        if await wait_for_pathname(bridge, "/"):
            print(f"{GREEN}[SUCCESS] Page transitioned! Pathname: /{RESET}")
        else:
            print(f"{YELLOW}[WARNING] Pathname did not update. Current: {bridge.graph.get_slot_value('__context__#env.pathname')}{RESET}")

        # -------------------------------------------------------------
        # STEP 7: Inspect Command Audit Log & Console logs
        # -------------------------------------------------------------
        await prompt_step(
            "Inspect Command Audit Log & Ledgers",
            "Queries the append-only command audit log and the browser console log ledger recorded by the bridge."
        )
        
        audit_logs = await bridge.query_audit_log()
        print("\n=================== Append-Only Command Audit Log ===================")
        if not audit_logs:
            print("No audit logs found.")
        else:
            for log in audit_logs:
                status = "SUCCESS" if log.get("success") else f"FAILED: {log.get('error')}"
                ts = time.strftime('%H:%M:%S', time.localtime(log.get("timestamp") / 1000.0))
                print(f"[{ts}] {log.get('type')} on {log.get('target')} -> {status}")
                if log.get("value") is not None:
                    print(f"  Value: {log.get('value')}")
        print("=====================================================================\n")

        browser_logs = await bridge.query_ledger()
        print("\n====================== Browser Console Logs ======================")
        if not browser_logs:
            print("No logs in ledger.")
        else:
            for log in browser_logs:
                ts = time.strftime('%H:%M:%S', time.localtime(log.get("timestamp") / 1000.0))
                lvl = log.get("type", "info").upper()
                src = log.get("source", "console").upper()
                print(f"[{ts}] [{lvl}] [{src}] {log.get('message')}")
        print("==================================================================\n")

        print(f"{GREEN}Walkthrough Completed successfully! Closing connections...{RESET}")
        
    except Exception as e:
        print(f"\n{RED}[ERROR] Walkthrough failed: {e}{RESET}")
        try:
            print("\n====================== Browser Console Logs (Before failure) ======================")
            browser_logs = await bridge.query_ledger()
            if not browser_logs:
                print("No logs in ledger.")
            else:
                for log in browser_logs:
                    lvl = log.get("type", "info").upper()
                    print(f"[{lvl}] {log.get('message')}")
            print("===================================================================================\n")
        except Exception as le:
            print(f"Could not fetch ledger: {le}")
        raise e
    finally:
        await bridge.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting walkthrough.")
