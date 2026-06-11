import asyncio
from react_agent_bridge.core.client import ReactAgentBridge

async def main():
    bridge = ReactAgentBridge(host="localhost", port=8000)
    await bridge.start()
    try:
        await asyncio.wait_for(bridge.wait_for_client(), timeout=5.0)
        await asyncio.sleep(1.0)
        
        print("=== Registered Components ===")
        for comp in bridge.graph.get_mounted_components():
            print(f"\nID: {comp.id} (DisplayName: {comp.display_name})")
            print(f"  Interactive Elements ({len(comp.interactive_elements)}):")
            for el in comp.interactive_elements:
                print(f"    - Selector: {el.selector}, Tag: {el.tagName}, Text: '{el.text}', Visible: {el.visible}")
                
        print("\n=== Browser Console Logs ===")
        logs = await bridge.query_ledger()
        for log in logs:
            print(f"[{log.get('type', 'info').upper()}] {log.get('message')}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await bridge.stop()

if __name__ == "__main__":
    asyncio.run(main())
