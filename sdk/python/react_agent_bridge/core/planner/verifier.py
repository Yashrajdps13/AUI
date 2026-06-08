import logging
from react_agent_bridge.core.transition.model import compute_slots_changed

logger = logging.getLogger("react_agent_bridge.planner.verifier")


class PostConditionVerifier:
    """
    Verifies if dispatched commands successfully produced their expected post-conditions in the state graph.
    """
    @staticmethod
    def verify(command: dict, state_before: dict, state_after: dict, ack_success: bool) -> bool:
        """
        Returns True if the command's expected post-conditions are detected, otherwise False.
        """
        if not ack_success:
            return False

        cmd_type = command.get("type")
        target = command.get("target")

        if cmd_type == "setState":
            parts = target.rsplit(".", 1)
            if len(parts) == 2:
                comp_id, slot_key = parts
                components = state_after.get("components", {})
                comp_data = components.get(comp_id, {})
                slots = comp_data.get("stateSlots", {})
                
                if slot_key not in slots:
                    return False
                    
                after_val = slots[slot_key]
                expected_val = command.get("value")
                return after_val == expected_val
            return False

        elif cmd_type == "dispatchEvent" and command.get("event") == "click":
            # A click should trigger some state change in the application
            changed = compute_slots_changed(state_before, state_after)
            if len(changed) == 0:
                logger.warning(f"Click dispatch on '{target}' selector '{command.get('payload')}' did not trigger any state change.")
                return False
            return True

        elif cmd_type == "callAction":
            # callAction should trigger at least one state change in the application
            changed = compute_slots_changed(state_before, state_after)
            return len(changed) > 0

        elif cmd_type == "waitFor":
            # If ack was success, the condition was met in the browser
            return True

        return True
