from typing import List, Tuple


class PostConditionPredictor:
    """
    Exposes an interface for predicting state side-effects from a model.
    """
    def __init__(self, model):
        self.model = model

    def predict(self, command: dict, current_state: dict) -> List[Tuple[str, float]]:
        """Predicts expected state changes based on historical transitions."""
        return self.model.predict_changes(command, current_state)
