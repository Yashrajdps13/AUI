#!/usr/bin/env python
"""
================================================================================
React Agent Bridge — Enterprise Dashboard Walkthrough Agent
================================================================================

This walkthrough demonstrates the core capabilities of the react-agent-bridge
Python SDK and shows the CLI commands developers can use to inspect and control
their React applications directly from the terminal.

PREREQUISITE:
Before running this script, run the first-time interactive setup:
  react-agent-bridge setup

Select "1" (Ollama) as your provider (default) or configure Gemini/OpenAI/Groq.

TO RUN:
1. Start the React Frontend:
   cd examples/ultimate-demo
   npm run dev

2. Run this script in a separate terminal:
   python agent.py
"""

import asyncio
import os
import sys
import time

from react_agent_bridge.core.client import ReactAgentBridge
from react_agent_bridge.core.planner.runner import AgentRunner
from react_agent_bridge.discovery.session import DiscoverySession

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
    print("      Starting react-agent-bridge SDK & CLI Walkthrough Tour")
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
    await prompt_step("Inspect Component Registry & Annotations", "react-agent-bridge registry")
    
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
    print("Type inputs, click check-boxes, or switch routes. When done, press [Enter] here to proceed...")
    input()
    
    # Remove listener so it doesn't clutter next logs
    bridge.remove_listener("state_update", state_changed)

    # -------------------------------------------------------------
    # STEP 4: Run Multi-Step Goal (Goal-Directed Planner)
    # CLI Equivalent: react-agent-bridge run "goal description"
    # -------------------------------------------------------------
    goal_desc = (
        'Log in with password "secretpassword", create a new project called "Synergy Alpha", '
        'open its task board, add a task "Setup API Gateway" for Alice, and mark it complete.'
    )
    await prompt_step("Execute Automated Planning Goal", f'react-agent-bridge run "{goal_desc}"')
    
    # Resolve LLM model following the 4-level resolution priority
    # Flag -> Env -> config.json -> Ollama default
    from react_agent_bridge.cli import resolve_and_check_llm, get_config_path
    
    model = resolve_and_check_llm()
    print(f"\nInitialising AgentRunner using model '{model}'...")
    
    runner = AgentRunner(
        bridge=bridge,
        model=model,
        max_steps=15
    )
    
    print(f"{CYAN}Running goal against enterprise dashboard...{RESET}")
    res = await runner.execute(goal_desc)
    print(f"Goal status: {res.get('status')}")

    # -------------------------------------------------------------
    # STEP 5: Inspect Audit Log & PII Redaction
    # CLI Equivalent: react-agent-bridge audit
    # -------------------------------------------------------------
    await prompt_step("Inspect Command Audit Log (PII Redaction Check)", "react-agent-bridge audit")
    
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
                # Sensitive values (like password) show up redacted
                print(f"  Value: {log.get('value')}")
    print("=====================================================================\n")

    # -------------------------------------------------------------
    # STEP 6: Inspect Browser Console Output Ledger
    # CLI Equivalent: react-agent-bridge logs
    # -------------------------------------------------------------
    await prompt_step("Inspect Browser Console Ledger", "react-agent-bridge logs")
    
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

    # -------------------------------------------------------------
    # STEP 7: Run Passive Discovery Mode Session
    # CLI Equivalent: react-agent-bridge discover
    # -------------------------------------------------------------
    await prompt_step("Run Passive Discovery & Inference Session", "react-agent-bridge discover")
    
    print(f"\nClosing active connection to boot Discovery mode...")
    await bridge.stop()
    
    # Discovery server instantiation
    discovery_bridge = ReactAgentBridge(host=host, port=port)
    session = DiscoverySession(
        bridge=discovery_bridge,
        db_path="./discovery.db",
        output_path="./agent-context.md"
    )
    
    # Register disconnect listener to print status lines
    session_count = 0
    def on_disconnect():
        nonlocal session_count
        session_count += 1
        async def print_status():
            await asyncio.sleep(0.5)
            import sqlite3
            try:
                conn = sqlite3.connect("./discovery.db")
                cursor = conn.cursor()
                cursor.execute("SELECT session_id, event_count, is_complete FROM sessions ORDER BY started_at DESC LIMIT 1")
                row = cursor.fetchone()
                conn.close()
                if row:
                    sid, cnt, is_comp = row
                    comp_str = "complete" if is_comp else "incomplete"
                    print(f"\n{GREEN}[Discovery] Completed session #{session_count} (ID: {sid[:8]}...) with {cnt} events ({comp_str}).{RESET}")
            except Exception:
                print(f"\n{GREEN}[Discovery] Completed session #{session_count}.{RESET}")
        asyncio.create_task(print_status())

    discovery_bridge.add_listener("disconnect", on_disconnect)
    
    print(f"\n{CYAN}Discovery Mode Server started on ws://{host}:{port}.{RESET}")
    print("1. Go to your browser and reload/re-authenticate.")
    print("2. Perform checkout flows or form updates (each reset/reload counts as a session).")
    print("3. COMPLETE AT LEAST 3 SESSIONS to trigger valid workflow & constraint extraction.")
    print("4. Press Ctrl+C in this terminal when finished to compile the context.")
    
    await discovery_bridge.start()
    
    try:
        while True:
            await asyncio.sleep(1.0)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupt received. Shutting down bridge and running workflow inference...{RESET}")
    finally:
        await discovery_bridge.stop()
        # Wait for database logs to finalize
        await asyncio.sleep(1.0)

    print(f"\n{CYAN}Running inference engines to write/update agent-context.md...{RESET}")
    try:
        await session.generate()
        print(f"{GREEN}[SUCCESS] Workflow context compiled and written to: ./agent-context.md{RESET}")
    except Exception as e:
        print(f"{YELLOW}Failed to generate agent-context.md: {e}{RESET}")
        
    print("\n================================================================================")
    print("      Walkthrough Tour Completed successfully!")
    print("================================================================================\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting walkthrough.")
