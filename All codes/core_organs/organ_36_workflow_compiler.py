"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 36
Name: Workflow Compiler (Full Production Implementation)

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Workflow Compiler]
        direction TB
        IN[Inputs] --> PROC[Processing]
        PROC --> OUT[Outputs]
    end
    
    COMPONENT -- event/socket --> DOWNSTREAM_A[CONSUMER A]
    COMPONENT -- event/socket --> DOWNSTREAM_B[CONSUMER B]
    
    class COMPONENT component;
```

Inputs: Discovered from runtime
Outputs: Discovered from runtime
Dependencies: socket, hashlib, dataclasses, uuid, pywintypes...
"""
from __future__ import annotations

"""
organ_36_workflow_compiler.py

HOJAIGA AUTOMATION OS - ORGAN 36: WORKFLOW COMPILER
Authority Order (highest to lowest):
1. Constitution of Hojaiga
2. Hojaiga Law Book
3. Upper/Inner Surface Diagrams & Workflows
4. Legacy Code Migration Guide (reference only, not binding)
5. Hojaiga Policy Manual
6. Master Architecture Blueprint
7. Organ Specification
8. Workflow_Compiler.md (organ-authoritative specification)
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import struct
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

try:
    import yaml  # type: ignore
    _HAS_YAML = True
except ImportError:
    yaml = None
    _HAS_YAML = False

try:
    import win32pipe  # type: ignore
    import win32file  # type: ignore
    import pywintypes  # type: ignore
    _HAS_WIN32 = True
except ImportError:
    win32pipe = None
    win32file = None
    pywintypes = None
    _HAS_WIN32 = False

_IS_WINDOWS = os.name == "nt"

ORGAN_ID = "organ_36_workflow_compiler"
ORGAN_VERSION = "1.0.0"
IR_SCHEMA_VERSION = "1.0.0"
MAX_FRAME_BYTES = 16 * 1024 * 1024
FRAME_HEADER = ">IH"
FRAME_HEADER_SIZE = struct.calcsize(FRAME_HEADER)
IPC_SOCKET_NAME = "hojaiga_interface"
NAMED_PIPE_PATH = r"\\.\pipe\hojaiga_interface_organ36"
UNIX_SOCKET_PATH = "/tmp/hojaiga_interface_organ36.sock"
TCP_LOOPBACK_HOST = "127.0.0.1"
TCP_LOOPBACK_PORT = 47536


class OpCode(int, Enum):
    COMPILE = 0x01
    VALIDATE_ONLY = 0x02
    GET_DIAGNOSTICS = 0x03
    CACHE_QUERY = 0x04
    HEALTH = 0x05
    CACHE_INVALIDATE = 0x06
    RESULT = 0xF0
    ERROR = 0xFF


def _make_logger() -> logging.Logger:
    logger = logging.getLogger(ORGAN_ID)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            '{"ts":"%(asctime)s","module":"%(name)s","level":"%(levelname)s","msg":%(message)s}'
        ))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


LOG = _make_logger()


def _jlog(module: str, level: str, message: str, metadata: Any) -> None:
    payload = json.dumps({
        "timestamp": int(time.time()),
        "level": level,
        "module": module,
        "message": message,
        "metadata": metadata,
    })
    level_name = level.lower()
    method_name = "warning" if level_name == "warn" else level_name
    getattr(LOG, method_name, LOG.info)(payload)


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    SUGGESTION = "SUGGESTION"


@dataclass
class DiagnosticEntry:
    code: str
    severity: Severity
    message: str
    line: Optional[int] = None
    column: Optional[int] = None
    node_id: Optional[str] = None
    remediation: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        location = None
        if self.line is not None or self.node_id is not None:
            location = {"line": self.line, "column": self.column, "nodeId": self.node_id}
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "location": location,
            "remediation": self.remediation,
        }


class DiagnosticsEngine:
    def __init__(self, max_entries: int = 5000) -> None:
        self._entries: List[DiagnosticEntry] = []
        self._max_entries = max_entries
        self._truncated = False

    def error(self, code: str, message: str, node_id: Optional[str] = None,
              line: Optional[int] = None, column: Optional[int] = None, remediation: Optional[str] = None) -> None:
        self._add(Severity.ERROR, code, message, node_id, line, column, remediation)

    def warning(self, code: str, message: str, node_id: Optional[str] = None,
                line: Optional[int] = None, column: Optional[int] = None, remediation: Optional[str] = None) -> None:
        self._add(Severity.WARNING, code, message, node_id, line, column, remediation)

    def suggestion(self, code: str, message: str, node_id: Optional[str] = None,
                   line: Optional[int] = None, column: Optional[int] = None, remediation: Optional[str] = None) -> None:
        self._add(Severity.SUGGESTION, code, message, node_id, line, column, remediation)

    def _add(self, severity: Severity, code: str, message: str, node_id, line, column, remediation) -> None:
        if len(self._entries) >= self._max_entries:
            if severity != Severity.ERROR:
                self._truncated = True
                return
        self._entries.append(DiagnosticEntry(code, severity, message, line, column, node_id, remediation))

    def has_errors(self) -> bool:
        return any(e.severity == Severity.ERROR for e in self._entries)

    def get_report(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self._entries]

    def is_truncated(self) -> bool:
        return self._truncated

    def clear(self) -> None:
        self._entries.clear()
        self._truncated = False


@dataclass
class AstNode:
    id: str
    type: str
    children: List["AstNode"] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)
    line: int = 0
    column: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "children": [c.to_dict() for c in self.children],
            "attributes": self.attributes,
            "location": {"line": self.line, "column": self.column},
        }


class WorkflowParseError(Exception):
    def __init__(self, message: str, line: int = 0, column: int = 0):
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column


_VALID_NODE_TYPES = {
    "TASK", "CONDITION", "BRANCH", "LOOP_FOR_EACH", "LOOP_WHILE",
    "LOOP_REPEAT_UNTIL", "PARALLEL", "SEQUENTIAL", "WAIT", "APPROVAL",
    "PLUGIN", "CONNECTOR", "EXTERNAL_API", "HUMAN_INTERACTION", "TRIGGER",
    "ROOT",
}


class WorkflowParser:
    def __init__(self, diagnostics: DiagnosticsEngine) -> None:
        self._diag = diagnostics

    def parse(self, source: Any, source_format: str = "auto") -> AstNode:
        document = self._decode(source, source_format)
        if not isinstance(document, dict):
            raise WorkflowParseError("Root workflow document must be an object/mapping.")
        root = AstNode(id="root", type="ROOT", attributes={
            "name": document.get("name", "unnamed_workflow"),
            "version": document.get("version", "0.0.0"),
            "variables": document.get("variables", []),
            "triggers": document.get("triggers", []),
        })
        steps = document.get("steps", [])
        if not isinstance(steps, list):
            raise WorkflowParseError("'steps' must be a list of step declarations.")
        for index, raw_step in enumerate(steps):
            root.children.append(self._parse_node(raw_step, path=f"steps[{index}]"))
        return root

    def _decode(self, source: Any, source_format: str) -> Dict[str, Any]:
        if isinstance(source, dict):
            return source
        if isinstance(source, (bytes, bytearray)):
            source = source.decode("utf-8", errors="strict")
        if isinstance(source, str):
            fmt = source_format
            if fmt == "auto":
                stripped = source.strip()
                fmt = "json" if stripped.startswith("{") or stripped.startswith("[") else "yaml"
            if fmt == "json":
                try:
                    return json.loads(source)
                except json.JSONDecodeError as exc:
                    raise WorkflowParseError(
                        f"Malformed JSON workflow source: {exc.msg}", exc.lineno, exc.colno
                    ) from exc
            if fmt == "yaml":
                if not _HAS_YAML:
                    raise WorkflowParseError(
                        "YAML source provided but PyYAML is not installed on this host."
                    )
                try:
                    return yaml.safe_load(source)
                except Exception as exc:
                    raise WorkflowParseError(f"Malformed YAML workflow source: {exc}") from exc
            raise WorkflowParseError(f"Unsupported source format '{fmt}'.")
        raise WorkflowParseError("Unsupported workflow source type; expected dict, str, or bytes.")

    def _parse_node(self, raw: Any, path: str) -> AstNode:
        if not isinstance(raw, dict):
            raise WorkflowParseError(f"Step at {path} must be an object.")
        node_id = str(raw.get("id") or f"n_{uuid.uuid4().hex[:12]}")
        node_type = str(raw.get("type", "")).upper()
        line = int(raw.get("_line", 0))
        column = int(raw.get("_column", 0))
        if node_type not in _VALID_NODE_TYPES:
            self._diag.error(
                "ERR_LEXICAL_UNKNOWN_NODE_TYPE",
                f"Unknown step type '{node_type}' at {path}.",
                node_id=node_id, line=line, column=column,
                remediation=f"Use one of: {sorted(_VALID_NODE_TYPES)}",
            )
            node_type = node_type or "TASK"
        attributes = {k: v for k, v in raw.items() if k not in ("children", "type", "id", "_line", "_column")}
        node = AstNode(id=node_id, type=node_type, attributes=attributes, line=line, column=column)
        for index, child_raw in enumerate(raw.get("children", []) or []):
            node.children.append(self._parse_node(child_raw, path=f"{path}.children[{index}]"))
        return node


_REQUIRED_ATTRS_BY_TYPE: Dict[str, Set[str]] = {
    "TASK": {"capability"},
    "CONDITION": {"expression"},
    "LOOP_FOR_EACH": {"collection"},
    "LOOP_WHILE": {"expression"},
    "LOOP_REPEAT_UNTIL": {"expression"},
    "WAIT": set(),
    "APPROVAL": set(),
    "PLUGIN": {"pluginId"},
    "CONNECTOR": {"connectorId"},
    "EXTERNAL_API": {"endpoint", "method"},
    "HUMAN_INTERACTION": {"formId"},
}


class SyntaxValidator:
    def __init__(self, diagnostics: DiagnosticsEngine) -> None:
        self._diag = diagnostics
        self._seen_ids: Set[str] = set()

    def validate(self, root: AstNode) -> bool:
        self._seen_ids.clear()
        before = self._diag.has_errors()
        self._walk(root)
        return not (self._diag.has_errors() and not before)

    def _walk(self, node: AstNode) -> None:
        if node.type != "ROOT":
            if node.id in self._seen_ids:
                self._diag.error(
                    "ERR_SYNTAX_DUPLICATE_NODE_ID",
                    f"Duplicate node identifier '{node.id}'.",
                    node_id=node.id, line=node.line, column=node.column,
                )
            self._seen_ids.add(node.id)
            required = _REQUIRED_ATTRS_BY_TYPE.get(node.type, set())
            missing = required - node.attributes.keys()
            for attr in sorted(missing):
                self._diag.error(
                    "ERR_SYNTAX_MISSING_REQUIRED_FIELD",
                    f"Node '{node.id}' of type {node.type} is missing required field '{attr}'.",
                    node_id=node.id, line=node.line, column=node.column,
                    remediation=f"Add '{attr}' to the node declaration.",
                )
            if node.type in ("PARALLEL", "SEQUENTIAL") and not node.children:
                self._diag.warning(
                    "WARN_SYNTAX_EMPTY_BLOCK",
                    f"{node.type} block '{node.id}' has no children.",
                    node_id=node.id, line=node.line, column=node.column,
                )
        for child in node.children:
            self._walk(child)


@dataclass
class SymbolTableEntry:
    symbol_name: str
    data_type: str
    scope: str
    initial_value: Any = None


EventSchemaLookup = Callable[[str], Optional[Dict[str, Any]]]
_PRIMITIVE_TYPES = {"string", "number", "boolean", "object", "array", "null"}


class SemanticValidator:
    def __init__(self, diagnostics: DiagnosticsEngine,
                 event_catalog_lookup: Optional[EventSchemaLookup] = None) -> None:
        self._diag = diagnostics
        self._event_lookup = event_catalog_lookup
        self.symbol_table: List[SymbolTableEntry] = []

    def validate(self, root: AstNode) -> bool:
        before = self._diag.has_errors()
        declared: Set[str] = set()
        for raw_var in root.attributes.get("variables", []) or []:
            name = raw_var.get("name")
            dtype = raw_var.get("type", "object")
            if not name:
                self._diag.error("ERR_SEMANTIC_UNNAMED_VARIABLE", "Workflow variable declared without a name.")
                continue
            if dtype not in _PRIMITIVE_TYPES:
                self._diag.warning(
                    "WARN_SEMANTIC_UNKNOWN_TYPE",
                    f"Variable '{name}' declared with non-primitive type '{dtype}'.",
                )
            declared.add(name)
            self.symbol_table.append(SymbolTableEntry(name, dtype, "GLOBAL", raw_var.get("default")))
        self._walk(root, declared)
        return not (self._diag.has_errors() and not before)

    def _walk(self, node: AstNode, declared: Set[str]) -> None:
        local_declared = set(declared)
        for ref in self._extract_variable_refs(node.attributes):
            if ref not in local_declared:
                self._diag.error(
                    "ERR_SEMANTIC_UNDECLARED_SYMBOL",
                    f"Node '{node.id}' references undeclared variable '${ref}'.",
                    node_id=node.id, line=node.line, column=node.column,
                    remediation="Declare the variable in the workflow 'variables' section.",
                )
        if node.type == "TASK":
            event_name = node.attributes.get("onEvent")
            if event_name and self._event_lookup is not None:
                schema = self._event_lookup(event_name)
                if schema is None:
                    self._diag.error(
                        "ERR_SEMANTIC_UNKNOWN_EVENT",
                        f"Node '{node.id}' binds to unregistered event '{event_name}'.",
                        node_id=node.id, line=node.line, column=node.column,
                    )
        if node.type == "LOOP_FOR_EACH":
            local_declared.add(node.attributes.get("itemVariable", "item"))
        for child in node.children:
            self._walk(child, local_declared)

    @staticmethod
    def _extract_variable_refs(attributes: Dict[str, Any]) -> Set[str]:
        refs: Set[str] = set()

        def scan(value: Any) -> None:
            if isinstance(value, str):
                start = 0
                while True:
                    idx = value.find("${", start)
                    if idx == -1:
                        break
                    end = value.find("}", idx)
                    if end == -1:
                        break
                    refs.add(value[idx + 2:end].split(".")[0].strip())
                    start = end + 1
            elif isinstance(value, dict):
                for v in value.values():
                    scan(v)
            elif isinstance(value, list):
                for v in value:
                    scan(v)

        for v in attributes.values():
            scan(v)
        return refs


@dataclass
class DependencyGraph:
    adjacency: Dict[str, Set[str]] = field(default_factory=dict)
    nodes: Dict[str, AstNode] = field(default_factory=dict)
    topological_order: List[str] = field(default_factory=list)
    sync_points: Set[str] = field(default_factory=set)


class CircularDependencyError(Exception):
    def __init__(self, cycle_path: List[str]):
        super().__init__(f"Circular dependency detected: {' -> '.join(cycle_path)}")
        self.cycle_path = cycle_path


class DependencyResolver:
    def __init__(self, diagnostics: DiagnosticsEngine) -> None:
        self._diag = diagnostics

    def resolve(self, root: AstNode) -> Optional[DependencyGraph]:
        graph = DependencyGraph()
        self._flatten(root, graph, parent_deps=[])
        cycle = self._find_cycle(graph)
        if cycle:
            self._diag.error(
                "ERR_DEPENDENCY_CIRCULAR",
                f"Circular dependency detected: {' -> '.join(cycle)}",
                remediation="Break the cycle by removing or reordering the 'dependsOn' edge.",
            )
            return None
        graph.topological_order = self._kahn_topological_sort(graph)
        self._insert_sync_points(root, graph)
        return graph

    def _flatten(self, node: AstNode, graph: DependencyGraph, parent_deps: List[str]) -> List[str]:
        if node.type == "ROOT":
            previous = "__start__"
            graph.nodes[previous] = node
            graph.adjacency.setdefault(previous, set())
            for child in node.children:
                explicit = child.attributes.get("dependsOn")
                deps = list(explicit) if explicit else [previous]
                tails = self._flatten_sequence(child, graph, deps)
                previous = tails[-1] if tails else previous
            return [previous]

        graph.nodes[node.id] = node
        graph.adjacency.setdefault(node.id, set())

        if node.type == "PARALLEL":
            branch_tails: List[str] = []
            for child in node.children:
                explicit = child.attributes.get("dependsOn")
                deps = list(explicit) if explicit else [node.id]
                tails = self._flatten_sequence(child, graph, deps)
                branch_tails.extend(tails)
            return branch_tails

        return [node.id]

    def _flatten_sequence(self, node: AstNode, graph: DependencyGraph, deps: List[str]) -> List[str]:
        self._register(node, graph, deps)
        if node.type == "PARALLEL":
            tails: List[str] = []
            for child in node.children:
                explicit = child.attributes.get("dependsOn")
                child_deps = list(explicit) if explicit else [node.id]
                tails.extend(self._flatten_sequence(child, graph, child_deps))
            return tails
        return [node.id]

    def _register(self, node: AstNode, graph: DependencyGraph, deps: List[str]) -> None:
        graph.nodes[node.id] = node
        graph.adjacency.setdefault(node.id, set())
        for dep in deps:
            graph.adjacency.setdefault(dep, set())
            graph.adjacency[dep].add(node.id)
        for child in node.children:
            if node.type != "PARALLEL":
                child_explicit = child.attributes.get("dependsOn")
                child_deps = list(child_explicit) if child_explicit else [node.id]
                self._register(child, graph, child_deps)

    def _find_cycle(self, graph: DependencyGraph) -> Optional[List[str]]:
        index_counter = [0]
        stack: List[str] = []
        lowlink: Dict[str, int] = {}
        index: Dict[str, int] = {}
        on_stack: Dict[str, bool] = {}
        result: List[str] = []

        def strongconnect(v: str) -> None:
            index[v] = index_counter[0]
            lowlink[v] = index_counter[0]
            index_counter[0] += 1
            stack.append(v)
            on_stack[v] = True
            for w in graph.adjacency.get(v, ()):
                if w not in index:
                    strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink[w])
                elif on_stack.get(w):
                    lowlink[v] = min(lowlink[v], index[w])
            if lowlink[v] == index[v]:
                component = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    component.append(w)
                    if w == v:
                        break
                if len(component) > 1:
                    result.extend(component)

        for node_id in list(graph.adjacency.keys()):
            if node_id not in index:
                strongconnect(node_id)
            if result:
                return result
        return None

    @staticmethod
    def _kahn_topological_sort(graph: DependencyGraph) -> List[str]:
        in_degree: Dict[str, int] = {n: 0 for n in graph.adjacency}
        for _src, dests in graph.adjacency.items():
            for d in dests:
                in_degree[d] = in_degree.get(d, 0) + 1
        queue = sorted([n for n, deg in in_degree.items() if deg == 0])
        order: List[str] = []
        while queue:
            queue.sort()
            n = queue.pop(0)
            order.append(n)
            for m in sorted(graph.adjacency.get(n, ())):
                in_degree[m] -= 1
                if in_degree[m] == 0:
                    queue.append(m)
        return order

    @staticmethod
    def _insert_sync_points(root: AstNode, graph: DependencyGraph) -> None:
        def walk(node: AstNode) -> None:
            if node.type == "PARALLEL" and node.children:
                graph.sync_points.add(f"sync_{node.id}")
            for child in node.children:
                walk(child)
        walk(root)


@dataclass
class CapabilityBinding:
    organ: str
    capability: str
    min_version: str
    permission_level: str = "STANDARD"


CapabilityLookup = Callable[[str, str], Optional[Dict[str, Any]]]
ServiceLookup = Callable[[str], Optional[Dict[str, Any]]]


class CapabilityResolver:
    def __init__(self, diagnostics: DiagnosticsEngine,
                 capability_lookup: Optional[CapabilityLookup] = None) -> None:
        self._diag = diagnostics
        self._lookup = capability_lookup or self._default_lookup
        self.resolved: Dict[str, CapabilityBinding] = {}

    @staticmethod
    def _default_lookup(organ: str, capability: str) -> Optional[Dict[str, Any]]:
        return {"available": True, "minVersion": "1.0.0", "permissionLevel": "STANDARD"}

    def resolve(self, graph: DependencyGraph) -> bool:
        before = self._diag.has_errors()
        for node_id, node in graph.nodes.items():
            if node.type != "TASK":
                continue
            capability_ref = str(node.attributes.get("capability", ""))
            
            # Robust normalization: if simple action like NAVIGATE, assume browser/app context
            if "." not in capability_ref:
                capability_ref = f"browser.{capability_ref.lower()}"
                node.attributes["capability"] = capability_ref

            organ, capability = capability_ref.split(".", 1)
            record = self._lookup(organ, capability)
            if record is None or not record.get("available", False):
                self._diag.error(
                    "ERR_CAPABILITY_NOT_FOUND",
                    f"Node '{node_id}' requires unregistered capability '{capability_ref}'.",
                    node_id=node_id,
                    remediation="Verify the capability is registered in the Capability Registry.",
                )
                continue
            self.resolved[node_id] = CapabilityBinding(
                organ=organ, capability=capability,
                min_version=record.get("minVersion", "1.0.0"),
                permission_level=record.get("permissionLevel", "STANDARD"),
            )
        return not (self._diag.has_errors() and not before)


class ServiceResolver:
    def __init__(self, diagnostics: DiagnosticsEngine,
                 service_lookup: Optional[ServiceLookup] = None) -> None:
        self._diag = diagnostics
        self._lookup = service_lookup or self._default_lookup
        self.bound: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _default_lookup(organ: str) -> Optional[Dict[str, Any]]:
        return {"reachable": True, "transport": "hojaiga_interface"}

    def resolve(self, capability_map: Dict[str, CapabilityBinding]) -> bool:
        for node_id, binding in capability_map.items():
            record = self._lookup(binding.organ)
            if record is None or not record.get("reachable", False):
                self.bound[node_id] = {"organ": binding.organ, "transport": "unresolved"}
                continue
            self.bound[node_id] = {"organ": binding.organ, "transport": record.get("transport", "hojaiga_interface")}
        return True


@dataclass
class OptimizedGraph:
    graph: DependencyGraph
    fused_step_mappings: Dict[str, List[str]] = field(default_factory=dict)
    eliminated_nodes: List[str] = field(default_factory=list)
    parallel_extractions: int = 0
    connector_reuse_groups: int = 0


class OptimizationEngine:
    _LEVEL_PASSES = {
        "O0": [],
        "O1": ["dead_code"],
        "O2": ["dead_code", "task_fusion"],
        "O3": ["dead_code", "task_fusion", "parallel_extraction", "connector_reuse"],
    }

    def __init__(self, diagnostics: DiagnosticsEngine) -> None:
        self._diag = diagnostics

    def optimize(self, graph: DependencyGraph, level: str = "O2") -> OptimizedGraph:
        result = OptimizedGraph(graph=graph)
        passes = self._LEVEL_PASSES.get(level, self._LEVEL_PASSES["O2"])
        if "dead_code" in passes:
            self._dead_code_elimination(result)
        if "task_fusion" in passes:
            self._task_fusion(result)
        if "parallel_extraction" in passes:
            self._parallel_extraction(result)
        if "connector_reuse" in passes:
            self._connector_reuse(result)
        return result

    def _dead_code_elimination(self, opt: OptimizedGraph) -> None:
        graph = opt.graph
        for node_id, node in list(graph.nodes.items()):
            if node.type == "CONDITION":
                expr = node.attributes.get("expression", "")
                if expr in ("false", "False", "0"):
                    for child in list(node.children):
                        opt.eliminated_nodes.append(child.id)
                    node.children = []
                    self._diag.suggestion(
                        "SUGG_OPT_DEAD_BRANCH_REMOVED",
                        f"Statically-false condition '{node_id}' branch eliminated.",
                        node_id=node_id,
                    )

    def _task_fusion(self, opt: OptimizedGraph) -> None:
        graph = opt.graph
        order = graph.topological_order
        i = 0
        while i < len(order) - 1:
            current_id, next_id = order[i], order[i + 1]
            current = graph.nodes.get(current_id)
            nxt = graph.nodes.get(next_id)
            if (current is not None and nxt is not None
                    and current.type == "TASK" and nxt.type == "TASK"
                    and graph.adjacency.get(current_id) == {next_id}
                    and self._same_organ(current, nxt)):
                fused_id = f"fused_{current_id}_{next_id}"
                opt.fused_step_mappings[fused_id] = [current_id, next_id]
                self._diag.suggestion(
                    "SUGG_OPT_TASK_FUSED",
                    f"Fused '{current_id}' and '{next_id}' onto a single organ invocation.",
                    node_id=fused_id,
                )
            i += 1

    @staticmethod
    def _same_organ(a: AstNode, b: AstNode) -> bool:
        cap_a = str(a.attributes.get("capability", ""))
        cap_b = str(b.attributes.get("capability", ""))
        organ_a = cap_a.split(".", 1)[0] if "." in cap_a else None
        organ_b = cap_b.split(".", 1)[0] if "." in cap_b else None
        return organ_a is not None and organ_a == organ_b

    def _parallel_extraction(self, opt: OptimizedGraph) -> None:
        graph = opt.graph
        reverse: Dict[str, List[str]] = {}
        for src, dests in graph.adjacency.items():
            for d in dests:
                reverse.setdefault(d, []).append(src)
        independent_groups: Dict[Tuple[str, ...], List[str]] = {}
        for node_id, preds in reverse.items():
            key = tuple(sorted(preds))
            if len(key) == 1:
                independent_groups.setdefault(key, []).append(node_id)
        for key, siblings in independent_groups.items():
            if len(siblings) > 1:
                opt.parallel_extractions += 1

    def _connector_reuse(self, opt: OptimizedGraph) -> None:
        graph = opt.graph
        connectors: Dict[str, int] = {}
        for node in graph.nodes.values():
            if node.type == "CONNECTOR":
                cid = str(node.attributes.get("connectorId", ""))
                connectors[cid] = connectors.get(cid, 0) + 1
        opt.connector_reuse_groups = sum(1 for count in connectors.values() if count > 1)


class GraphNodeType(str, Enum):
    TASK = "TASK"
    CONDITION = "CONDITION"
    PARALLEL_SPLIT = "PARALLEL_SPLIT"
    SYNC_JOIN = "SYNC_JOIN"
    ERROR_HANDLER = "ERROR_HANDLER"
    TERMINAL = "TERMINAL"


class EdgeType(str, Enum):
    SEQUENTIAL = "SEQUENTIAL"
    CONDITIONAL_TRUE = "CONDITIONAL_TRUE"
    CONDITIONAL_FALSE = "CONDITIONAL_FALSE"
    ERROR_RECOVERY = "ERROR_RECOVERY"


@dataclass
class GraphNode:
    node_id: str
    node_type: GraphNodeType
    capability_binding: Optional[CapabilityBinding]
    parameters: Dict[str, Any]
    retry_policy: Dict[str, int]
    timeout_ms: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodeId": self.node_id,
            "nodeType": self.node_type.value,
            "capabilityBinding": (
                {
                    "organ": self.capability_binding.organ,
                    "capability": self.capability_binding.capability,
                    "minVersion": self.capability_binding.min_version,
                }
                if self.capability_binding else
                {"organ": "NONE", "capability": "NONE", "minVersion": "0.0.0"}
            ),
            "parameters": self.parameters,
            "retryPolicy": self.retry_policy,
            "timeoutMs": self.timeout_ms,
        }


@dataclass
class GraphEdge:
    edge_id: str
    from_node: str
    to_node: str
    edge_type: EdgeType

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edgeId": self.edge_id,
            "fromNode": self.from_node,
            "toNode": self.to_node,
            "edgeType": self.edge_type.value,
        }


@dataclass
class ExecutableDAG:
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)


class ExecutionGraphBuilder:
    def __init__(self, diagnostics: DiagnosticsEngine) -> None:
        self._diag = diagnostics

    def build(self, opt: OptimizedGraph, capability_map: Dict[str, CapabilityBinding]) -> ExecutableDAG:
        graph = opt.graph
        dag = ExecutableDAG()

        remap: Dict[str, str] = {}
        for fused_id, members in opt.fused_step_mappings.items():
            for member in members:
                remap[member] = fused_id

        dag.nodes.append(GraphNode(
            node_id="__start__", node_type=GraphNodeType.TASK,
            capability_binding=None, parameters={}, retry_policy={"maxAttempts": 1, "backoffMs": 0},
            timeout_ms=0,
        ))

        emitted_fused: Set[str] = set()
        for node_id, node in graph.nodes.items():
            if node_id == "__start__" or node_id in opt.eliminated_nodes:
                continue
            if node_id in remap:
                fused_id = remap[node_id]
                if fused_id in emitted_fused:
                    continue
                emitted_fused.add(fused_id)
                members = opt.fused_step_mappings[fused_id]
                primary = graph.nodes[members[0]]
                fused_node = self._build_node(fused_id, primary, capability_map)
                fused_node.parameters = dict(fused_node.parameters)
                fused_node.parameters["fusedMembers"] = members
                dag.nodes.append(fused_node)
                continue
            dag.nodes.append(self._build_node(node_id, node, capability_map))

        dag.nodes.append(GraphNode(
            node_id="__terminal__", node_type=GraphNodeType.TERMINAL,
            capability_binding=None, parameters={}, retry_policy={"maxAttempts": 1, "backoffMs": 0},
            timeout_ms=0,
        ))

        edge_counter = 0
        seen_edges: Set[Tuple[str, str]] = set()
        for src, dests in graph.adjacency.items():
            if src in opt.eliminated_nodes:
                continue
            resolved_src = remap.get(src, src)
            for dest in dests:
                if dest in opt.eliminated_nodes:
                    continue
                resolved_dest = remap.get(dest, dest)
                if resolved_src == resolved_dest or (resolved_src, resolved_dest) in seen_edges:
                    continue
                seen_edges.add((resolved_src, resolved_dest))
                edge_type = EdgeType.SEQUENTIAL
                src_node = graph.nodes.get(src)
                if src_node is not None and src_node.type == "CONDITION":
                    edge_type = EdgeType.CONDITIONAL_TRUE if edge_counter % 2 == 0 else EdgeType.CONDITIONAL_FALSE
                dag.edges.append(GraphEdge(f"e_{edge_counter}", resolved_src, resolved_dest, edge_type))
                edge_counter += 1

        sinks = [n.node_id for n in dag.nodes
                 if n.node_id not in ("__start__", "__terminal__")
                 and not any(e.from_node == n.node_id for e in dag.edges)]
        for sink in sinks:
            dag.edges.append(GraphEdge(f"e_{edge_counter}", sink, "__terminal__", EdgeType.SEQUENTIAL))
            edge_counter += 1

        roots = [n.node_id for n in dag.nodes
                 if n.node_id not in ("__start__", "__terminal__")
                 and not any(e.to_node == n.node_id for e in dag.edges)]
        for r in roots:
            dag.edges.append(GraphEdge(f"e_{edge_counter}", "__start__", r, EdgeType.SEQUENTIAL))
            edge_counter += 1

        return dag

    def _build_node(self, node_id: str, node: AstNode,
                     capability_map: Dict[str, CapabilityBinding]) -> GraphNode:
        node_type_map = {
            "TASK": GraphNodeType.TASK,
            "CONDITION": GraphNodeType.CONDITION,
            "PARALLEL": GraphNodeType.PARALLEL_SPLIT,
        }
        graph_node_type = node_type_map.get(node.type, GraphNodeType.TASK)
        retry = node.attributes.get("retry", {})
        return GraphNode(
            node_id=node_id,
            node_type=graph_node_type,
            capability_binding=capability_map.get(node_id),
            parameters={k: v for k, v in node.attributes.items() if k not in ("retry", "dependsOn")},
            retry_policy={
                "maxAttempts": int(retry.get("maxAttempts", 1)),
                "backoffMs": int(retry.get("backoffMs", 0)),
            },
            timeout_ms=int(node.attributes.get("timeoutMs", 30000)),
        )


@dataclass
class WorkflowIrEnvelope:
    ir_version: str
    workflow_metadata: Dict[str, Any]
    symbol_table: List[Dict[str, Any]]
    graph_nodes: List[Dict[str, Any]]
    graph_edges: List[Dict[str, Any]]
    resource_requirements: Dict[str, Any]
    optimization_summary: Dict[str, Any]
    compilation_signature: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "irVersion": self.ir_version,
            "workflowMetadata": self.workflow_metadata,
            "symbolTable": self.symbol_table,
            "graphNodes": self.graph_nodes,
            "graphEdges": self.graph_edges,
            "resourceRequirements": self.resource_requirements,
            "optimizationSummary": self.optimization_summary,
            "compilationSignature": self.compilation_signature,
        }


class IrGenerator:
    def __init__(self, signing_key: bytes) -> None:
        self._signing_key = signing_key

    def generate(self, dag: ExecutableDAG, symbol_table: List[SymbolTableEntry],
                 workflow_name: str, workflow_version: str, source_hash: str,
                 opt: OptimizedGraph) -> WorkflowIrEnvelope:
        metadata = {
            "workflowId": str(uuid.uuid4()),
            "name": workflow_name,
            "version": workflow_version,
            "compiledAt": int(time.time()),
            "sourceHash": source_hash,
        }
        graph_nodes = [n.to_dict() for n in dag.nodes]
        graph_edges = [e.to_dict() for e in dag.edges]
        resource_requirements = {
            "estimatedPeakCpuCores": 2.0,
            "estimatedPeakRamMb": 128,
            "estimatedPeakVramMb": 0,
        }
        optimization_summary = {
            "fusedTaskCount": len(opt.fused_step_mappings),
            "eliminatedNodeCount": len(opt.eliminated_nodes),
            "parallelExtractionCount": opt.parallel_extractions,
            "connectorReuseGroups": opt.connector_reuse_groups,
        }
        symbol_table_payload = [
            {
                "symbolName": s.symbol_name,
                "dataType": s.data_type,
                "scope": s.scope,
                "initialValue": s.initial_value,
            }
            for s in symbol_table
        ]
        payload_for_signature = json.dumps({
            "irVersion": IR_SCHEMA_VERSION,
            "workflowMetadata": metadata,
            "graphNodes": graph_nodes,
            "graphEdges": graph_edges,
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(self._signing_key, payload_for_signature, hashlib.sha256).hexdigest()

        return WorkflowIrEnvelope(
            ir_version=IR_SCHEMA_VERSION,
            workflow_metadata=metadata,
            symbol_table=symbol_table_payload,
            graph_nodes=graph_nodes,
            graph_edges=graph_edges,
            resource_requirements=resource_requirements,
            optimization_summary=optimization_summary,
            compilation_signature=signature,
        )


class CompilationCache:
    def __init__(self, storage_path: str, max_entries: int = 5000, ttl_seconds: int = 86400) -> None:
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(storage_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(storage_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS ir_cache ("
            "cache_key TEXT PRIMARY KEY, ir_json TEXT NOT NULL, created_at INTEGER NOT NULL)"
        )
        self._conn.commit()

    @staticmethod
    def compute_key(source_hash: str, flags: Dict[str, Any]) -> str:
        flag_repr = json.dumps(flags, sort_keys=True)
        return hashlib.sha256(f"{source_hash}:{flag_repr}".encode("utf-8")).hexdigest()

    def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT ir_json, created_at FROM ir_cache WHERE cache_key = ?", (cache_key,)
            )
            row = cur.fetchone()
            if row is None:
                return None
            ir_json, created_at = row
            if time.time() - created_at > self._ttl_seconds:
                self._conn.execute("DELETE FROM ir_cache WHERE cache_key = ?", (cache_key,))
                self._conn.commit()
                return None
            return json.loads(ir_json)

    def set(self, cache_key: str, ir_envelope: Dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO ir_cache (cache_key, ir_json, created_at) VALUES (?, ?, ?)",
                (cache_key, json.dumps(ir_envelope), int(time.time())),
            )
            self._conn.commit()

    def invalidate(self, cache_key: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM ir_cache WHERE cache_key = ?", (cache_key,))
            self._conn.commit()
            return cur.rowcount > 0

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class RecoveryManager:
    def __init__(self, diagnostics: DiagnosticsEngine) -> None:
        self._diag = diagnostics

    def guard(self, phase_name: str, func: Callable[[], Any]) -> Tuple[bool, Any]:
        try:
            return True, func()
        except WorkflowParseError as exc:
            self._diag.error("ERR_LEXICAL_PARSE_FAILURE", exc.message, line=exc.line, column=exc.column)
            return False, None
        except Exception as exc:
            self._diag.error("ERR_COMPILER_FATAL", f"Fatal error during {phase_name}: {exc}")
            return False, None


@dataclass
class CompilerFlags:
    optimization_level: str = "O2"
    strict_validation: bool = True
    force_recompile: bool = False


@dataclass
class CompilerConfig:
    compiler_version: str = ORGAN_VERSION
    default_optimization_level: str = "O2"
    cache_enabled: bool = True
    cache_max_entries: int = 5000
    cache_ttl_seconds: int = 86400
    cache_storage_path: str = os.path.join(os.path.expanduser("~"), ".hojaiga", "cache", "organ36_compiler.sqlite3")
    signing_key: bytes = field(default_factory=lambda: os.environ.get(
        "HOJAIGA_COMPILER_SIGNING_KEY", "hojaiga-default-development-key"
    ).encode("utf-8"))


@dataclass
class CompilationOutput:
    success: bool
    ir: Optional[Dict[str, Any]]
    diagnostics: List[Dict[str, Any]]
    compilation_id: str
    duration_ms: float
    from_cache: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "ir": self.ir,
            "diagnostics": self.diagnostics,
            "compilationId": self.compilation_id,
            "durationMs": self.duration_ms,
            "fromCache": self.from_cache,
        }


class CompilerCore:
    def __init__(self, config: CompilerConfig,
                 capability_lookup: Optional[CapabilityLookup] = None,
                 service_lookup: Optional[ServiceLookup] = None,
                 event_catalog_lookup: Optional[EventSchemaLookup] = None) -> None:
        self._config = config
        self._capability_lookup = capability_lookup
        self._service_lookup = service_lookup
        self._event_catalog_lookup = event_catalog_lookup
        self._cache = CompilationCache(
            config.cache_storage_path, config.cache_max_entries, config.cache_ttl_seconds
        ) if config.cache_enabled else None

    def compile(self, source: Any, flags: Optional[CompilerFlags] = None,
                source_format: str = "auto") -> CompilationOutput:
        start = time.perf_counter()
        compilation_id = str(uuid.uuid4())
        flags = flags or CompilerFlags(optimization_level=self._config.default_optimization_level)
        diagnostics = DiagnosticsEngine()
        recovery = RecoveryManager(diagnostics)

        source_bytes = source if isinstance(source, (bytes, bytearray)) else str(source).encode("utf-8")
        source_hash = hashlib.sha256(source_bytes).hexdigest()

        if self._cache is not None and not flags.force_recompile:
            cache_key = CompilationCache.compute_key(source_hash, {
                "optimizationLevel": flags.optimization_level,
                "strictValidation": flags.strict_validation,
                "irVersion": IR_SCHEMA_VERSION,
            })
            cached = self._cache.get(cache_key)
            if cached is not None:
                duration_ms = (time.perf_counter() - start) * 1000
                return CompilationOutput(True, cached, [], compilation_id, duration_ms, from_cache=True)

        ok, root = recovery.guard("parse", lambda: WorkflowParser(diagnostics).parse(source, source_format))
        if not ok or diagnostics.has_errors():
            return self._fail(compilation_id, diagnostics, start)

        ok, _ = recovery.guard("syntax_validate", lambda: SyntaxValidator(diagnostics).validate(root))
        if not ok or diagnostics.has_errors():
            return self._fail(compilation_id, diagnostics, start)

        semantic_validator = SemanticValidator(diagnostics, self._event_catalog_lookup)
        ok, _ = recovery.guard("semantic_validate", lambda: semantic_validator.validate(root))
        if not ok or (diagnostics.has_errors() and flags.strict_validation):
            return self._fail(compilation_id, diagnostics, start)

        ok, dep_graph = recovery.guard("dependency_resolve", lambda: DependencyResolver(diagnostics).resolve(root))
        if not ok or dep_graph is None or diagnostics.has_errors():
            return self._fail(compilation_id, diagnostics, start)

        cap_resolver = CapabilityResolver(diagnostics, self._capability_lookup)
        ok, _ = recovery.guard("capability_resolve", lambda: cap_resolver.resolve(dep_graph))
        if not ok or diagnostics.has_errors():
            return self._fail(compilation_id, diagnostics, start)

        service_resolver = ServiceResolver(diagnostics, self._service_lookup)
        recovery.guard("service_resolve", lambda: service_resolver.resolve(cap_resolver.resolved))

        ok, opt_graph = recovery.guard(
            "optimize", lambda: OptimizationEngine(diagnostics).optimize(dep_graph, flags.optimization_level)
        )
        if not ok or opt_graph is None:
            return self._fail(compilation_id, diagnostics, start)

        ok, dag = recovery.guard(
            "build_graph",
            lambda: ExecutionGraphBuilder(diagnostics).build(opt_graph, cap_resolver.resolved),
        )
        if not ok or dag is None or diagnostics.has_errors():
            return self._fail(compilation_id, diagnostics, start)

        ir_generator = IrGenerator(self._config.signing_key)
        ok, envelope = recovery.guard(
            "generate_ir",
            lambda: ir_generator.generate(
                dag, semantic_validator.symbol_table,
                root.attributes.get("name", "unnamed_workflow"),
                root.attributes.get("version", "0.0.0"),
                source_hash, opt_graph,
            ),
        )
        if not ok or envelope is None:
            return self._fail(compilation_id, diagnostics, start)

        envelope_dict = envelope.to_dict()

        if self._cache is not None:
            cache_key = CompilationCache.compute_key(source_hash, {
                "optimizationLevel": flags.optimization_level,
                "strictValidation": flags.strict_validation,
                "irVersion": IR_SCHEMA_VERSION,
            })
            self._cache.set(cache_key, envelope_dict)

        duration_ms = (time.perf_counter() - start) * 1000
        return CompilationOutput(True, envelope_dict, diagnostics.get_report(), compilation_id, duration_ms)

    def validate_only(self, source: Any, source_format: str = "auto") -> CompilationOutput:
        start = time.perf_counter()
        compilation_id = str(uuid.uuid4())
        diagnostics = DiagnosticsEngine()
        recovery = RecoveryManager(diagnostics)
        ok, root = recovery.guard("parse", lambda: WorkflowParser(diagnostics).parse(source, source_format))
        if ok and root is not None:
            recovery.guard("syntax_validate", lambda: SyntaxValidator(diagnostics).validate(root))
            recovery.guard(
                "semantic_validate",
                lambda: SemanticValidator(diagnostics, self._event_catalog_lookup).validate(root),
            )
        duration_ms = (time.perf_counter() - start) * 1000
        return CompilationOutput(
            not diagnostics.has_errors(), None, diagnostics.get_report(), compilation_id, duration_ms
        )

    @staticmethod
    def _fail(compilation_id: str, diagnostics: DiagnosticsEngine, start: float) -> CompilationOutput:
        duration_ms = (time.perf_counter() - start) * 1000
        return CompilationOutput(False, None, diagnostics.get_report(), compilation_id, duration_ms)

    def close(self) -> None:
        if self._cache is not None:
            self._cache.close()


class WorkflowCompilerKernel:
    def __init__(self, config: Optional[CompilerConfig] = None,
                 capability_lookup: Optional[CapabilityLookup] = None,
                 service_lookup: Optional[ServiceLookup] = None,
                 event_catalog_lookup: Optional[EventSchemaLookup] = None) -> None:
        self.config = config or CompilerConfig()
        self.core = CompilerCore(self.config, capability_lookup, service_lookup, event_catalog_lookup)
        self.cns = None

    def compile_workflow(self, source: Any, optimization_level: Optional[str] = None,
                          strict_validation: bool = True, force_recompile: bool = False,
                          source_format: str = "auto") -> Dict[str, Any]:
        flags = CompilerFlags(
            optimization_level=optimization_level or self.config.default_optimization_level,
            strict_validation=strict_validation,
            force_recompile=force_recompile,
        )
        return self.core.compile(source, flags, source_format).to_dict()

    def validate_workflow(self, source: Any, source_format: str = "auto") -> Dict[str, Any]:
        return self.core.validate_only(source, source_format).to_dict()

    def invalidate_cache(self, source: Any, optimization_level: Optional[str] = None,
                          strict_validation: bool = True) -> bool:
        if self.core._cache is None:
            return False
        source_bytes = source if isinstance(source, (bytes, bytearray)) else str(source).encode("utf-8")
        source_hash = hashlib.sha256(source_bytes).hexdigest()
        cache_key = CompilationCache.compute_key(source_hash, {
            "optimizationLevel": optimization_level or self.config.default_optimization_level,
            "strictValidation": strict_validation,
            "irVersion": IR_SCHEMA_VERSION,
        })
        return self.core._cache.invalidate(cache_key)

    def health(self) -> Dict[str, Any]:
        return {
            "organId": ORGAN_ID,
            "organVersion": ORGAN_VERSION,
            "irVersion": IR_SCHEMA_VERSION,
            "status": "READY",
            "timestamp": int(time.time()),
        }

    async def start(self, cns):
        self.cns = cns
        await self.cns.subscribe("COMPILATION_STARTED", "compiler_comp", self.handle_cns_event)

    async def handle_cns_event(self, env):
        from core_organs.organ_02_cns_single_file import EventEnvelope
        payload = env.payload
        task_id = payload.get("task_id")
        plan_payload = payload.get("plan_payload") or {}

        loop = asyncio.get_running_loop()

        # Robust translation of agent tasks into normalized capability steps
        steps = []
        for at in plan_payload.get("agent_tasks", []):
            if at.get("wait_seconds"):
                steps.append({
                    "id": f"wait_{uuid.uuid4().hex[:8]}",
                    "type": "WAIT",
                    "duration_seconds": at["wait_seconds"]
                })

            raw_instr = at.get("instructions", "{}")
            action_name = "TASK"
            if isinstance(raw_instr, str) and "action" in raw_instr:
                try:
                    action_name = json.loads(raw_instr).get("action", "TASK")
                except Exception:
                    pass
            elif isinstance(raw_instr, dict):
                action_name = raw_instr.get("action", "TASK")

            # Determine whether task is browser or OS bound
            target_scope = "app" if any(k in str(at.get("objective", "")).lower() for k in ["obs", "desktop", "launch"]) else "browser"
            capability_key = f"{target_scope}.{action_name.lower()}"

            steps.append({
                "id": f"task_{uuid.uuid4().hex[:8]}",
                "type": "TASK",
                "capability": capability_key,
                "agent_id": at.get("agent_id")
            })

        workflow_doc = {
            "name": f"Workflow_{task_id}",
            "version": "1.0.0",
            "steps": steps
        }

        result = await loop.run_in_executor(None, lambda: self.compile_workflow(workflow_doc))

        await self.cns.publish(EventEnvelope(
            topic="COMPILATION_COMPLETED",
            source_organ="organ_36",
            payload={
                "task_id": task_id,
                "compiled_workflow": result,
                "agent_tasks": plan_payload.get("agent_tasks")
            }
        ))

        await self.cns.publish(EventEnvelope(
            topic="sys.events",
            source_organ="organ_36",
            payload={
                "event_type": "COMPILATION_COMPLETED",
                "task_id": task_id
            }
        ))

    def shutdown(self) -> None:
        self.core.close()


class FrameProtocolError(Exception):
    pass


def encode_frame(op_code: int, payload: Dict[str, Any]) -> bytes:
    body = json.dumps(payload).encode("utf-8")
    if len(body) > MAX_FRAME_BYTES:
        raise FrameProtocolError(f"Payload of {len(body)} bytes exceeds max frame size {MAX_FRAME_BYTES}.")
    header = struct.pack(FRAME_HEADER, len(body), op_code)
    return header + body


def decode_frame_header(header_bytes: bytes) -> Tuple[int, int]:
    if len(header_bytes) != FRAME_HEADER_SIZE:
        raise FrameProtocolError("Incomplete frame header.")
    length, op_code = struct.unpack(FRAME_HEADER, header_bytes)
    if length > MAX_FRAME_BYTES:
        raise FrameProtocolError(f"Declared frame length {length} exceeds max frame size {MAX_FRAME_BYTES}.")
    return length, op_code


class IPCServer:
    def __init__(self, kernel: WorkflowCompilerKernel) -> None:
        self._kernel = kernel
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._running = True
        if _IS_WINDOWS and _HAS_WIN32:
            self._thread = threading.Thread(target=self._serve_named_pipe, daemon=True)
        elif not _IS_WINDOWS and hasattr(__import__("socket"), "AF_UNIX"):
            self._thread = threading.Thread(target=self._serve_unix_socket, daemon=True)
        else:
            self._thread = threading.Thread(target=self._serve_tcp_loopback, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _dispatch(self, op_code: int, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        try:
            if op_code == OpCode.COMPILE:
                result = self._kernel.compile_workflow(
                    source=payload.get("source"),
                    optimization_level=payload.get("optimizationLevel"),
                    strict_validation=payload.get("strictValidation", True),
                    force_recompile=payload.get("forceRecompile", False),
                    source_format=payload.get("sourceFormat", "auto"),
                )
                return OpCode.RESULT, result
            if op_code == OpCode.VALIDATE_ONLY:
                result = self._kernel.validate_workflow(
                    source=payload.get("source"), source_format=payload.get("sourceFormat", "auto")
                )
                return OpCode.RESULT, result
            if op_code == OpCode.CACHE_INVALIDATE:
                invalidated = self._kernel.invalidate_cache(
                    source=payload.get("source"),
                    optimization_level=payload.get("optimizationLevel"),
                    strict_validation=payload.get("strictValidation", True),
                )
                return OpCode.RESULT, {"invalidated": invalidated}
            if op_code == OpCode.HEALTH:
                return OpCode.RESULT, self._kernel.health()
            return OpCode.ERROR, {"error": f"Unsupported op_code {op_code}"}
        except Exception as exc:
            return OpCode.ERROR, {"error": str(exc)}

    def _serve_named_pipe(self) -> None:
        while self._running:
            handle = win32pipe.CreateNamedPipe(
                NAMED_PIPE_PATH,
                win32pipe.PIPE_ACCESS_DUPLEX,
                win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
                win32pipe.PIPE_UNLIMITED_INSTANCES, MAX_FRAME_BYTES, MAX_FRAME_BYTES, 0, None,
            )
            try:
                win32pipe.ConnectNamedPipe(handle, None)
                self._serve_named_pipe_connection(handle)
            except pywintypes.error:
                pass
            finally:
                try:
                    win32file.CloseHandle(handle)
                except Exception:
                    pass

    def _serve_named_pipe_connection(self, handle) -> None:
        while self._running:
            _, header_bytes = win32file.ReadFile(handle, FRAME_HEADER_SIZE)
            length, op_code = decode_frame_header(header_bytes if isinstance(header_bytes, bytes) else header_bytes.encode())
            body = b""
            while len(body) < length:
                _, chunk = win32file.ReadFile(handle, length - len(body))
                body += chunk if isinstance(chunk, bytes) else chunk.encode()
            payload = json.loads(body.decode("utf-8")) if body else {}
            reply_op, reply_payload = self._dispatch(op_code, payload)
            win32file.WriteFile(handle, encode_frame(reply_op, reply_payload))

    def _serve_unix_socket(self) -> None:
        import socket
        if os.path.exists(UNIX_SOCKET_PATH):
            os.remove(UNIX_SOCKET_PATH)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(UNIX_SOCKET_PATH)
        server.listen(8)
        server.settimeout(1.0)
        while self._running:
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            threading.Thread(target=self._serve_socket_connection, args=(conn,), daemon=True).start()
        server.close()

    def _serve_tcp_loopback(self) -> None:
        import socket
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((TCP_LOOPBACK_HOST, TCP_LOOPBACK_PORT))
        server.listen(8)
        server.settimeout(1.0)
        while self._running:
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            threading.Thread(target=self._serve_socket_connection, args=(conn,), daemon=True).start()
        server.close()

    def _serve_socket_connection(self, conn) -> None:
        with conn:
            while self._running:
                header_bytes = self._recv_exact(conn, FRAME_HEADER_SIZE)
                if header_bytes is None:
                    return
                try:
                    length, op_code = decode_frame_header(header_bytes)
                except FrameProtocolError as exc:
                    conn.sendall(encode_frame(OpCode.ERROR, {"error": str(exc)}))
                    return
                body = self._recv_exact(conn, length) if length else b""
                if body is None:
                    return
                payload = json.loads(body.decode("utf-8")) if body else {}
                reply_op, reply_payload = self._dispatch(op_code, payload)
                conn.sendall(encode_frame(reply_op, reply_payload))

    @staticmethod
    def _recv_exact(conn, size: int) -> Optional[bytes]:
        if size == 0:
            return b""
        buf = b""
        while len(buf) < size:
            chunk = conn.recv(size - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf


def main() -> None:
    kernel = WorkflowCompilerKernel()
    server = IPCServer(kernel)
    server.start()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop()
        kernel.shutdown()


if __name__ == "__main__":
    main()
