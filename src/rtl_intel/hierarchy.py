"""Module hierarchy construction."""

from __future__ import annotations

from typing import Dict, List, Sequence, Set, Tuple

from .models import Module


def build_hierarchy(modules: Sequence[Module]) -> Tuple[Dict[str, object], List[Tuple[Module, str, str, int]]]:
    """Build a forest of module instances and return unresolved references."""
    module_map = {module.name: module for module in modules}
    instantiated_types = {
        instance.module_type
        for module in modules
        for instance in module.instances
        if instance.module_type in module_map
    }
    root_names = sorted(set(module_map) - instantiated_types)
    if not root_names and module_map:
        # A fully cyclic design has no natural root. Expose every module so the
        # cycle is visible instead of returning an empty hierarchy.
        root_names = sorted(module_map)

    unresolved: List[Tuple[Module, str, str, int]] = []
    for module in modules:
        for instance in module.instances:
            if instance.module_type not in module_map:
                unresolved.append((module, instance.name, instance.module_type, instance.line))

    def node(module_name: str, instance_name: str, active: Set[str]) -> Dict[str, object]:
        if module_name in active:
            return {
                "instance": instance_name,
                "module": module_name,
                "cycle": True,
                "children": [],
            }
        module = module_map[module_name]
        next_active = active | {module_name}
        children: List[Dict[str, object]] = []
        for instance in module.instances:
            if instance.module_type in module_map:
                children.append(node(instance.module_type, instance.name, next_active))
            else:
                children.append(
                    {
                        "instance": instance.name,
                        "module": instance.module_type,
                        "unresolved": True,
                        "children": [],
                    }
                )
        return {
            "instance": instance_name,
            "module": module_name,
            "children": children,
        }

    roots = [node(name, name, set()) for name in root_names]
    hierarchy = {
        "roots": roots,
        "root_modules": root_names,
        "unresolved_instances": [
            {
                "parent_module": parent.name,
                "instance": instance_name,
                "module_type": module_type,
                "path": parent.path,
                "line": line,
            }
            for parent, instance_name, module_type, line in unresolved
        ],
    }
    return hierarchy, unresolved

