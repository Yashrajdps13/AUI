from typing import List, Callable, Tuple
from react_agent_bridge.core.rules.base_rules import ALL_BASE_RULES


class RuleRegistry:
    """
    Manages the collection of correctness rules, ordered by evaluation priority.
    """
    def __init__(self):
        # List of tuples: (rule_function, priority_int)
        # Higher priority runs first.
        self.rules: List[Tuple[Callable, int]] = []
        
        # Register base rules with default priority 100
        for rule in ALL_BASE_RULES:
            self.add_rule(rule, priority=100)

    def add_rule(self, rule_fn: Callable, priority: int = 200):
        """Adds a validation rule function (command, graph) -> Optional[RuleViolation]."""
        self.rules.append((rule_fn, priority))
        # Sort by priority descending
        self.rules.sort(key=lambda x: x[1], reverse=True)

    def remove_rule(self, rule_fn: Callable):
        """Removes a rule function from the registry."""
        self.rules = [r for r in self.rules if r[0] != rule_fn]

    def clear_custom_rules(self):
        """Resets the registry to only base rules."""
        self.rules = [r for r in self.rules if r[1] == 100]
