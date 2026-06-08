import logging
import time
from typing import Dict, List, Tuple, Any, Optional
from react_agent_bridge.storage.base import BaseStore
from react_agent_bridge.core.transition.observation import TransitionObservation

logger = logging.getLogger("react_agent_bridge.transition.model")


def compute_slots_changed(before: dict, after: dict) -> List[str]:
    """
    Compares before and after state snapshots to identify which state slots changed.
    Returned targets are in format 'ComponentId.slotKey'.
    """
    changed = []
    before_comps = before.get("components", {})
    after_comps = after.get("components", {})

    for comp_id, after_comp in after_comps.items():
        before_comp = before_comps.get(comp_id, {})
        before_slots = before_comp.get("stateSlots", {})
        after_slots = after_comp.get("stateSlots", {})

        for slot_key, after_val in after_slots.items():
            if slot_key not in before_slots or before_slots[slot_key] != after_val:
                changed.append(f"{comp_id}.{slot_key}")

    return changed


class TransitionModel:
    """
    Empirical transition model derived from recorded agent actions and state differences.
    """
    def __init__(self, store: BaseStore, session_id: str = "default"):
        self.store = store
        self.session_id = session_id

    def record_transition(
        self,
        command: dict,
        state_before: dict,
        state_after: dict,
        ack_success: bool,
        time_to_settle_ms: float
    ) -> TransitionObservation:
        """
        Computes state deltas, creates a TransitionObservation, and saves it in the store.
        """
        slots_changed = compute_slots_changed(state_before, state_after)
        obs = TransitionObservation(
            command=command,
            state_before=state_before,
            state_after=state_after,
            ack_success=ack_success,
            slots_changed=slots_changed,
            time_to_settle_ms=time_to_settle_ms,
            session_id=self.session_id,
            timestamp=time.time()
        )
        self.store.save_observation(obs)
        return obs

    def predict_changes(self, command: dict, current_state: dict) -> List[Tuple[str, float]]:
        """
        Returns a list of (slot_target, confidence) pairs that are predicted to change.
        """
        cmd_type = command.get("type")
        cmd_target = command.get("target")
        
        obs_list = self.store.query_observations_by_command(cmd_type, cmd_target)
        if not obs_list:
            return []

        change_counts = {}
        for obs in obs_list:
            if not obs.ack_success:
                continue
            for target in obs.slots_changed:
                change_counts[target] = change_counts.get(target, 0) + 1

        total = len([o for o in obs_list if o.ack_success])
        if total == 0:
            return []

        predictions = []
        for target, count in change_counts.items():
            confidence = count / total
            predictions.append((target, confidence))

        # Sort by confidence descending
        predictions.sort(key=lambda x: x[1], reverse=True)
        return predictions

    def expected_settle_time(self, command: dict) -> float:
        """
        Predicts how long in milliseconds we should wait for renderSettled.
        Defaults to 5000ms if no historical data.
        """
        cmd_type = command.get("type")
        cmd_target = command.get("target")

        obs_list = self.store.query_observations_by_command(cmd_type, cmd_target)
        valid_times = [o.time_to_settle_ms for o in obs_list if o.ack_success and o.time_to_settle_ms > 0]
        
        if not valid_times:
            return 5000.0  # Default 5 seconds

        # Return average settlement time + buffer (200ms)
        return (sum(valid_times) / len(valid_times)) + 200.0

    def is_action_effective(self, command: dict, current_state: dict) -> Tuple[bool, float]:
        """
        Returns (is_effective, confidence) of whether this command in this state
        is expected to produce any state changes at all.
        """
        cmd_type = command.get("type")
        cmd_target = command.get("target")

        obs_list = self.store.query_observations_by_command(cmd_type, cmd_target)
        if not obs_list:
            return True, 0.0  # Safe default: assume effective

        effective_count = 0
        total = 0
        for obs in obs_list:
            if not obs.ack_success:
                continue
            total += 1
            if len(obs.slots_changed) > 0:
                effective_count += 1

        if total == 0:
            return True, 0.0

        confidence = effective_count / total
        # If it has never produced state changes in many runs, mark as ineffective
        if total >= 3 and confidence < 0.1:
            return False, 1.0 - confidence
        
        return True, confidence
