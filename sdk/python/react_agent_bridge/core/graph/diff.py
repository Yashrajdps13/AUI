from dataclasses import dataclass, field
from typing import List
from react_agent_bridge.core.graph.node import ComponentNode


@dataclass
class GraphDiff:
    """
    Represents a diff applied to the state graph.
    """
    added: List[ComponentNode] = field(default_factory=list)
    updated: List[ComponentNode] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
