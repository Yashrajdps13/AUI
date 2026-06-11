from dataclasses import dataclass, field
from typing import List, Any


@dataclass
class GoalCondition:
    """
    Represents a specific state condition target.operator.value that must be met.
    """
    target: str
    operator: str  # "equals" | "truthy" | "falsy" | "changed"
    value: Any = None

    def evaluate(self, current_state: Any) -> bool:
        """
        Evaluates the condition against a serialized graph snapshot dictionary or StateGraph.
        """
        parts = self.target.split(".", 1)
        if len(parts) != 2:
            return False
        comp_id, path_str = parts

        # Suffix-agnostic component lookup
        comp = None
        if hasattr(current_state, "get_component"):
            comp = current_state.get_component(comp_id)
            if not comp:
                comp_id_clean = comp_id.split("#", 1)[0].split(":", 1)[0]
                for cid, node in current_state.components.items():
                    cid_clean = cid.split("#", 1)[0].split(":", 1)[0]
                    if cid_clean == comp_id_clean:
                        comp = node
                        break
        else:
            components = current_state.get("components", {})
            comp_data = components.get(comp_id)
            if not comp_data:
                comp_id_clean = comp_id.split("#", 1)[0].split(":", 1)[0]
                for cid, cdata in components.items():
                    cid_clean = cid.split("#", 1)[0].split(":", 1)[0]
                    if cid_clean == comp_id_clean:
                        comp_data = cdata
                        comp_id = cid
                        break
            if comp_data:
                class MockNode:
                    def __init__(self, cid, data):
                        self.id = cid
                        self.route = data.get("route")
                        self.state_slots = data.get("stateSlots", {})
                comp = MockNode(comp_id, comp_data)

        # Handle virtual slots first
        if path_str == "isMounted":
            val = comp is not None
            if self.operator == "equals":
                return val == self.value
            elif self.operator == "truthy":
                return val
            elif self.operator == "falsy":
                return not val
            return False

        if path_str == "route":
            val = comp.route if comp is not None else None
            if self.operator == "equals":
                return val == self.value
            elif self.operator == "truthy":
                return bool(val)
            elif self.operator == "falsy":
                return not bool(val)
            elif self.operator == "changed":
                return val is not None and val != getattr(comp, "route_at_mount", None)
            return False

        if comp is None:
            return self.operator == "falsy"

        import re
        segments = path_str.split(".")
        first_segment = segments[0]
        match_bracket = re.match(r'^([^\[]+)(.*)$', first_segment)
        if match_bracket:
            slot_key = match_bracket.group(1)
            brackets = match_bracket.group(2)
        else:
            slot_key = first_segment
            brackets = ""

        if hasattr(comp, "state_slots") and isinstance(comp.state_slots, dict):
            if slot_key not in comp.state_slots:
                return self.operator == "falsy"
            slot_obj = comp.state_slots[slot_key]
            if hasattr(slot_obj, "value"):
                base_val = slot_obj.value
            else:
                base_val = slot_obj
        else:
            return self.operator == "falsy"

        nested_segments = []
        if brackets:
            nested_segments.extend(re.findall(r'\[\d+\]', brackets))
        nested_segments.extend(segments[1:])

        if nested_segments:
            success, val = self._resolve_nested_value(base_val, nested_segments)
            if not success:
                return self.operator == "falsy"
        else:
            val = base_val


        if self.operator == "equals":
            return val == self.value
        elif self.operator == "truthy":
            return bool(val)
        elif self.operator == "falsy":
            return not bool(val)
        elif self.operator == "changed":
            if not hasattr(slot_obj, "value_history") or not slot_obj.value_history:
                return False
            initial_base_val = slot_obj.value_history[0]
            if nested_segments:
                success, initial_val = self._resolve_nested_value(initial_base_val, nested_segments)
                if not success:
                    return False
            else:
                initial_val = initial_base_val
            return val != initial_val
        return False

    def _resolve_nested_value(self, val: Any, path_segments: List[str]) -> tuple:
        import re
        curr = val
        for segment in path_segments:
            if curr is None:
                return False, None
            parts = re.split(r'(\[\d+\])', segment)
            for part in parts:
                if not part:
                    continue
                if part.startswith('[') and part.endswith(']'):
                    idx_str = part[1:-1]
                    try:
                        idx = int(idx_str)
                        if isinstance(curr, list) and 0 <= idx < len(curr):
                            curr = curr[idx]
                        else:
                            return False, None
                    except ValueError:
                        return False, None
                else:
                    if isinstance(curr, dict) and part in curr:
                        curr = curr[part]
                    elif hasattr(curr, part):
                        curr = getattr(curr, part)
                    else:
                        return False, None
        return True, curr



@dataclass
class Goal:
    """
    Represents the planning target goal containing description and conditions.
    """
    description: str
    success_conditions: List[GoalCondition] = field(default_factory=list)
    failure_conditions: List[GoalCondition] = field(default_factory=list)
    max_steps: int = 15
    timeout_seconds: float = 60.0
