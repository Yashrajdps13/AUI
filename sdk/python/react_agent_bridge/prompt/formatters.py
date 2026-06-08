def format_slot(key: str, value: any, description: str = None, writeable: str = None) -> str:
    meta = []
    if description:
        meta.append(description)
    if writeable == "user":
        meta.append("READ-ONLY")
    meta_str = f" ({', '.join(meta)})" if meta else ""
    return f"    - {key}: {value}{meta_str}"


def format_action(action_name: str) -> str:
    return f"    - Action: {action_name}"


def format_interactive_element(el: dict) -> str:
    desc = f" '{el['text']}'" if el.get("text") else ""
    disabled_str = " [DISABLED]" if el.get("disabled") else ""
    visible_str = " [HIDDEN]" if not el.get("visible", True) else ""
    return f"    - Element: {el['selector']} ({el['tagName']}){desc}{disabled_str}{visible_str}"


def format_component(comp_id: str, comp_data: dict) -> str:
    """Formats a component's details, active state, actions, and elements into a text block."""
    lines = []
    lines.append(f"Component: {comp_id} (Type: {comp_data['displayName']})")
    if comp_data.get("route"):
        lines.append(f"  Route: {comp_data['route']}")
    if comp_data.get("parent_id"):
        lines.append(f"  Parent: {comp_data['parent_id']}")

    slots = comp_data.get("stateSlots", {})
    descs = comp_data.get("stateSlotDescriptions", {})
    writeables = comp_data.get("stateSlotWriteables", {})
    if slots:
        lines.append("  State Slots:")
        for k, v in slots.items():
            # Skip logs and complex collections to prevent LLM confusion and save context tokens
            if k.lower() in ("auditlog", "log", "logs") or isinstance(v, (list, dict)):
                continue
            lines.append(format_slot(k, v, descs.get(k), writeables.get(k)))

    actions = comp_data.get("actions", [])
    if actions:
        lines.append("  Callable Actions:")
        for act in actions:
            lines.append(format_action(act))

    elements = comp_data.get("interactiveElements", [])
    if elements:
        lines.append("  Interactive Elements:")
        for el in elements:
            lines.append(format_interactive_element(el))

    return "\n".join(lines)


def format_graph_snapshot(snapshot: dict) -> str:
    """Renders the entire graph snapshot into a single readable text string."""
    components = snapshot.get("components", {})
    if not components:
        return "No active components mounted in registry."

    blocks = []
    for comp_id, comp_data in components.items():
        blocks.append(format_component(comp_id, comp_data))
    
    return "\n\n".join(blocks)
