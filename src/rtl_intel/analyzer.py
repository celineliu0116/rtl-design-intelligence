"""Lint rules and design-level analysis orchestration."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, Dict, Iterable, List, Sequence, Set, Tuple, Union

from .hierarchy import build_hierarchy
from .models import AnalysisReport, Issue, Module, ProceduralBlock, Signal
from .parser import ASSIGNMENT_RE, VerilogParser, identifiers


RTL_EXTENSIONS = {".v", ".sv", ".vh", ".svh"}


def discover_files(paths: Sequence[Union[str, Path]]) -> Tuple[List[Path], List[Issue]]:
    files: Set[Path] = set()
    issues: List[Issue] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_file():
            files.add(path)
        elif path.is_dir():
            files.update(
                candidate
                for candidate in path.rglob("*")
                if candidate.is_file() and candidate.suffix.lower() in RTL_EXTENSIONS
            )
        else:
            issues.append(
                Issue(
                    path=str(path),
                    line=1,
                    rule="INPUT_NOT_FOUND",
                    severity="error",
                    message="Input path does not exist.",
                )
            )
    return sorted(files, key=lambda item: str(item)), issues


def analyze_paths(paths: Sequence[Union[str, Path]]) -> AnalysisReport:
    """Parse and analyze RTL files and directories."""
    files, issues = discover_files(paths)
    parser = VerilogParser()
    modules: List[Module] = []
    for path in files:
        parsed_modules, parse_issues = parser.parse_file(path)
        modules.extend(parsed_modules)
        issues.extend(parse_issues)

    seen: Dict[str, Module] = {}
    for module in modules:
        previous = seen.get(module.name)
        if previous:
            issues.append(
                Issue(
                    path=module.path,
                    line=module.line,
                    rule="DUPLICATE_MODULE",
                    severity="error",
                    message=(
                        f"Module '{module.name}' is also declared at "
                        f"{previous.path}:{previous.line}."
                    ),
                    module=module.name,
                    suggestion="Give each module a unique name or analyze one definition at a time.",
                )
            )
        else:
            seen[module.name] = module

    module_map = {module.name: module for module in modules}
    for module in modules:
        issues.extend(_lint_module(module, module_map))

    hierarchy, unresolved = build_hierarchy(modules)
    for parent, instance_name, module_type, line in unresolved:
        issues.append(
            Issue(
                path=parent.path,
                line=line,
                rule="UNKNOWN_MODULE",
                severity="warning",
                message=(
                    f"Instance '{instance_name}' references module '{module_type}', "
                    "which was not found in the analyzed files."
                ),
                module=parent.name,
                suggestion="Include the referenced RTL file or verify the module name.",
            )
        )

    if not files and not any(issue.rule == "INPUT_NOT_FOUND" for issue in issues):
        issues.append(
            Issue(
                path=str(paths[0] if paths else "."),
                line=1,
                rule="NO_RTL_FILES",
                severity="error",
                message="No .v, .sv, .vh, or .svh files were found.",
            )
        )

    issues.sort(key=lambda issue: (issue.path, issue.line, issue.rule, issue.message))
    summary = build_design_summary(files, modules, issues, hierarchy)
    return AnalysisReport(
        files=[str(path) for path in files],
        modules=modules,
        issues=issues,
        hierarchy=hierarchy,
        design_summary=summary,
    )


def _lint_module(module: Module, module_map: Dict[str, Module]) -> List[Issue]:
    issues: List[Issue] = []
    declarations = module.signal_map()
    reads: DefaultDict[str, int] = defaultdict(int)
    writes: DefaultDict[str, int] = defaultdict(int)

    def record_reads(expression: str) -> None:
        for name in identifiers(expression):
            if name in declarations:
                reads[name] += 1

    for assignment in module.continuous_assignments:
        if assignment.target in declarations:
            writes[assignment.target] += 1
        record_reads(assignment.rhs)

    for block in module.procedural_blocks:
        masked = list(block.text)
        for match in ASSIGNMENT_RE.finditer(block.text):
            target = match.group("lhs").split("[", 1)[0].strip()
            if target in declarations:
                writes[target] += 1
            for index in range(match.start("lhs"), match.end("lhs")):
                masked[index] = " "
        record_reads("".join(masked))
        issues.extend(_lint_assignment_style(module, block))
        if block.kind == "combinational":
            issues.extend(_lint_latches(module, block, declarations))

    _record_instance_usage(module, module_map, declarations, reads, writes)

    for signal in module.signals:
        if reads[signal.name] == 0:
            detail = (
                "is driven but its value is never read"
                if writes[signal.name]
                else "is never read or driven"
            )
            issues.append(
                _issue(
                    module,
                    signal.line,
                    "UNUSED_SIGNAL",
                    "warning",
                    f"Internal {signal.kind} '{signal.name}' {detail}.",
                    signal,
                    "Remove the signal or connect it to logic that consumes its value.",
                )
            )
        elif writes[signal.name] == 0:
            issues.append(
                _issue(
                    module,
                    signal.line,
                    "UNDRIVEN_SIGNAL",
                    "warning",
                    f"Internal signal '{signal.name}' is read but has no detected driver.",
                    signal,
                    "Drive the signal with a continuous assignment, procedural assignment, or child output.",
                )
            )

    for port in module.ports:
        if port.direction == "input" and reads[port.name] == 0:
            issues.append(
                _issue(
                    module,
                    port.line,
                    "UNUSED_INPUT",
                    "info",
                    f"Input port '{port.name}' is never read inside the module.",
                    port,
                    "Remove the port or use it in the module implementation.",
                )
            )
        elif port.direction == "output" and writes[port.name] == 0:
            issues.append(
                _issue(
                    module,
                    port.line,
                    "UNDRIVEN_OUTPUT",
                    "error",
                    f"Output port '{port.name}' has no detected assignment or child-module driver.",
                    port,
                    "Assign the output on every required path or connect it to a child output.",
                )
            )
    return issues


def _record_instance_usage(
    module: Module,
    module_map: Dict[str, Module],
    declarations: Dict[str, Signal],
    reads: DefaultDict[str, int],
    writes: DefaultDict[str, int],
) -> None:
    for instance in module.instances:
        child = module_map.get(instance.module_type)
        child_ports = {port.name: port for port in child.ports} if child else {}
        expressions: List[Tuple[str, Signal]] = []
        for port_name, expression in instance.connections.items():
            child_port = child_ports.get(port_name)
            if child_port:
                expressions.append((expression, child_port))
            else:
                for name in identifiers(expression):
                    if name in declarations:
                        reads[name] += 1
        if child:
            for index, expression in enumerate(instance.positional_connections):
                if index < len(child.ports):
                    expressions.append((expression, child.ports[index]))
        else:
            for expression in instance.positional_connections:
                for name in identifiers(expression):
                    if name in declarations:
                        reads[name] += 1

        for expression, child_port in expressions:
            names = [name for name in identifiers(expression) if name in declarations]
            for name in names:
                if child_port.direction in {"output", "inout"}:
                    writes[name] += 1
                if child_port.direction in {"input", "inout"}:
                    reads[name] += 1


def _lint_assignment_style(module: Module, block: ProceduralBlock) -> List[Issue]:
    issues: List[Issue] = []
    for assignment in block.assignments:
        signal = module.signal_map().get(assignment.target)
        if block.kind == "sequential" and assignment.operator == "=":
            issues.append(
                _issue(
                    module,
                    assignment.line,
                    "BLOCKING_IN_SEQUENTIAL",
                    "warning",
                    f"Sequential block uses blocking assignment for '{assignment.target}'.",
                    signal,
                    "Use a non-blocking assignment (<=) for clocked state updates.",
                )
            )
        elif block.kind == "combinational" and assignment.operator == "<=":
            issues.append(
                _issue(
                    module,
                    assignment.line,
                    "NONBLOCKING_IN_COMBINATIONAL",
                    "warning",
                    f"Combinational block uses non-blocking assignment for '{assignment.target}'.",
                    signal,
                    "Use a blocking assignment (=) for combinational logic.",
                )
            )
    return issues


def _lint_latches(
    module: Module, block: ProceduralBlock, declarations: Dict[str, Signal]
) -> List[Issue]:
    issues: List[Issue] = []
    targets = {assignment.target for assignment in block.assignments if assignment.target in declarations}
    for target in sorted(targets):
        if _definitely_assigned(block, target):
            continue
        signal = declarations[target]
        first_assignment = next(
            assignment for assignment in block.assignments if assignment.target == target
        )
        issues.append(
            _issue(
                module,
                first_assignment.line,
                "POSSIBLE_LATCH",
                "warning",
                (
                    f"Combinational signal '{target}' may retain its previous value because "
                    "no unconditional/default assignment was detected."
                ),
                signal,
                "Set a default value before conditional logic or assign the signal in every branch.",
            )
        )
    return issues


def _definitely_assigned(block: ProceduralBlock, target: str) -> bool:
    target_pattern = re.compile(rf"\b{re.escape(target)}\b(?:\s*\[[^\]]+\])?\s*(?:=|<=)")
    assignments = list(target_pattern.finditer(block.text))
    if not assignments:
        return False

    if any(_is_unconditional_position(block.text, assignment.start()) for assignment in assignments):
        return True

    # A default case arm is a catch-all assignment for case-style logic.
    default = re.search(r"\bdefault\s*:(.*?)(?:\bendcase\b|$)", block.text, re.DOTALL)
    if default and target_pattern.search(default.group(1)):
        return True

    # For the supported simple subset, a two-arm if/else assigning the same
    # target is considered complete. Nested branch completeness is intentionally
    # left to a future AST-based data-flow pass.
    if re.search(r"\belse\b", block.text) and len(assignments) >= 2:
        return True
    return False


def _is_unconditional_position(text: str, position: int) -> bool:
    """Return whether a simple assignment sits outside conditional scopes.

    This small structural check handles the common default-before/default-after
    coding styles while remaining conservative for deeply nested constructs.
    """
    prefix = text[:position]
    begin_depth = 0
    case_depth = 0
    for token in re.finditer(r"\b(endcase|casez|casex|case|begin|end)\b", prefix):
        word = token.group(1)
        if word == "begin":
            begin_depth += 1
        elif word == "end":
            begin_depth = max(0, begin_depth - 1)
        elif word == "endcase":
            case_depth = max(0, case_depth - 1)
        else:
            case_depth += 1

    if case_depth or begin_depth > 1:
        return False
    # Covers single-statement branches without begin/end.
    trailing_control = re.search(
        r"(?:\bif\s*\([^)]*\)|\bfor\s*\([^)]*\)|\bwhile\s*\([^)]*\)|\belse)\s*$",
        prefix,
        re.DOTALL,
    )
    return trailing_control is None


def _issue(
    module: Module,
    line: int,
    rule: str,
    severity: str,
    message: str,
    signal: Signal = None,
    suggestion: str = None,
) -> Issue:
    return Issue(
        path=module.path,
        line=line,
        rule=rule,
        severity=severity,
        message=message,
        module=module.name,
        signal=signal.name if signal else None,
        suggestion=suggestion,
    )


def build_design_summary(
    files: Sequence[Path],
    modules: Sequence[Module],
    issues: Sequence[Issue],
    hierarchy: Dict[str, object],
) -> str:
    """Create a deterministic natural-language design overview."""
    roots = hierarchy.get("root_modules", [])
    instance_count = sum(len(module.instances) for module in modules)
    sequential_count = sum(
        block.kind == "sequential" for module in modules for block in module.procedural_blocks
    )
    combinational_count = sum(
        block.kind == "combinational" for module in modules for block in module.procedural_blocks
    )
    errors = sum(issue.severity == "error" for issue in issues)
    warnings = sum(issue.severity == "warning" for issue in issues)

    if not modules:
        return f"No RTL modules were discovered in {len(files)} analyzed file(s)."

    root_text = ", ".join(roots) if roots else "none detected"
    sentences = [
        (
            f"The design contains {len(modules)} module(s) across {len(files)} RTL file(s), "
            f"with top-level module(s): {root_text}."
        ),
        (
            f"It instantiates {instance_count} child module(s) and includes "
            f"{combinational_count} combinational and {sequential_count} sequential procedural block(s)."
        ),
    ]

    clocks = sorted(
        {
            port.name
            for module in modules
            for port in module.ports
            if port.direction == "input" and re.search(r"(^|_)(clk|clock)($|_)", port.name, re.I)
        }
    )
    resets = sorted(
        {
            port.name
            for module in modules
            for port in module.ports
            if port.direction == "input" and re.search(r"(^|_)(rst|reset)(n)?($|_)", port.name, re.I)
        }
    )
    if clocks or resets:
        details = []
        if clocks:
            details.append("clock-like inputs " + ", ".join(clocks))
        if resets:
            details.append("reset-like inputs " + ", ".join(resets))
        sentences.append("Detected " + " and ".join(details) + ".")

    if errors or warnings:
        sentences.append(
            f"Linting found {errors} error(s) and {warnings} warning(s); inspect the structured issues for source locations and suggested fixes."
        )
    else:
        sentences.append("No error- or warning-level lint findings were detected by the enabled rules.")
    return " ".join(sentences)
