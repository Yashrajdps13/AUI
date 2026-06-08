from dataclasses import dataclass


@dataclass
class StateEdge:
    """
    Represents an empirically observed relationship between two state slots
    or between an action/event and a state slot.
    """
    source_target: str
    destination_target: str
    co_occurrence_count: int = 0
    total_observations: int = 0
    strength: float = 0.0

    def record_observation(self, co_occurred: bool):
        self.total_observations += 1
        if co_occurred:
            self.co_occurrence_count += 1
        self.strength = self.co_occurrence_count / max(1, self.total_observations)
