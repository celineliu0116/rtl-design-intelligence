"""A small, dependency-free parser for a useful Verilog/SystemVerilog subset.

This parser is deliberately structural rather than grammar-complete. It recognizes
modules, declarations, assignments, always blocks, and module instances while
preserving source locations for lint diagnostics.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .models import Assignment, Instance, Issue, Module, ProceduralBlock, Signal


IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_$]*\b")
MODULE_START_RE = re.compile(r"\bmodule\s+(?:automatic\s+)?([A-Za-z_][A-Za-z0-9_$]*)")
ENDMODULE_RE = re.compile(r"\bendmodule\b")
ALWAYS_RE = re.compile(r"\b(always_comb|always_ff|always_latch|always)\b")
ASSIGNMENT_RE = re.compile(
    r"(?<![\w.$])(?P<lhs>[A-Za-z_][A-Za-z0-9_$]*(?:\s*\[[^\]]+\])?)"
    r"\s*(?P<op><=|=(?!=))\s*(?P<rhs>[^;]+);"
)
CONTINUOUS_ASSIGN_RE = re.compile(
    r"\bassign\s+(?P<lhs>[A-Za-z_][A-Za-z0-9_$]*(?:\s*\[[^\]]+\])?)"
    r"\s*=\s*(?P<rhs>[^;]+);"
)

RESERVED_INSTANCE_WORDS = {
    "always",
    "always_comb",
    "always_ff",
    "always_latch",
    "assign",
    "begin",
    "case",
    "casex",
    "casez",
    "else",
    "end",
    "for",
    "function",
    "generate",
    "if",
    "initial",
    "logic",
    "priority",
    "reg",
    "task",
    "unique",
    "wire",
    "while",
}


def strip_comments(text: str) -> str:
    """Remove comments while retaining newlines and character offsets."""
    result = list(text)
    index = 0
    in_string = False
    while index < len(text):
        if text[index] == '"' and (index == 0 or text[index - 1] != "\\"):
            in_string = not in_string
            index += 1
            continue
        if not in_string and text.startswith("//", index):
            end = text.find("\n", index + 2)
            if end == -1:
                end = len(text)
            for offset in range(index, end):
                result[offset] = " "
            index = end
            continue
        if not in_string and text.startswith("/*", index):
            end_marker = text.find("*/", index + 2)
            end = len(text) if end_marker == -1 else end_marker + 2
            for offset in range(index, end):
                if result[offset] != "\n":
                    result[offset] = " "
            index = end
            continue
        index += 1
    return "".join(result)


def split_top_level(text: str, delimiter: str = ",") -> List[str]:
    """Split on a delimiter only when outside (), [], and {}."""
    parts: List[str] = []
    start = 0
    depths = {"(": 0, "[": 0, "{": 0}
    matching = {")": "(", "]": "[", "}": "{"}
    for index, character in enumerate(text):
        if character in depths:
            depths[character] += 1
        elif character in matching:
            opener = matching[character]
            depths[opener] = max(0, depths[opener] - 1)
        elif character == delimiter and not any(depths.values()):
            parts.append(text[start:index])
            start = index + 1
    parts.append(text[start:])
    return parts


def find_matching(text: str, start: int, opener: str = "(", closer: str = ")") -> int:
    depth = 0
    for index in range(start, len(text)):
        if text[index] == opener:
            depth += 1
        elif text[index] == closer:
            depth -= 1
            if depth == 0:
                return index
    return -1


def line_at(text: str, offset: int, base_line: int = 1) -> int:
    return base_line + text.count("\n", 0, offset)


def _width_from(fragment: str) -> Optional[str]:
    """mainly used to extract a Verilog signal or port’s declared bit range. e.g., `[7:0]` or `[WIDTH-1:0]`. Returns None if no range is found."""
    match = re.search(r"\[[^\]]+\]", fragment)
    return match.group(0).strip() if match else None


def _declaration_name(fragment: str) -> Optional[str]:
    fragment = fragment.split("=", 1)[0].strip()
    match = re.match(r"([A-Za-z_][A-Za-z0-9_$]*)\s*(?:\[[^\]]+\]\s*)*$", fragment)
    return match.group(1) if match else None


class VerilogParser:
    """Parse RTL source text or files into lightweight structural models."""

    def parse_file(self, path: Path) -> Tuple[List[Module], List[Issue]]:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            return [], [
                Issue(
                    path=str(path),
                    line=1,
                    rule="PARSE_FILE_ERROR",
                    severity="error",
                    message=f"Could not read RTL source: {error}",
                )
            ]
        return self.parse_text(text, str(path))

    def parse_text(self, text: str, path: str = "<memory>") -> Tuple[List[Module], List[Issue]]:
        cleaned = strip_comments(text)
        modules: List[Module] = []
        issues: List[Issue] = []
        cursor = 0

        while True:
            start_match = MODULE_START_RE.search(cleaned, cursor)
            if not start_match:
                break
            end_match = ENDMODULE_RE.search(cleaned, start_match.end())
            if not end_match:
                issues.append(
                    Issue(
                        path=path,
                        line=line_at(cleaned, start_match.start()),
                        rule="PARSE_MISSING_ENDMODULE",
                        severity="error",
                        message=f"Module '{start_match.group(1)}' has no matching endmodule.",
                        module=start_match.group(1),
                        suggestion="Add an endmodule declaration.",
                    )
                )
                break

            module_text = cleaned[start_match.start() : end_match.end()]
            module = self._parse_module(
                module_text,
                path=path,
                base_line=line_at(cleaned, start_match.start()),
                name=start_match.group(1),
                name_end=start_match.end() - start_match.start(),
            )
            modules.append(module)
            cursor = end_match.end()

        if not modules and not issues and cleaned.strip():
            issues.append(
                Issue(
                    path=path,
                    line=1,
                    rule="PARSE_NO_MODULE",
                    severity="warning",
                    message="No module declaration was found in this RTL file.",
                )
            )
        return modules, issues

    def _parse_module(
        self, module_text: str, path: str, base_line: int, name: str, name_end: int
    ) -> Module:
        header_end, port_text, port_offset = self._parse_header(module_text, name_end)
        body_end_match = ENDMODULE_RE.search(module_text, header_end)
        body_end = body_end_match.start() if body_end_match else len(module_text)
        body = module_text[header_end:body_end]
        body_base_line = line_at(module_text, header_end, base_line)

        ports = self._parse_ansi_ports(port_text, module_text, port_offset, base_line)
        body_ports = self._parse_body_ports(body, body_base_line)
        ports = self._merge_ports(ports, body_ports)

        blocks_with_spans = self._parse_procedural_blocks(body, body_base_line)
        blocks = [block for block, _start, _end in blocks_with_spans]
        signals = self._parse_internal_signals(body, body_base_line, blocks_with_spans, ports)
        continuous = self._parse_continuous_assignments(body, body_base_line)
        instances = self._parse_instances(body, body_base_line, blocks_with_spans)

        return Module(
            name=name,
            path=path,
            line=base_line,
            ports=ports,
            signals=signals,
            continuous_assignments=continuous,
            procedural_blocks=blocks,
            instances=instances,
        )

    def _parse_header(self, text: str, name_end: int) -> Tuple[int, str, int]:
        cursor = name_end
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor < len(text) and text[cursor] == "#":
            cursor += 1
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
            if cursor < len(text) and text[cursor] == "(":
                end = find_matching(text, cursor)
                cursor = len(text) if end == -1 else end + 1
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1

        port_text = ""
        port_offset = cursor
        if cursor < len(text) and text[cursor] == "(":
            end = find_matching(text, cursor)
            if end != -1:
                port_offset = cursor + 1
                port_text = text[port_offset:end]
                cursor = end + 1
        semicolon = text.find(";", cursor)
        header_end = len(text) if semicolon == -1 else semicolon + 1
        return header_end, port_text, port_offset

    def _parse_ansi_ports(
        self, port_text: str, full_text: str, offset: int, base_line: int
    ) -> List[Signal]:
        ports: List[Signal] = []
        direction: Optional[str] = None
        kind = "wire"
        width: Optional[str] = None
        signed = False
        search_offset = 0

        for raw_part in split_top_level(port_text):
            part = re.sub(r"\(\*.*?\*\)", "", raw_part, flags=re.DOTALL).strip()
            part_location = port_text.find(raw_part, search_offset)
            search_offset = max(search_offset, part_location + len(raw_part))
            declaration = re.match(r"^(input|output|inout)\b(.*)$", part, re.DOTALL)
            if declaration:
                direction = declaration.group(1)
                remainder = declaration.group(2).strip()
                kind_match = re.match(r"^(wire|logic|reg|bit)\b(.*)$", remainder, re.DOTALL)
                if kind_match:
                    kind = kind_match.group(1)
                    remainder = kind_match.group(2).strip()
                else:
                    kind = "wire"
                signed = bool(re.search(r"\bsigned\b", remainder))
                remainder = re.sub(r"\bsigned\b", "", remainder).strip()
                width = _width_from(remainder)
                if width:
                    remainder = remainder.replace(width, "", 1).strip()
                name = _declaration_name(remainder)
            else:
                name = _declaration_name(part)

            if direction and name:
                ports.append(
                    Signal(
                        name=name,
                        kind=kind,
                        direction=direction,
                        width=width,
                        signed=signed,
                        line=line_at(full_text, offset + max(0, part_location), base_line),
                    )
                )
        return ports

    def _parse_body_ports(self, body: str, base_line: int) -> List[Signal]:
        ports: List[Signal] = []
        pattern = re.compile(r"(?m)^\s*(input|output|inout)\b([^;]*);")
        for match in pattern.finditer(body):
            direction = match.group(1)
            remainder = match.group(2).strip()
            kind_match = re.match(r"^(wire|logic|reg|bit)\b(.*)$", remainder, re.DOTALL)
            kind = kind_match.group(1) if kind_match else "wire"
            remainder = kind_match.group(2).strip() if kind_match else remainder
            signed = bool(re.search(r"\bsigned\b", remainder))
            remainder = re.sub(r"\bsigned\b", "", remainder).strip()
            width = _width_from(remainder)
            if width:
                remainder = remainder.replace(width, "", 1).strip()
            for fragment in split_top_level(remainder):
                name = _declaration_name(fragment.strip())
                if name:
                    ports.append(
                        Signal(
                            name=name,
                            kind=kind,
                            direction=direction,
                            width=width,
                            signed=signed,
                            line=line_at(body, match.start(), base_line),
                        )
                    )
        return ports

    @staticmethod
    def _merge_ports(header_ports: Sequence[Signal], body_ports: Sequence[Signal]) -> List[Signal]:
        merged: Dict[str, Signal] = {port.name: port for port in header_ports}
        for port in body_ports:
            existing = merged.get(port.name)
            if existing and existing.direction is None:
                existing.direction = port.direction
                existing.kind = port.kind
                existing.width = port.width
                existing.signed = port.signed
            else:
                merged[port.name] = port
        return list(merged.values())

    def _parse_internal_signals(
        self,
        body: str,
        base_line: int,
        blocks: Sequence[Tuple[ProceduralBlock, int, int]],
        ports: Sequence[Signal],
    ) -> List[Signal]:
        signals: List[Signal] = []
        port_names = {port.name for port in ports}
        pattern = re.compile(r"(?m)^\s*(wire|logic|reg|bit)\b([^;]*);")
        for match in pattern.finditer(body):
            if any(start <= match.start() < end for _block, start, end in blocks):
                continue
            kind = match.group(1)
            remainder = match.group(2).strip()
            signed = bool(re.search(r"\bsigned\b", remainder))
            remainder = re.sub(r"\bsigned\b", "", remainder).strip()
            width = _width_from(remainder)
            if width:
                remainder = remainder.replace(width, "", 1).strip()
            for fragment in split_top_level(remainder):
                name = _declaration_name(fragment.strip())
                if name and name not in port_names:
                    signals.append(
                        Signal(
                            name=name,
                            kind=kind,
                            width=width,
                            signed=signed,
                            line=line_at(body, match.start(), base_line),
                        )
                    )
        return signals

    def _parse_procedural_blocks(
        self, body: str, base_line: int
    ) -> List[Tuple[ProceduralBlock, int, int]]:
        results: List[Tuple[ProceduralBlock, int, int]] = []
        cursor = 0
        while True:
            match = ALWAYS_RE.search(body, cursor)
            if not match:
                break
            keyword = match.group(1)
            header_end = match.end()
            sensitivity = ""
            # Both classic `always` and `always_ff` commonly carry an explicit
            # event control. Accept it on any always flavor so the following
            # begin/end block is extracted in full.
            at = re.match(r"\s*@\s*", body[header_end:])
            if at:
                sensitivity_start = header_end + at.end()
                if sensitivity_start < len(body) and body[sensitivity_start] == "(":
                    sensitivity_end = find_matching(body, sensitivity_start)
                    if sensitivity_end != -1:
                        sensitivity = body[sensitivity_start + 1 : sensitivity_end].strip()
                        header_end = sensitivity_end + 1
                elif sensitivity_start < len(body) and body[sensitivity_start] == "*":
                    sensitivity = "*"
                    header_end = sensitivity_start + 1
                elif sensitivity_start < len(body):
                    token = IDENTIFIER_RE.match(body, sensitivity_start)
                    if token:
                        sensitivity = token.group(0)
                        header_end = token.end()

            kind = self._block_kind(keyword, sensitivity)
            statement_start = header_end
            while statement_start < len(body) and body[statement_start].isspace():
                statement_start += 1
            if body.startswith("begin", statement_start) and re.match(r"begin\b", body[statement_start:]):
                statement_end = self._find_end_token(body, statement_start)
            else:
                semicolon = body.find(";", statement_start)
                statement_end = len(body) if semicolon == -1 else semicolon + 1
            text = body[match.start() : statement_end]
            assignments = [
                Assignment(
                    lhs=item.group("lhs").replace(" ", ""),
                    rhs=item.group("rhs").strip(),
                    operator=item.group("op"),
                    line=line_at(body, match.start() + item.start(), base_line),
                )
                for item in ASSIGNMENT_RE.finditer(text)
            ]
            block = ProceduralBlock(
                kind=kind,
                sensitivity=sensitivity,
                text=text,
                line=line_at(body, match.start(), base_line),
                assignments=assignments,
            )
            results.append((block, match.start(), statement_end))
            cursor = max(statement_end, match.end())
        return results

    @staticmethod
    def _find_end_token(text: str, begin_start: int) -> int:
        depth = 0
        for token in re.finditer(r"\b(begin|end)\b", text[begin_start:]):
            if token.group(1) == "begin":
                depth += 1
            else:
                depth -= 1
                if depth == 0:
                    return begin_start + token.end()
        return len(text)

    @staticmethod
    def _block_kind(keyword: str, sensitivity: str) -> str:
        if keyword == "always_ff" or re.search(r"\b(posedge|negedge)\b", sensitivity):
            return "sequential"
        if keyword == "always_comb" or sensitivity.strip() in {"*", "(*)"}:
            return "combinational"
        if keyword == "always_latch":
            return "latch"
        return "procedural"

    def _parse_continuous_assignments(self, body: str, base_line: int) -> List[Assignment]:
        return [
            Assignment(
                lhs=match.group("lhs").replace(" ", ""),
                rhs=match.group("rhs").strip(),
                operator="=",
                line=line_at(body, match.start(), base_line),
            )
            for match in CONTINUOUS_ASSIGN_RE.finditer(body)
        ]

    def _parse_instances(
        self,
        body: str,
        base_line: int,
        blocks: Sequence[Tuple[ProceduralBlock, int, int]],
    ) -> List[Instance]:
        instances: List[Instance] = []
        pattern = re.compile(
            r"(?ms)^\s*(?P<type>[A-Za-z_][A-Za-z0-9_$]*)\s*"
            r"(?:#\s*\((?P<params>.*?)\)\s*)?"
            r"(?P<name>[A-Za-z_][A-Za-z0-9_$]*)\s*"
            r"\((?P<connections>.*?)\)\s*;"
        )
        for match in pattern.finditer(body):
            if any(start <= match.start() < end for _block, start, end in blocks):
                continue
            module_type = match.group("type")
            if module_type in RESERVED_INSTANCE_WORDS:
                continue
            connection_text = match.group("connections")
            named: Dict[str, str] = {}
            positional: List[str] = []
            for connection in split_top_level(connection_text):
                connection = connection.strip()
                named_match = re.match(
                    r"^\.([A-Za-z_][A-Za-z0-9_$]*)\s*\((.*)\)$", connection, re.DOTALL
                )
                if named_match:
                    named[named_match.group(1)] = named_match.group(2).strip()
                elif connection:
                    positional.append(connection)
            instances.append(
                Instance(
                    module_type=module_type,
                    name=match.group("name"),
                    connections=named,
                    positional_connections=positional,
                    line=line_at(body, match.start(), base_line),
                )
            )
        return instances


def identifiers(text: str) -> Iterable[str]:
    """Yield identifiers present in an RTL expression."""
    return (match.group(0) for match in IDENTIFIER_RE.finditer(text))
