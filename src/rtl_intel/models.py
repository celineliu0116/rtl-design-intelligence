"""Data models shared by the parser, analyzers, and reporters."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class Signal:
    name: str
    kind: str
    direction: Optional[str] = None
    width: Optional[str] = None
    signed: bool = False
    line: int = 1

    def to_dict(self) -> Dict[str, object]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass
class Assignment:
    lhs: str
    rhs: str
    operator: str
    line: int

    @property
    def target(self) -> str:
        """Return the base identifier of an assignment target."""
        return self.lhs.split("[", 1)[0].strip()

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class ProceduralBlock:
    kind: str
    sensitivity: str
    text: str
    line: int
    assignments: List[Assignment] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "kind": self.kind,
            "sensitivity": self.sensitivity,
            "line": self.line,
            "assignments": [assignment.to_dict() for assignment in self.assignments],
        }


@dataclass
class Instance:
    module_type: str
    name: str
    connections: Dict[str, str]
    positional_connections: List[str]
    line: int

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class Module:
    name: str
    path: str
    line: int
    ports: List[Signal] = field(default_factory=list)
    signals: List[Signal] = field(default_factory=list)
    continuous_assignments: List[Assignment] = field(default_factory=list)
    procedural_blocks: List[ProceduralBlock] = field(default_factory=list)
    instances: List[Instance] = field(default_factory=list)

    @property
    def declarations(self) -> List[Signal]:
        return self.ports + self.signals

    def signal_map(self) -> Dict[str, Signal]:
        return {signal.name: signal for signal in self.declarations}

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "source": {"path": self.path, "line": self.line},
            "ports": [port.to_dict() for port in self.ports],
            "signals": [signal.to_dict() for signal in self.signals],
            "continuous_assignments": [item.to_dict() for item in self.continuous_assignments],
            "procedural_blocks": [block.to_dict() for block in self.procedural_blocks],
            "instances": [instance.to_dict() for instance in self.instances],
        }


@dataclass(order=True)
class Issue:
    path: str
    line: int
    rule: str
    severity: str
    message: str
    module: Optional[str] = None
    signal: Optional[str] = None
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass
class AnalysisReport:
    files: List[str]
    modules: List[Module]
    issues: List[Issue]
    hierarchy: Dict[str, object]
    design_summary: str

    def counts(self) -> Dict[str, int]:
        counts = {"errors": 0, "warnings": 0, "info": 0}
        for issue in self.issues:
            key = {"error": "errors", "warning": "warnings"}.get(issue.severity, "info")
            counts[key] += 1
        return counts

    def to_dict(self) -> Dict[str, object]:
        counts = self.counts()
        return {
            "schema_version": "1.0",
            "tool": {"name": "rtl-intel", "version": "0.1.0"},
            "summary": {
                "files_analyzed": len(self.files),
                "modules_found": len(self.modules),
                "issues_found": len(self.issues),
                **counts,
            },
            "files": self.files,
            "modules": [module.to_dict() for module in self.modules],
            "hierarchy": self.hierarchy,
            "issues": [issue.to_dict() for issue in self.issues],
            "design_summary": self.design_summary,
        }
