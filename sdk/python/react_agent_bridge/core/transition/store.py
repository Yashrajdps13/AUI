from typing import List
from react_agent_bridge.storage.base import BaseStore
from react_agent_bridge.core.transition.observation import TransitionObservation


class TransitionStore:
    """
    Wrapper mapping high-level transition observation operations to the underlying database storage.
    """
    def __init__(self, storage: BaseStore):
        self.storage = storage

    def save(self, obs: TransitionObservation) -> None:
        self.storage.save_observation(obs)

    def get_latest(self, limit: int = 100) -> List[TransitionObservation]:
        return self.storage.get_observations(limit)

    def query(self, command_type: str, target: str) -> List[TransitionObservation]:
        return self.storage.query_observations_by_command(command_type, target)
