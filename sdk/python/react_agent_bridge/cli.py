#!/usr/bin/env python
import argparse
import asyncio
import json
import os
import sys
import time
import getpass
import urllib.request

from react_agent_bridge.core.client import ReactAgentBridge
from react_agent_bridge.core.planner.runner import AgentRunner
from react_agent_bridge.discovery.session import DiscoverySession
from typing import Any


def get_config_path() -> str:
    config_dir = os.path.expanduser("~/.react-agent-bridge")
    return os.path.join(config_dir, "config.json")


def load_config() -> dict:
    config_path = get_config_path()
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def check_ollama_running() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434", timeout=1.0) as conn:
            return True
    except Exception:
        return False


def resolve_and_check_llm(explicit_model: str = None) -> str:
    model = explicit_model
    config = load_config()

    # 1. Env Var
    if not model:
        model = os.environ.get("REACT_AGENT_BRIDGE_MODEL")
    # 2. Config JSON
    if not model:
        model = config.get("model")
    # 3. Final default
    if not model:
        model = "ollama/qwen2.5:7b"

    # Export keys to environment
    api_keys = config.get("api_keys", {})
    for k, v in api_keys.items():
        if v and k not in os.environ:
            os.environ[k] = v

    # Reachability check
    reachable = True
    if "ollama" in model.lower():
        reachable = check_ollama_running()
    elif "gemini" in model.lower():
        reachable = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("LITELLM_API_KEY"))
    elif "openai" in model.lower():
        reachable = bool(os.environ.get("OPENAI_API_KEY"))
    elif "groq" in model.lower():
        reachable = bool(os.environ.get("GROQ_API_KEY"))
    else:
        # Check for generic custom model key setups
        if api_keys:
            reachable = any(os.environ.get(k) for k in api_keys.keys())

    if not reachable:
        print(f"Error: The LLM model '{model}' is not reachable or configured.")
        print("Please run 'react-agent-bridge setup' to configure your LLM provider and credentials.")
        sys.exit(0)

    return model


def cmd_setup(args):
    print("=== React Agent Bridge LLM Configuration ===")
    print("Please select your preferred LLM provider:")
    print("1. Ollama (free, local, no API key, recommended default)")
    print("2. Gemini")
    print("3. OpenAI")
    print("4. Groq")
    print("5. Other (manual LiteLLM model string)")

    choice = input("Select provider (1-5): ").strip()
    config_dir = os.path.expanduser("~/.react-agent-bridge")
    os.makedirs(config_dir, exist_ok=True)
    config_path = get_config_path()

    config = {"provider": "", "model": "", "api_keys": {}}

    if choice == "1":
        config["provider"] = "ollama"
        config["model"] = "ollama/qwen2.5:7b"
        print("Checking if Ollama is running locally...")
        if check_ollama_running():
            print("[SUCCESS] Ollama detected running locally.")
        else:
            print("[WARNING] Ollama is not detected running on http://localhost:11434.")
            print("Please ensure Ollama is installed and started, then run:")
            print("  ollama pull qwen2.5:7b")

    elif choice == "2":
        config["provider"] = "gemini"
        config["model"] = "gemini/gemini-1.5-flash"
        key = getpass.getpass("Enter GEMINI_API_KEY: ").strip()
        config["api_keys"]["GEMINI_API_KEY"] = key

    elif choice == "3":
        config["provider"] = "openai"
        config["model"] = "openai/gpt-4o-mini"
        key = getpass.getpass("Enter OPENAI_API_KEY: ").strip()
        config["api_keys"]["OPENAI_API_KEY"] = key

    elif choice == "4":
        config["provider"] = "groq"
        config["model"] = "groq/llama3-8b-8192"
        key = getpass.getpass("Enter GROQ_API_KEY: ").strip()
        config["api_keys"]["GROQ_API_KEY"] = key

    elif choice == "5":
        config["provider"] = "other"
        model = input("Enter LiteLLM model string (e.g., anthropic/claude-3-5-sonnet): ").strip()
        config["model"] = model
        key_env = input("Enter API key environment variable name (e.g., ANTHROPIC_API_KEY, leave empty if none): ").strip()
        if key_env:
            key_val = getpass.getpass(f"Enter {key_env}: ").strip()
            config["api_keys"][key_env] = key_val

    else:
        print("Invalid selection. Exiting setup.")
        sys.exit(1)

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    print(f"Configuration saved successfully to {config_path}")


async def run_connect(host: str, port: int):
    bridge = ReactAgentBridge(host=host, port=port)
    await bridge.start()
    print(f"Connecting to React application on ws://{host}:{port}...")
    try:
        await asyncio.wait_for(bridge.wait_for_client(), timeout=10.0)
        # Wait for registry sync
        start_wait = time.time()
        while not bridge.graph.get_mounted_components() and (time.time() - start_wait) < 3.0:
            await asyncio.sleep(0.1)

        components = bridge.graph.get_mounted_components()
        routes = sorted(list(set(c.route for c in components if c.route)))

        app_name = "React Application"
        if components:
            roots = [c for c in components if c.parent_id is None]
            if roots:
                app_name = roots[0].display_name
            else:
                app_name = components[0].display_name

        print("\n================ Health Check ================")
        print(f"Status:            [CONNECTED]")
        print(f"React App Name:    {app_name}")
        print(f"Component Count:   {len(components)}")
        print(f"Mounted Routes:    {', '.join(routes) if routes else 'None'}")
        print("==============================================")
    except asyncio.TimeoutError:
        print(f"Error: Connection timed out. No React app connected to ws://{host}:{port} within 10 seconds.")
        sys.exit(1)
    except Exception as e:
        print(f"Error connecting to bridge: {e}")
        sys.exit(1)
    finally:
        await bridge.stop()


async def run_registry(host: str, port: int):
    bridge = ReactAgentBridge(host=host, port=port)
    await bridge.start()
    try:
        await asyncio.wait_for(bridge.wait_for_client(), timeout=10.0)
        start_wait = time.time()
        while not bridge.graph.get_mounted_components() and (time.time() - start_wait) < 3.0:
            await asyncio.sleep(0.1)

        components = bridge.graph.get_mounted_components()
        if not components:
            print("No components found in the registry.")
            return

        print("\n================ Component Registry ================")
        for comp in components:
            if comp.id in ["__context__#env", "__context__#custom"]:
                print(f"\nComponent: [context] {comp.display_name} ({comp.id})")
            else:
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
            else:
                print("  State Slots: None")
            if comp.actions:
                print(f"  Actions: {', '.join(comp.actions)}")
        print("\n====================================================")
    except asyncio.TimeoutError:
        print(f"Error: Connection timed out. No React app connected to ws://{host}:{port}.")
        sys.exit(1)
    except Exception as e:
        print(f"Error fetching registry: {e}")
        sys.exit(1)
    finally:
        await bridge.stop()


async def run_watch(host: str, port: int):
    bridge = ReactAgentBridge(host=host, port=port)
    await bridge.start()

    def on_state_update(target: str, value: Any):
        parts = target.rsplit(".", 1)
        if len(parts) == 2:
            comp_id, slot_key = parts
            comp = bridge.graph.get_component(comp_id)
            if comp and slot_key in comp.state_slots:
                slot = comp.state_slots[slot_key]
                prev_val = slot.previous_value
                if prev_val != value:
                    prev_str = "[REDACTED]" if slot.sensitive else (f'"{prev_val}"' if isinstance(prev_val, str) else str(prev_val))
                    new_str = "[REDACTED]" if slot.sensitive else (f'"{value}"' if isinstance(value, str) else str(value))
                    print(f"[{comp.display_name}] {slot_key}: {prev_str} -> {new_str}")

    bridge.add_listener("state_update", on_state_update)
    print(f"Watching state changes on ws://{host}:{port}... Press Ctrl+C to stop.\n")

    try:
        await asyncio.wait_for(bridge.wait_for_client(), timeout=10.0)
        while True:
            await asyncio.sleep(1.0)
    except asyncio.TimeoutError:
        print(f"Error: Connection timed out. No React app connected to ws://{host}:{port}.")
        sys.exit(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nStopping state watcher.")
    finally:
        await bridge.stop()


async def run_audit(host: str, port: int):
    bridge = ReactAgentBridge(host=host, port=port)
    await bridge.start()
    try:
        await asyncio.wait_for(bridge.wait_for_client(), timeout=10.0)
        logs = await bridge.query_audit_log()
        if not logs:
            print("No audit logs found for the current session.")
            return

        print("\n================ Command Audit Log ================")
        for log in logs:
            status = "SUCCESS" if log.get("success") else f"FAILED: {log.get('error')}"
            ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(log.get("timestamp") / 1000.0))
            print(f"[{ts}] {log.get('type')} on {log.get('target')} -> {status}")
            if log.get("value") is not None:
                print(f"  Value: {log.get('value')}")
        print("===================================================")
    except asyncio.TimeoutError:
        print(f"Error: Connection timed out. No React app connected to ws://{host}:{port}.")
        sys.exit(1)
    except Exception as e:
        print(f"Error retrieving audit log: {e}")
        sys.exit(1)
    finally:
        await bridge.stop()


async def run_logs(host: str, port: int):
    bridge = ReactAgentBridge(host=host, port=port)
    await bridge.start()
    try:
        await asyncio.wait_for(bridge.wait_for_client(), timeout=10.0)
        logs = await bridge.query_ledger()
        if not logs:
            print("No console logs found in the browser ledger.")
            return

        print("\n================ Browser Logs ================")
        for log in logs:
            ts = time.strftime('%H:%M:%S', time.localtime(log.get("timestamp") / 1000.0))
            level = log.get("type", "info").upper()
            src = log.get("source", "console").upper()
            print(f"[{ts}] [{level}] [{src}] {log.get('message')}")
            if log.get("stack"):
                print(f"  Stack Trace: {log.get('stack')}")
        print("==============================================")
    except asyncio.TimeoutError:
        print(f"Error: Connection timed out. No React app connected to ws://{host}:{port}.")
        sys.exit(1)
    except Exception as e:
        print(f"Error retrieving logs: {e}")
        sys.exit(1)
    finally:
        await bridge.stop()


async def run_goal(host: str, port: int, goal_desc: str, explicit_model: str, context_flag: str, max_steps: int):
    model = resolve_and_check_llm(explicit_model)

    context_path = context_flag
    if not context_path and os.path.exists("./agent-context.md"):
        context_path = "./agent-context.md"

    business_context = None
    if context_path and os.path.exists(context_path):
        try:
            with open(context_path, "r", encoding="utf-8") as f:
                business_context = f.read()
            print(f"Loaded business context from: {context_path}")
        except Exception as e:
            print(f"Warning: Failed to read context file '{context_path}': {e}")

    bridge = ReactAgentBridge(host=host, port=port)
    await bridge.start()

    print(f"Waiting for React app to connect on ws://{host}:{port}...")
    try:
        await asyncio.wait_for(bridge.wait_for_client(), timeout=10.0)
        runner = AgentRunner(
            bridge=bridge,
            model=model,
            business_context=business_context,
            max_steps=max_steps
        )
        print(f"Executing goal: '{goal_desc}' using model: '{model}'")
        res = await runner.execute(goal_desc)
        if res.get("status") == "failed":
            sys.exit(1)
    except asyncio.TimeoutError:
        print(f"Error: Connection timed out. No React app connected to ws://{host}:{port}.")
        sys.exit(1)
    except Exception as e:
        print(f"Error running goal: {e}")
        sys.exit(1)
    finally:
        await bridge.stop()


async def run_discover(host: str, port: int, db_path: str, output_path: str):
    bridge = ReactAgentBridge(host=host, port=port)
    session = DiscoverySession(
        bridge=bridge,
        db_path=db_path,
        output_path=output_path
    )

    session_count = 0

    def on_disconnect():
        nonlocal session_count
        session_count += 1
        async def print_status():
            await asyncio.sleep(0.5)  # Wait for DB sync to finish
            try:
                import sqlite3
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT session_id, event_count, is_complete FROM sessions ORDER BY started_at DESC LIMIT 1")
                row = cursor.fetchone()
                conn.close()
                if row:
                    sid, cnt, is_comp = row
                    comp_str = "complete" if is_comp else "incomplete"
                    print(f"[Discovery] Completed session #{session_count} (ID: {sid[:8]}...) with {cnt} events ({comp_str}).")
            except Exception:
                print(f"[Discovery] Completed session #{session_count}.")
        asyncio.create_task(print_status())

    bridge.add_listener("disconnect", on_disconnect)
    print(f"Discovery Mode started on ws://{host}:{port}.")
    print(f"Passive human sessions will be recorded in '{db_path}'.")
    print("Press Ctrl+C to stop recording and generate the agent context.\n")

    if not bridge._server:
        await bridge.start()

    try:
        while True:
            await asyncio.sleep(1.0)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nInterrupt received. Stopping discovery recording...")
    finally:
        await bridge.stop()
        # Settle any remaining async database logs
        await asyncio.sleep(1.0)

    print("Running workflow inference engine to generate agent-context.md...")
    try:
        await session.generate()
        print(f"Success! '{output_path}' has been successfully written to the current directory.")
    except Exception as e:
        print(f"Error generating context: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="react-agent-bridge command-line interface.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # setup
    subparsers.add_parser("setup", help="Interactive first-run LLM configuration.")

    # connect
    parser_connect = subparsers.add_parser("connect", help="Health check command to verify connection.")
    parser_connect.add_argument("--host", default="localhost")
    parser_connect.add_argument("--port", type=int, default=8000)

    # registry
    parser_reg = subparsers.add_parser("registry", help="Prints the live component registry.")
    parser_reg.add_argument("--host", default="localhost")
    parser_reg.add_argument("--port", type=int, default=8000)

    # watch
    parser_watch = subparsers.add_parser("watch", help="Prints state changes in real time.")
    parser_watch.add_argument("--host", default="localhost")
    parser_watch.add_argument("--port", type=int, default=8000)

    # audit
    parser_aud = subparsers.add_parser("audit", help="Prints the current command audit log.")
    parser_aud.add_argument("--host", default="localhost")
    parser_aud.add_argument("--port", type=int, default=8000)

    # logs
    parser_log = subparsers.add_parser("logs", help="Prints browser console logs.")
    parser_log.add_argument("--host", default="localhost")
    parser_log.add_argument("--port", type=int, default=8000)

    # run
    parser_run = subparsers.add_parser("run", help="Runs the AgentRunner with the provided goal.")
    parser_run.add_argument("goal", help="The goal description.")
    parser_run.add_argument("--model", help="Explicit LiteLLM model string to use.")
    parser_run.add_argument("--context", help="Path to agent-context.md file.")
    parser_run.add_argument("--max-steps", type=int, default=15)
    parser_run.add_argument("--host", default="localhost")
    parser_run.add_argument("--port", type=int, default=8000)

    # discover
    parser_disc = subparsers.add_parser("discover", help="Starts discovery session to passively record usage.")
    parser_disc.add_argument("--host", default="localhost")
    parser_disc.add_argument("--port", type=int, default=8000)
    parser_disc.add_argument("--db", default="./discovery.db", help="SQLite DB path to save logs.")
    parser_disc.add_argument("--context-out", default="./agent-context.md", help="MD path to save inferred context.")

    args = parser.parse_args()

    if args.command == "setup":
        cmd_setup(args)
        return

    # Helper function to run async main coroutine safely
    def run_async(coro):
        try:
            asyncio.run(coro)
        except KeyboardInterrupt:
            pass

    if args.command == "connect":
        run_async(run_connect(args.host, args.port))
    elif args.command == "registry":
        run_async(run_registry(args.host, args.port))
    elif args.command == "watch":
        run_async(run_watch(args.host, args.port))
    elif args.command == "audit":
        run_async(run_audit(args.host, args.port))
    elif args.command == "logs":
        run_async(run_logs(args.host, args.port))
    elif args.command == "run":
        run_async(run_goal(args.host, args.port, args.goal, args.model, args.context, args.max_steps))
    elif args.command == "discover":
        run_async(run_discover(args.host, args.port, args.db, args.context_out))


if __name__ == "__main__":
    main()
