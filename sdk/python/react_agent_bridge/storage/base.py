from abc import ABC, abstractmethod
from typing import List
from react_agent_bridge.core.transition.observation import TransitionObservation


class BaseStore(ABC):
    """
    Abstract interface for persisting TransitionObservations.
    """
    @abstractmethod
    def save_observation(self, obs: TransitionObservation) -> None:
        """Saves a transition observation to the store."""
        pass

    @abstractmethod
    def get_observations(self, limit: int = 100) -> List[TransitionObservation]:
        """Gets the most recent observations."""
        pass

    @abstractmethod
    def query_observations_by_command(self, command_type: str, target: str) -> List[TransitionObservation]:
        """Queries observations matching a given command type and target."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clears all stored observations."""
        pass
