import logging
from react_agent_bridge.core.rules.registry import RuleRegistry
from react_agent_bridge.core.rules.result import RuleResult
from react_agent_bridge.core.graph.state_graph import ApplicationStateGraph

logger = logging.getLogger("react_agent_bridge.rules.engine")


class RulesEngine:
    """
    Executes pre-flight gate checks on commands before transmission over WebSocket.
    """
    def __init__(self, registry: RuleRegistry):
        self.registry = registry

    def evaluate(self, command: dict, graph: ApplicationStateGraph) -> RuleResult:
        """
        Evaluates a proposed command against all active rules in priority order.
        Returns a RuleResult indicating validity and listing violations (fail-fast).
        """
        violations = []
        for rule_fn, priority in self.registry.rules:
            try:
                violation = rule_fn(command, graph)
                if violation:
                    violations.append(violation)
                    logger.debug(f"Rule violation caught by {rule_fn.__name__}: {violation.message}")
                    break  # Fail-fast on the first violation
            except Exception as e:
                logger.error(f"Error evaluating rule {rule_fn.__name__}: {e}", exc_info=True)
                
        return RuleResult(valid=len(violations) == 0, violations=violations)
