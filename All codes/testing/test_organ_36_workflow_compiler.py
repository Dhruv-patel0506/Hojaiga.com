"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 36
Name: Workflow Compiler

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
Dependencies: unittest, tempfile, time, os, core_organs.organ_36_workflow_compiler...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: test_organ_36_workflow_compiler.py]) --> output([Output Node])
```
"""

"""
test_organ_36_workflow_compiler.py

Test suite for Organ 36 -- Workflow Compiler.
Run: python3 -m unittest test_organ_36_workflow_compiler -v
"""

import os
import tempfile
import unittest

import core_organs.organ_36_workflow_compiler as compiler


def make_kernel() -> compiler.WorkflowCompilerKernel:
    tmp_dir = tempfile.mkdtemp(prefix="organ36_test_")
    cfg = compiler.CompilerConfig(cache_storage_path=os.path.join(tmp_dir, "cache.sqlite3"))
    return compiler.WorkflowCompilerKernel(config=cfg)


SIMPLE_WORKFLOW = {
    "name": "simple",
    "version": "1.0.0",
    "variables": [{"name": "x", "type": "string", "default": "v"}],
    "steps": [
        {"id": "t1", "type": "TASK", "capability": "MEMORY.READ_VECTOR", "parameters": {"key": "${x}"}},
    ],
}


class TestWorkflowParser(unittest.TestCase):
    def test_parses_json_string(self) -> None:
        diag = compiler.DiagnosticsEngine()
        root = compiler.WorkflowParser(diag).parse('{"name": "w", "steps": []}')
        self.assertEqual(root.type, "ROOT")
        self.assertEqual(root.attributes["name"], "w")

    def test_parses_dict_directly(self) -> None:
        diag = compiler.DiagnosticsEngine()
        root = compiler.WorkflowParser(diag).parse(SIMPLE_WORKFLOW)
        self.assertEqual(len(root.children), 1)
        self.assertEqual(root.children[0].type, "TASK")

    def test_rejects_malformed_json(self) -> None:
        diag = compiler.DiagnosticsEngine()
        with self.assertRaises(compiler.WorkflowParseError):
            compiler.WorkflowParser(diag).parse("{not valid json")

    def test_unknown_node_type_flagged(self) -> None:
        diag = compiler.DiagnosticsEngine()
        compiler.WorkflowParser(diag).parse({
            "name": "w", "steps": [{"id": "a", "type": "NOT_A_TYPE"}]
        })
        codes = [d.code for d in diag._entries]  # noqa: SLF001
        self.assertIn("ERR_LEXICAL_UNKNOWN_NODE_TYPE", codes)


class TestSyntaxValidator(unittest.TestCase):
    def test_missing_required_field(self) -> None:
        diag = compiler.DiagnosticsEngine()
        root = compiler.WorkflowParser(diag).parse({"name": "w", "steps": [{"id": "a", "type": "TASK"}]})
        compiler.SyntaxValidator(diag).validate(root)
        self.assertTrue(diag.has_errors())

    def test_duplicate_node_id(self) -> None:
        diag = compiler.DiagnosticsEngine()
        root = compiler.WorkflowParser(diag).parse({
            "name": "w",
            "steps": [
                {"id": "dup", "type": "TASK", "capability": "A.B"},
                {"id": "dup", "type": "TASK", "capability": "A.B"},
            ],
        })
        compiler.SyntaxValidator(diag).validate(root)
        codes = [d.code for d in diag._entries]  # noqa: SLF001
        self.assertIn("ERR_SYNTAX_DUPLICATE_NODE_ID", codes)

    def test_valid_workflow_passes(self) -> None:
        diag = compiler.DiagnosticsEngine()
        root = compiler.WorkflowParser(diag).parse(SIMPLE_WORKFLOW)
        ok = compiler.SyntaxValidator(diag).validate(root)
        self.assertTrue(ok)
        self.assertFalse(diag.has_errors())


class TestSemanticValidator(unittest.TestCase):
    def test_undeclared_variable_flagged(self) -> None:
        diag = compiler.DiagnosticsEngine()
        root = compiler.WorkflowParser(diag).parse({
            "name": "w",
            "steps": [{"id": "a", "type": "TASK", "capability": "A.B", "parameters": {"k": "${missing}"}}],
        })
        compiler.SemanticValidator(diag).validate(root)
        codes = [d.code for d in diag._entries]  # noqa: SLF001
        self.assertIn("ERR_SEMANTIC_UNDECLARED_SYMBOL", codes)

    def test_declared_variable_passes(self) -> None:
        diag = compiler.DiagnosticsEngine()
        root = compiler.WorkflowParser(diag).parse(SIMPLE_WORKFLOW)
        ok = compiler.SemanticValidator(diag).validate(root)
        self.assertTrue(ok)

    def test_loop_for_each_binds_item_variable(self) -> None:
        diag = compiler.DiagnosticsEngine()
        root = compiler.WorkflowParser(diag).parse({
            "name": "w",
            "steps": [{
                "id": "loop1", "type": "LOOP_FOR_EACH", "collection": "items", "itemVariable": "it",
                "children": [{"id": "inner", "type": "TASK", "capability": "A.B", "parameters": {"k": "${it}"}}],
            }],
        })
        ok = compiler.SemanticValidator(diag).validate(root)
        self.assertTrue(ok)


class TestDependencyResolver(unittest.TestCase):
    def test_topological_order_respects_deps(self) -> None:
        diag = compiler.DiagnosticsEngine()
        root = compiler.WorkflowParser(diag).parse({
            "name": "w",
            "steps": [
                {"id": "a", "type": "TASK", "capability": "X.Y"},
                {"id": "b", "type": "TASK", "capability": "X.Y", "dependsOn": ["a"]},
                {"id": "c", "type": "TASK", "capability": "X.Y", "dependsOn": ["b"]},
            ],
        })
        graph = compiler.DependencyResolver(diag).resolve(root)
        self.assertIsNotNone(graph)
        order = graph.topological_order  # type: ignore
        self.assertLess(order.index("a"), order.index("b"))
        self.assertLess(order.index("b"), order.index("c"))

    def test_cycle_detected(self) -> None:
        diag = compiler.DiagnosticsEngine()
        root = compiler.WorkflowParser(diag).parse({
            "name": "w",
            "steps": [
                {"id": "a", "type": "TASK", "capability": "X.Y", "dependsOn": ["b"]},
                {"id": "b", "type": "TASK", "capability": "X.Y", "dependsOn": ["a"]},
            ],
        })
        graph = compiler.DependencyResolver(diag).resolve(root)
        self.assertIsNone(graph)
        codes = [d.code for d in diag._entries]  # noqa: SLF001
        self.assertIn("ERR_DEPENDENCY_CIRCULAR", codes)

    def test_parallel_sync_point_registered(self) -> None:
        diag = compiler.DiagnosticsEngine()
        root = compiler.WorkflowParser(diag).parse({
            "name": "w",
            "steps": [{"id": "p1", "type": "PARALLEL", "children": [
                {"id": "a", "type": "TASK", "capability": "X.Y"},
                {"id": "b", "type": "TASK", "capability": "X.Y"},
            ]}],
        })
        graph = compiler.DependencyResolver(diag).resolve(root)
        self.assertIn("sync_p1", graph.sync_points)  # type: ignore


class TestCapabilityAndServiceResolvers(unittest.TestCase):
    def test_unregistered_capability_fails(self) -> None:
        diag = compiler.DiagnosticsEngine()
        root = compiler.WorkflowParser(diag).parse({
            "name": "w", "steps": [{"id": "a", "type": "TASK", "capability": "GHOST.ORGAN_CAP"}]
        })
        graph = compiler.DependencyResolver(diag).resolve(root)
        resolver = compiler.CapabilityResolver(diag, capability_lookup=lambda o, c: None)
        ok = resolver.resolve(graph)
        self.assertFalse(ok)

    def test_registered_capability_resolves(self) -> None:
        diag = compiler.DiagnosticsEngine()
        root = compiler.WorkflowParser(diag).parse(SIMPLE_WORKFLOW)
        graph = compiler.DependencyResolver(diag).resolve(root)
        resolver = compiler.CapabilityResolver(diag)
        ok = resolver.resolve(graph)
        self.assertTrue(ok)
        self.assertIn("t1", resolver.resolved)

    def test_malformed_capability_reference(self) -> None:
        diag = compiler.DiagnosticsEngine()
        root = compiler.WorkflowParser(diag).parse({
            "name": "w", "steps": [{"id": "a", "type": "TASK", "capability": "NoDotHere"}]
        })
        graph = compiler.DependencyResolver(diag).resolve(root)
        resolver = compiler.CapabilityResolver(diag)
        resolver.resolve(graph)
        codes = [d.code for d in diag._entries]  # noqa: SLF001
        self.assertIn("ERR_CAPABILITY_MALFORMED_REF", codes)


class TestOptimizationEngine(unittest.TestCase):
    def test_o0_applies_no_passes(self) -> None:
        diag = compiler.DiagnosticsEngine()
        root = compiler.WorkflowParser(diag).parse({
            "name": "w",
            "steps": [
                {"id": "a", "type": "TASK", "capability": "MEM.READ"},
                {"id": "b", "type": "TASK", "capability": "MEM.READ", "dependsOn": ["a"]},
            ],
        })
        graph = compiler.DependencyResolver(diag).resolve(root)
        opt = compiler.OptimizationEngine(diag).optimize(graph, level="O0")
        self.assertEqual(len(opt.fused_step_mappings), 0)

    def test_o2_fuses_same_organ_chain(self) -> None:
        diag = compiler.DiagnosticsEngine()
        root = compiler.WorkflowParser(diag).parse({
            "name": "w",
            "steps": [
                {"id": "a", "type": "TASK", "capability": "MEM.READ"},
                {"id": "b", "type": "TASK", "capability": "MEM.READ", "dependsOn": ["a"]},
            ],
        })
        graph = compiler.DependencyResolver(diag).resolve(root)
        opt = compiler.OptimizationEngine(diag).optimize(graph, level="O2")
        self.assertEqual(len(opt.fused_step_mappings), 1)


class TestExecutionGraphBuilder(unittest.TestCase):
    def test_builds_start_and_terminal(self) -> None:
        diag = compiler.DiagnosticsEngine()
        root = compiler.WorkflowParser(diag).parse(SIMPLE_WORKFLOW)
        graph = compiler.DependencyResolver(diag).resolve(root)
        cap = compiler.CapabilityResolver(diag)
        cap.resolve(graph)
        opt = compiler.OptimizationEngine(diag).optimize(graph, level="O0")
        dag = compiler.ExecutionGraphBuilder(diag).build(opt, cap.resolved)
        ids = [n.node_id for n in dag.nodes]
        self.assertIn("__start__", ids)
        self.assertIn("__terminal__", ids)
        self.assertIn("t1", ids)

    def test_no_orphan_edges(self) -> None:
        diag = compiler.DiagnosticsEngine()
        root = compiler.WorkflowParser(diag).parse({
            "name": "w",
            "steps": [
                {"id": "t1", "type": "TASK", "capability": "MEM.READ"},
                {"id": "t2", "type": "TASK", "capability": "MEM.WRITE", "dependsOn": ["t1"]},
                {"id": "p1", "type": "PARALLEL", "dependsOn": ["t2"], "children": [
                    {"id": "t3", "type": "TASK", "capability": "CDP.CLICK"},
                    {"id": "t4", "type": "TASK", "capability": "CDP.SCREENSHOT"},
                ]},
            ],
        })
        graph = compiler.DependencyResolver(diag).resolve(root)
        cap = compiler.CapabilityResolver(diag)
        cap.resolve(graph)
        opt = compiler.OptimizationEngine(diag).optimize(graph, level="O3")
        dag = compiler.ExecutionGraphBuilder(diag).build(opt, cap.resolved)
        node_ids = {n.node_id for n in dag.nodes}
        for edge in dag.edges:
            self.assertIn(edge.from_node, node_ids)
            self.assertIn(edge.to_node, node_ids)
        self.assertFalse(diag.has_errors())


class TestIrGenerator(unittest.TestCase):
    def test_signature_round_trips(self) -> None:
        diag = compiler.DiagnosticsEngine()
        root = compiler.WorkflowParser(diag).parse(SIMPLE_WORKFLOW)
        graph = compiler.DependencyResolver(diag).resolve(root)
        cap = compiler.CapabilityResolver(diag)
        cap.resolve(graph)
        opt = compiler.OptimizationEngine(diag).optimize(graph, level="O0")
        dag = compiler.ExecutionGraphBuilder(diag).build(opt, cap.resolved)
        sem = compiler.SemanticValidator(diag)
        sem.validate(root)
        key = b"unit-test-signing-key"
        envelope = compiler.IrGenerator(key).generate(dag, sem.symbol_table, "w", "1.0.0", "hash123", opt)
        envelope_dict = envelope.to_dict()
        self.assertTrue(compiler.IrGenerator.verify_signature(envelope_dict, key))
        tampered = dict(envelope_dict)
        tampered["graphNodes"] = []
        self.assertFalse(compiler.IrGenerator.verify_signature(tampered, key))


class TestCompilationCache(unittest.TestCase):
    def test_set_get_roundtrip(self) -> None:
        tmp_dir = tempfile.mkdtemp(prefix="organ36_cache_test_")
        cache = compiler.CompilationCache(os.path.join(tmp_dir, "c.sqlite3"))
        key = compiler.CompilationCache.compute_key("hash", {"optimizationLevel": "O2"})
        self.assertIsNone(cache.get(key))
        cache.set(key, {"irVersion": "1.0.0"})
        self.assertEqual(cache.get(key)["irVersion"], "1.0.0")  # type: ignore
        self.assertTrue(cache.invalidate(key))
        self.assertIsNone(cache.get(key))
        cache.close()

    def test_ttl_expiry(self) -> None:
        tmp_dir = tempfile.mkdtemp(prefix="organ36_cache_ttl_")
        cache = compiler.CompilationCache(os.path.join(tmp_dir, "c.sqlite3"), ttl_seconds=0)
        key = compiler.CompilationCache.compute_key("hash", {})
        cache.set(key, {"irVersion": "1.0.0"})
        import time
        time.sleep(0.01)
        self.assertIsNone(cache.get(key))
        cache.close()


class TestCompilerCoreEndToEnd(unittest.TestCase):
    def setUp(self) -> None:
        self.kernel = make_kernel()

    def tearDown(self) -> None:
        self.kernel.shutdown()

    def test_full_compile_success(self) -> None:
        out = self.kernel.compile_workflow(SIMPLE_WORKFLOW)
        self.assertTrue(out["success"])
        self.assertIsNotNone(out["ir"])
        self.assertEqual(out["ir"]["irVersion"], compiler.IR_SCHEMA_VERSION)

    def test_cache_hit_on_second_compile(self) -> None:
        self.kernel.compile_workflow(SIMPLE_WORKFLOW)
        second = self.kernel.compile_workflow(SIMPLE_WORKFLOW)
        self.assertTrue(second["fromCache"])

    def test_force_recompile_bypasses_cache(self) -> None:
        self.kernel.compile_workflow(SIMPLE_WORKFLOW)
        second = self.kernel.compile_workflow(SIMPLE_WORKFLOW, force_recompile=True)
        self.assertFalse(second["fromCache"])

    def test_validate_only_reports_errors_without_ir(self) -> None:
        out = self.kernel.validate_workflow({"name": "w", "steps": [{"id": "a", "type": "TASK"}]})
        self.assertFalse(out["success"])
        self.assertIsNone(out["ir"])

    def test_depth_limit_enforced(self) -> None:
        cfg = compiler.CompilerConfig(
            cache_storage_path=self.kernel.config.cache_storage_path.replace("cache.sqlite3", "cache2.sqlite3"),
            max_workflow_depth=2,
        )
        deep_kernel = compiler.WorkflowCompilerKernel(config=cfg)
        nested = {"id": "l3", "type": "TASK", "capability": "A.B"}
        wf = {"name": "deep", "steps": [{"id": "l1", "type": "SEQUENTIAL", "children": [
            {"id": "l2", "type": "SEQUENTIAL", "children": [nested]}
        ]}]}
        out = deep_kernel.compile_workflow(wf)
        self.assertFalse(out["success"])
        codes = [d["code"] for d in out["diagnostics"]]
        self.assertIn("ERR_VALIDATION_DEPTH_EXCEEDED", codes)
        deep_kernel.shutdown()

    def test_health_reports_ready(self) -> None:
        health = self.kernel.health()
        self.assertEqual(health["status"], "READY")
        self.assertEqual(health["organId"], compiler.ORGAN_ID)


class TestFrameProtocol(unittest.TestCase):
    def test_encode_decode_round_trip(self) -> None:
        frame = compiler.encode_frame(compiler.OpCode.HEALTH, {"ping": True})
        header = frame[:compiler.FRAME_HEADER_SIZE]
        length, op_code = compiler.decode_frame_header(header)
        self.assertEqual(op_code, compiler.OpCode.HEALTH)
        body = frame[compiler.FRAME_HEADER_SIZE:compiler.FRAME_HEADER_SIZE + length]
        self.assertEqual(body, b'{"ping": true}')

    def test_oversized_payload_rejected(self) -> None:
        huge = {"data": "x" * (compiler.MAX_FRAME_BYTES + 10)}
        with self.assertRaises(compiler.FrameProtocolError):
            compiler.encode_frame(compiler.OpCode.COMPILE, huge)


class TestIPCDispatch(unittest.TestCase):
    def setUp(self) -> None:
        self.kernel = make_kernel()
        self.server = compiler.IPCServer(self.kernel)

    def tearDown(self) -> None:
        self.kernel.shutdown()

    def test_dispatch_compile(self) -> None:
        op, payload = self.server._dispatch(compiler.OpCode.COMPILE, {"source": SIMPLE_WORKFLOW})  # noqa: SLF001
        self.assertEqual(op, compiler.OpCode.RESULT)
        self.assertTrue(payload["success"])

    def test_dispatch_health(self) -> None:
        op, payload = self.server._dispatch(compiler.OpCode.HEALTH, {})  # noqa: SLF001
        self.assertEqual(op, compiler.OpCode.RESULT)
        self.assertEqual(payload["status"], "READY")

    def test_dispatch_unknown_opcode(self) -> None:
        op, payload = self.server._dispatch(0x99, {})  # noqa: SLF001
        self.assertEqual(op, compiler.OpCode.ERROR)


if __name__ == "__main__":
    unittest.main()
