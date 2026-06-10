import os
import time
import re
import logging
from typing import Dict, Any, List, Optional
from react_agent_bridge.discovery.generator.templates import (
    HEADER_TEMPLATE, GLOSSARY_HEADER, COMPONENT_TEMPLATE, SLOT_TEMPLATE,
    WORKFLOWS_HEADER, WORKFLOW_TEMPLATE, CONSTRAINTS_HEADER, CONSTRAINT_TEMPLATE,
    SENSITIVE_CONTEXT_TEMPLATE
)

logger = logging.getLogger("react_agent_bridge.discovery.generator.context_writer")


class ContextWriter:
    """
    Generates and updates the agent-context.md file, preserving manual
    descriptions, promoted constraints, and custom sections written by the developer.
    """
    def __init__(self, output_path: str = "./agent-context.md"):
        self.output_path = output_path

    def _parse_existing_file(self) -> Dict[str, Any]:
        """
        Parses the existing agent-context.md file if it exists.
        Returns a dict of parsed manual developer edits:
        {
            "descriptions": { "Component.slot": "custom description" },
            "confirmed_constraints": { "ConstraintName": { "status": "CONFIRMED", "description": "...", ... } },
            "sensitive_context": "..."
        }
        """
        res = {
            "descriptions": {},
            "confirmed_constraints": {},
            "sensitive_context": ""
        }

        if not os.path.exists(self.output_path):
            return res

        try:
            with open(self.output_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 1. Parse Sensitive Context section
            sensitive_parts = content.split("## Sensitive Context")
            if len(sensitive_parts) > 1:
                # Capture everything after "## Sensitive Context", stripping out template comments if desired,
                # but to be safe, just preserve the exact text block.
                res["sensitive_context"] = sensitive_parts[1].strip()

            # 2. Parse Glossary descriptions
            # We look for components (### Comp) and slots (#### slot)
            lines = content.splitlines()
            current_comp = None
            current_slot = None
            for idx, line in enumerate(lines):
                line = line.strip()
                if line.startswith("### "):
                    current_comp = line[4:].strip()
                    current_slot = None
                elif line.startswith("#### "):
                    current_slot = line[5:].strip()
                elif line.startswith("# ") and "Description:" in line and current_comp and current_slot:
                    # Check if this description is custom
                    # Format is: "# [REVIEW NEEDED] Description: text" or "# Description: text"
                    desc_match = re.search(r"^#\s+(?:\[REVIEW NEEDED\]\s+)?Description:\s*(.*)$", line)
                    if desc_match:
                        desc_text = desc_match.group(1).strip()
                        # If description does not look like auto-generated default draft, preserve it
                        is_default = desc_text.startswith(f"Tracks the {current_slot} state for")
                        if not is_default:
                            key = f"{current_comp}.{current_slot}"
                            res["descriptions"][key] = desc_text

            # 3. Parse Confirmed Constraints
            # We look for constraints under "## Constraints"
            constraints_part = content.split("## Constraints")
            if len(constraints_part) > 1:
                constraint_blocks = constraints_part[1].split("### ")
                for block in constraint_blocks[1:]:
                    block_lines = block.splitlines()
                    if not block_lines:
                        continue
                    constraint_name = block_lines[0].strip()
                    
                    # Search for Status
                    status = "INFERRED"
                    desc_lines = []
                    for bl in block_lines[1:]:
                        bl_strip = bl.strip()
                        if bl_strip.startswith("# Status:"):
                            status = bl_strip.split("Status:")[1].strip()
                        elif bl_strip.startswith("#"):
                            continue
                        elif bl_strip:
                            desc_lines.append(bl_strip)

                    if status == "CONFIRMED":
                        res["confirmed_constraints"][constraint_name] = {
                            "status": "CONFIRMED",
                            "description": "\n".join(desc_lines)
                        }

        except Exception as e:
            logger.error(f"Failed to parse existing agent-context.md: {e}", exc_info=True)

        return res

    def write(
        self,
        annotations: Dict[str, Dict[str, Any]],
        workflows: List[Dict[str, Any]],
        inferred_constraints: List[Dict[str, Any]],
        session_metrics: Dict[str, Any],
        version_hash: str
    ) -> str:
        """
        Generates/updates agent-context.md, merging manually confirmed content.
        Returns the console report string.
        """
        existing = self._parse_existing_file()

        # 1. Generate Header
        t_str = time.strftime('%Y-%m-%d %H:%M:%S')
        total_sessions = session_metrics.get("total", 0)
        human_count = session_metrics.get("human", 0)
        agent_count = session_metrics.get("agent", 0)

        header = HEADER_TEMPLATE.format(
            timestamp=t_str,
            session_count=total_sessions,
            human_count=human_count,
            agent_count=agent_count,
            version_hash=version_hash
        )

        # 2. Generate Glossary
        glossary = GLOSSARY_HEADER.format(session_count=total_sessions, timestamp=t_str)
        # Group annotations by component
        comp_slots: Dict[str, List[tuple]] = {}
        for target, ann in annotations.items():
            comp_name, slot_key = target.rsplit(".", 1)
            if comp_name not in comp_slots:
                comp_slots[comp_name] = []
            comp_slots[comp_name].append((slot_key, ann))

        for comp_name, slots in sorted(comp_slots.items()):
            all_routes = set()
            for _, ann in slots:
                all_routes.update(ann.get("routes_observed_on", []))
            
            routes_str = str(sorted(list(all_routes)))
            glossary += COMPONENT_TEMPLATE.format(
                component_name=comp_name,
                routes=routes_str,
                session_count=total_sessions
            )

            for slot_key, ann in sorted(slots, key=lambda x: x[0]):
                target = f"{comp_name}.{slot_key}"
                
                # Check for custom description override
                desc = ann["description_draft"]
                review_marker = "[REVIEW NEEDED] "
                if target in existing["descriptions"]:
                    desc = existing["descriptions"][target]
                    review_marker = ""

                examples_str = ", ".join(ann["observed_value_examples"][:5])
                glossary += SLOT_TEMPLATE.format(
                    slot_key=slot_key,
                    inferred_type=ann["inferred_type"],
                    sensitive="yes" if ann["is_probably_sensitive"] else "no",
                    derived="yes" if ann["is_derived"] else "no",
                    volatile="yes" if ann["is_volatile"] else "no",
                    confidence=ann["confidence"],
                    review_marker=review_marker,
                    description=desc,
                    examples=examples_str
                )
            glossary += "\n"

        # 3. Generate Workflows
        workflows_sec = WORKFLOWS_HEADER.format(workflow_count=len(workflows))
        for wf in workflows:
            pre_lines = []
            for pre in wf.get("preconditions", []):
                val_suffix = f" {pre['value']}" if pre.get("value") is not None else ""
                pre_lines.append(f"- {pre['slot_target']} {pre['operator']}{val_suffix}")
            pre_str = "\n".join(pre_lines) if pre_lines else "None identified"

            step_lines = []
            for s in wf["steps"]:
                val_suffix = f" {s['value']}" if s.get("value") is not None else ""
                step_lines.append(f"- {s['description']} ({s['target']} {s['operator']}{val_suffix})")
            steps_str = "\n".join(step_lines)

            sc = wf["success_condition"]
            sc_val_suffix = f" {sc.value}" if sc.value is not None else ""
            sc_str = f"{sc.target} {sc.operator}{sc_val_suffix}"

            fail_cond = wf["failure_condition"]
            if fail_cond:
                fc_val_suffix = f" {fail_cond.value}" if fail_cond.value is not None else ""
                fail_str = f"{fail_cond.target} {fail_cond.operator}{fc_val_suffix}"
            else:
                fail_str = "None identified"

            workflows_sec += WORKFLOW_TEMPLATE.format(
                workflow_name=wf["name"],
                confidence=wf["confidence"],
                session_count=wf["session_count"],
                avg_step_count=len(wf["steps"]),
                preconditions=pre_str,
                steps=steps_str,
                success_condition=sc_str,
                failure_condition=fail_str
            )
            workflows_sec += "\n"

        # 4. Generate Constraints
        # Merge inferred and confirmed constraints
        final_constraints = {}
        # Prepopulate with confirmed constraints
        for name, details in existing["confirmed_constraints"].items():
            final_constraints[name] = {
                "status": "CONFIRMED",
                "description": details["description"],
                "constraint_type": "inferred",
                "confidence": 1.0,
                "session_count": total_sessions,
                "evidence_summary": "Manually verified and promoted by developer."
            }

        # Add newly inferred constraints if not already confirmed
        for ic in inferred_constraints:
            name = ic["name"]
            if name not in final_constraints:
                final_constraints[name] = {
                    "status": "INFERRED",
                    "description": ic["description"],
                    "constraint_type": ic["constraint_type"],
                    "confidence": ic["confidence"],
                    "session_count": ic["session_count"],
                    "evidence_summary": ic["evidence_summary"]
                }

        confirmed_cnt = sum(1 for c in final_constraints.values() if c["status"] == "CONFIRMED")
        inferred_cnt = len(final_constraints) - confirmed_cnt

        constraints_sec = CONSTRAINTS_HEADER.format(confirmed_count=confirmed_cnt, inferred_count=inferred_cnt)
        for name, c in sorted(final_constraints.items()):
            constraints_sec += CONSTRAINT_TEMPLATE.format(
                constraint_name=name,
                status=c["status"],
                constraint_type=c["constraint_type"],
                confidence=c["confidence"],
                session_count=c["session_count"],
                evidence_summary=c["evidence_summary"],
                description=c["description"]
            )
            constraints_sec += "\n"

        # 5. Generate Sensitive Context
        sensitive_sec = SENSITIVE_CONTEXT_TEMPLATE
        if existing["sensitive_context"]:
            sensitive_sec += "\n" + existing["sensitive_context"]

        # Compose entire document
        full_content = header + glossary + workflows_sec + constraints_sec + sensitive_sec

        # Write to file
        with open(self.output_path, "w", encoding="utf-8") as f:
            f.write(full_content)

        # Generate Console Report
        report = []
        report.append("Discovery Mode Report")
        report.append("=====================")
        report.append(f"Sessions analysed: {total_sessions} ({human_count} human, {agent_count} agent)")
        report.append(f"Workflows identified: {len(workflows)}")
        for wf in workflows:
            report.append(f"  {wf['name']}: {wf['confidence']:.0%} confidence ({wf['session_count']} sessions)")
        report.append(f"Constraints proposed: {len(final_constraints)} ({confirmed_cnt} confirmed, {inferred_cnt} awaiting review)")
        
        volatile_keys = [k for k, v in annotations.items() if v.get("is_volatile")]
        report.append(f"Volatile slots detected: {len(volatile_keys)}")
        
        sensitive_keys = [k for k, v in annotations.items() if v.get("is_probably_sensitive")]
        report.append(f"Sensitive slots auto-redacted: {len(sensitive_keys)}")
        for sk in sensitive_keys[:5]:
            report.append(f"  {sk}")
        
        report.append(f"Next update scheduled: every {session_metrics.get('interval_hours', 24)}h")
        report.append(f"Type agent-context.md to view the generated file.")

        return "\n".join(report)
