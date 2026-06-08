from typing import List
from react_agent_bridge.storage.base import BaseStore
from react_agent_bridge.core.transition.observation import TransitionObservation


class MemoryStore(BaseStore):
    """
    An ephemeral, in-memory implementation of the observation store.
    Useful for testing and local agent sessions that do not need to persist learning.
    """
    def __init__(self):
        self.observations: List[TransitionObservation] = []

    def save_observation(self, obs: TransitionObservation) -> None:
        self.observations.append(obs)

    def get_observations(self, limit: int = 100) -> List[TransitionObservation]:
        return self.observations[-limit:]

    def query_observations_by_command(self, command_type: str, target: str) -> List[TransitionObservation]:
        matched = []
        for obs in self.observations:
            cmd = obs.command
            if cmd.get("type") == command_type and cmd.get("target") == target:
                matched.append(obs)
        return matched

    def clear(self) -> None:
        self.observations.clear()
