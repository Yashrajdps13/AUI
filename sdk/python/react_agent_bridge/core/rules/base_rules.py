from typing import Optional
from react_agent_bridge.core.rules.result import RuleViolation
from react_agent_bridge.core.graph.state_graph import ApplicationStateGraph


def target_mounted_rule(command: dict, graph: ApplicationStateGraph) -> Optional[RuleViolation]:
    """Ensures the target component is currently mounted in the state graph."""
    target = command.get("target")
    if not target:
        return None

    # setState and queryState target format is ComponentId.slotKey
    if command.get("type") in ["setState", "queryState"]:
        comp_id = target.rsplit(".", 1)[0] if "." in target else target
    else:
        comp_id = target

    if comp_id not in graph.components:
        return RuleViolation(
            rule_name="TargetMountedRule",
            message=f"Component '{comp_id}' is not currently mounted in the application state graph.",
            target=target
        )
    return None


def slot_exists_rule(command: dict, graph: ApplicationStateGraph) -> Optional[RuleViolation]:
    """For state operations, ensures the state slot key actually exists on the target component."""
    cmd_type = command.get("type")
    if cmd_type not in ["setState", "queryState"]:
        return None

    target = command.get("target", "")
    parts = target.rsplit(".", 1)
    if len(parts) != 2:
        return RuleViolation(
            rule_name="SlotExistsRule",
            message=f"Invalid target state slot format: '{target}'. Expected 'ComponentId.slotKey'.",
            target=target
        )

    comp_id, slot_key = parts
    comp = graph.get_component(comp_id)
    if comp and slot_key not in comp.state_slots:
        return RuleViolation(
            rule_name="SlotExistsRule",
            message=f"State slot '{slot_key}' does not exist on component '{comp_id}'.",
            target=target
        )
    return None


def no_direct_collection_mutation_rule(command: dict, graph: ApplicationStateGraph) -> Optional[RuleViolation]:
    """setState should not directly mutate lists or objects containing more than one key."""
    if command.get("type") != "setState":
        return None

    target = command.get("target", "")
    parts = target.rsplit(".", 1)
    if len(parts) != 2:
        return None

    comp_id, slot_key = parts
    comp = graph.get_component(comp_id)
    if not comp:
        return None

    slot = comp.state_slots.get(slot_key)
    if slot and slot.value is not None:
        # Check if the current value is a list or dict with size > 1
        if isinstance(slot.value, list) or (isinstance(slot.value, dict) and len(slot.value) > 1):
            return RuleViolation(
                rule_name="NoDirectCollectionMutationRule",
                message=(
                    f"Direct setState mutation of collections on '{target}' is prohibited. "
                    f"Use a callAction method to modify collections to avoid state corruption."
                ),
                target=target
            )
    return None


def sensitive_slot_read_protection_rule(command: dict, graph: ApplicationStateGraph) -> Optional[RuleViolation]:
    """queryState should not be called directly on sensitive slots."""
    if command.get("type") != "queryState":
        return None

    target = command.get("target", "")
    if graph.is_slot_sensitive(target):
        return RuleViolation(
            rule_name="SensitiveSlotReadProtectionRule",
            message=f"Reading sensitive state target '{target}' via queryState is blocked. Values are redacted.",
            target=target
        )
    return None


def disabled_element_rule(command: dict, graph: ApplicationStateGraph) -> Optional[RuleViolation]:
    """dispatchEvent click events must target elements that are visible and not disabled."""
    if command.get("type") != "dispatchEvent" or command.get("event") != "click":
        return None

    target_comp_id = command.get("target")
    selector = command.get("payload")
    if not selector or not isinstance(selector, str):
        return None

    comp = graph.get_component(target_comp_id)
    if not comp:
        return None

    # Check interactive elements
    for el in comp.interactive_elements:
        if el.selector == selector:
            if el.disabled:
                return RuleViolation(
                    rule_name="DisabledElementRule",
                    message=f"Cannot click element '{selector}' on component '{target_comp_id}': element is disabled.",
                    target=target_comp_id,
                    details={"selector": selector}
                )
            if not el.visible:
                return RuleViolation(
                    rule_name="DisabledElementRule",
                    message=f"Cannot click element '{selector}' on component '{target_comp_id}': element is not visible.",
                    target=target_comp_id,
                    details={"selector": selector}
                )
            break

    return None


def action_registered_rule(command: dict, graph: ApplicationStateGraph) -> Optional[RuleViolation]:
    """callAction target action name must be registered on the target component."""
    if command.get("type") != "callAction":
        return None

    target = command.get("target", "")
    parts = target.rsplit(".", 1)
    if len(parts) != 2:
        return RuleViolation(
            rule_name="ActionRegisteredRule",
            message=f"Invalid action target format: '{target}'. Expected 'ComponentId.actionName'.",
            target=target
        )

    comp_id, action_name = parts
    comp = graph.get_component(comp_id)
    if comp and action_name not in comp.actions:
        return RuleViolation(
            rule_name="ActionRegisteredRule",
            message=f"Action '{action_name}' is not registered on component '{comp_id}'. Registered: {comp.actions}",
            target=target
        )
    return None


def writeable_slot_rule(command: dict, graph: ApplicationStateGraph) -> Optional[RuleViolation]:
    """Ensures state mutation operations do not target slots that are writeable only by the user."""
    if command.get("type") != "setState":
        return None

    target = command.get("target", "")
    parts = target.rsplit(".", 1)
    if len(parts) != 2:
        return None

    comp_id, slot_key = parts
    comp = graph.get_component(comp_id)
    if not comp:
        return None

    slot = comp.state_slots.get(slot_key)
    if slot and getattr(slot, "writeable", None) == "user":
        return RuleViolation(
            rule_name="WriteableSlotRule",
            message=f"Direct setState mutation of '{target}' is blocked. State is marked as user-writable only.",
            target=target
        )
    return None


ALL_BASE_RULES = [
    target_mounted_rule,
    slot_exists_rule,
    no_direct_collection_mutation_rule,
    sensitive_slot_read_protection_rule,
    disabled_element_rule,
    action_registered_rule,
    writeable_slot_rule,
]
