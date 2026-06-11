#!/usr/bin/env python
"""
================================================================================
React Agent Bridge — Redux Integration Walkthrough Agent
================================================================================

This walkthrough demonstrates the core capabilities of the react-agent-bridge
Python SDK with Redux Toolkit and shows the CLI commands developers can use to 
inspect and control their React applications directly from the terminal.

TO RUN:
1. Start the React Frontend:
   cd examples/redux-flow
   npm run dev

2. Run this script in a separate terminal:
   python agent.py
"""

import asyncio
import sys

from react_agent_bridge.core.client import ReactAgentBridge

# Color formatting for terminal outputs
GREEN = "\033[1;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[1;36m"
MAGENTA = "\033[1;35m"
RESET = "\033[0m"


async def prompt_step(step_name, cli_command):
    print(f"\n{MAGENTA}>>> Next Step: {step_name}{RESET}")
    print(f"    Equivalent CLI: {YELLOW}{cli_command}{RESET}")
    input("    Press [Enter] to execute this step...")


async def main():
    print("================================================================================")
    print("      Starting react-agent-bridge SDK & Redux Walkthrough Tour")
    print("================================================================================\n")

    host = "localhost"
    port = 8000

    # -------------------------------------------------------------
    # STEP 1: Connect (Health Check)
    # CLI Equivalent: react-agent-bridge connect
    # -------------------------------------------------------------
    await prompt_step("Connect & Verify Connection Health", f"react-agent-bridge connect --host {host} --port {port}")
    
    bridge = ReactAgentBridge(host=host, port=port)
    await bridge.start()
    print(f"\nConnecting to React application on ws://{host}:{port}...")
    
    try:
        # Blocks until browser tab links with bridge
        await asyncio.wait_for(bridge.wait_for_client(), timeout=30.0)
        print(f"{GREEN}[SUCCESS] React application linked successfully!{RESET}")
        
        # Wait a short moment for registry deltas to sync
        await asyncio.sleep(1.5)
        
        components = bridge.graph.get_mounted_components()
        routes = sorted(list(set(c.route for c in components if c.route)))
        print(f"  Component Count: {len(components)}")
        print(f"  Mounted Routes:  {', '.join(routes)}")
        
    except asyncio.TimeoutError:
        print(f"\n{YELLOW}Connection timed out. Did you open http://localhost:5173 in your browser?{RESET}")
        await bridge.stop()
        sys.exit(1)

    # -------------------------------------------------------------
    # STEP 2: Inspect Live Component Registry
    # CLI Equivalent: react-agent-bridge registry
    # -------------------------------------------------------------
    await prompt_step("Inspect Component Registry & Slices", "react-agent-bridge registry")
    
    components = bridge.graph.get_mounted_components()
    print("\n================= Active Registry Snapshot =================")
    for comp in components:
        print(f"\nComponent: {comp.display_name} ({comp.id})")
        print(f"  Route: {comp.route or 'None'}")
        if comp.state_slots:
            print("  State Slots:")
            for key, slot in comp.state_slots.items():
                val = slot.value
                is_col = isinstance(val, (list, dict))
                is_sensitive = slot.sensitive
                is_readonly = slot.writeable == "user"

                val_str = f'"{val}"' if isinstance(val, str) else str(val)
                if is_sensitive:
                    val_str = "[REDACTED]"

                markers = []
                if is_sensitive:
                    markers.append("[Sensitive]")
                if is_col:
                    markers.append("[Collection]")
                if is_readonly:
                    markers.append("[Readonly]")

                marker_str = " ".join(markers)
                if marker_str:
                    marker_str = f" {marker_str}"
                print(f"    - {key}: {val_str}{marker_str}")
    print("============================================================\n")

    # -------------------------------------------------------------
    # STEP 3: Watch State Changes in Real-Time
    # CLI Equivalent: react-agent-bridge watch
    # -------------------------------------------------------------
    await prompt_step("Watch Live State Updates", "react-agent-bridge watch")
    
    def state_changed(target, val):
        parts = target.rsplit(".", 1)
        if len(parts) == 2:
            comp_id, key = parts
            comp = bridge.graph.get_component(comp_id)
            if comp and key in comp.state_slots:
                slot = comp.state_slots[key]
                # Filter out no-op changes
                if slot.previous_value != val:
                    prev_str = "[REDACTED]" if slot.sensitive else str(slot.previous_value)
                    val_str = "[REDACTED]" if slot.sensitive else str(val)
                    print(f"  {GREEN}[State Transition] {comp.display_name}.{key}: {prev_str} -> {val_str}{RESET}")

    bridge.add_listener("state_update", state_changed)
    print(f"\n{CYAN}State change listener registered. Go to your browser and trigger some changes!{RESET}")
    print("Click standard increment/decrement/setName buttons. Press [Enter] here to proceed...")
    input()

    # -------------------------------------------------------------
    # STEP 4: Direct Action Dispatching (Bypassing LLM Runner)
    # CLI Equivalent: react-agent-bridge run "increment the counter three times"
    # -------------------------------------------------------------
    await prompt_step(
        "Execute Direct Action Dispatches (Call Redux Dispatch via SDK)", 
        'react-agent-bridge run "increment the counter three times"'
    )
    
    print(f"\n{CYAN}Dispatching counter/increment action 3 times directly via the bridge...{RESET}")
    for i in range(3):
        print(f"  Dispatching action {i+1}/3...")
        try:
            # Invokes storeName#redux.dispatch('counter/increment')
            await bridge.call_action("ReduxStore#redux.dispatch", ["counter/increment"])
        except Exception as e:
            print(f"  {YELLOW}Action dispatch failed: {e}{RESET}")
        await asyncio.sleep(0.5)

    # Clean up listener and bridge connection before exiting
    bridge.remove_listener("state_update", state_changed)
    await bridge.stop()
    
    print("\n================================================================================")
    print("      Walkthrough Tour Completed successfully!")
    print("================================================================================\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting walkthrough.")
