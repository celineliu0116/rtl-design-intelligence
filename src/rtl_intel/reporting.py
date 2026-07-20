"""Text and JSON report rendering."""

from __future__ import annotations

import json
from typing import Dict, List

from .models import AnalysisReport


def render_json(report: AnalysisReport, pretty: bool = True) -> str:
    return json.dumps(report.to_dict(), indent=2 if pretty else None, sort_keys=False) + "\n"


def render_text(report: AnalysisReport, include_summary: bool = False) -> str:
    counts = report.counts()
    lines = [
        (
            f"RTL Intel analyzed {len(report.files)} file(s), found {len(report.modules)} module(s), "
            f"and reported {len(report.issues)} issue(s)."
        ),
        f"Errors: {counts['errors']}  Warnings: {counts['warnings']}  Info: {counts['info']}",
        "",
        "Hierarchy:",
    ]
    roots = report.hierarchy.get("roots", [])
    if roots:
        for root in roots:
            lines.extend(_render_tree(root, ""))
    else:
        lines.append("  (no modules)")

    lines.extend(["", "Issues:"])
    if not report.issues:
        lines.append("  No issues found.")
    else:
        for issue in report.issues:
            context = f" ({issue.module})" if issue.module else ""
            lines.append(
                f"  {issue.path}:{issue.line}: {issue.severity.upper()} {issue.rule}{context}: {issue.message}"
            )
            if issue.suggestion:
                lines.append(f"    help: {issue.suggestion}")

    if include_summary:
        lines.extend(["", "Design summary:", f"  {report.design_summary}"])
    return "\n".join(lines) + "\n"


def _render_tree(node: Dict[str, object], prefix: str) -> List[str]:
    flags = ""
    if node.get("unresolved"):
        flags = " [unresolved]"
    elif node.get("cycle"):
        flags = " [cycle]"
    instance = str(node.get("instance"))
    module = str(node.get("module"))
    label = module if instance == module else f"{instance}: {module}"
    lines = [f"{prefix}- {label}{flags}"]
    for child in node.get("children", []):
        lines.extend(_render_tree(child, prefix + "  "))
    return lines

