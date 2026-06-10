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
        parts = self.target.rsplit(".", 1)
        if len(parts) != 2:
            return False
        comp_id, slot_key = parts

        if hasattr(current_state, "get_slot_value"):
            comp = current_state.get_component(comp_id)
            if not comp:
                comp_id_clean = comp_id.split("#", 1)[0].split(":", 1)[0]
                for cid, node in current_state.components.items():
                    cid_clean = cid.split("#", 1)[0].split(":", 1)[0]
                    if cid_clean == comp_id_clean:
                        comp = node
                        break
            if not comp or slot_key not in comp.state_slots:
                return self.operator == "falsy"
            val = comp.state_slots[slot_key].value
        else:
            components = current_state.get("components", {})
            comp_data = components.get(comp_id)
            if not comp_data:
                comp_id_clean = comp_id.split("#", 1)[0].split(":", 1)[0]
                for cid, cdata in components.items():
                    cid_clean = cid.split("#", 1)[0].split(":", 1)[0]
                    if cid_clean == comp_id_clean:
                        comp_data = cdata
                        break
            comp_data = comp_data or {}
            slots_data = comp_data.get("stateSlots", {})

            if slot_key not in slots_data:
                return self.operator == "falsy"

            val = slots_data[slot_key]

        if self.operator == "equals":
            return val == self.value
        elif self.operator == "truthy":
            return bool(val)
        elif self.operator == "falsy":
            return not bool(val)
        elif self.operator == "changed":
            if self.value is not None and self.value != "None" and self.value != "":
                return str(val) != str(self.value)
            return val is not None and val != [] and val != "" and val != {}
        elif self.operator in ["contains", "includes"]:
            if isinstance(val, str) and isinstance(self.value, str):
                return self.value in val
            if isinstance(val, list):
                return any(self.value == item or str(self.value) in str(item) for item in val)
            return False
        return False


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
