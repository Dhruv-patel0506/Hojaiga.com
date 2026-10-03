"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 7
Name: Security

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Security]
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
Dependencies: core_organs.organ_07_security, pathlib, unittest, tempfile...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: test_organ_07_security.py]) --> output([Output Node])
```
"""

"""tests/test_organ_07_security.py — minimal unit coverage for the kernel."""

import tempfile
import unittest
from pathlib import Path

from core_organs.organ_07_security import (
    SecurityKernel, SocketAuthRequest, PipelineValidationPayload,
    CapabilityTokenRequest, FilePathPayload, Capability,
)


class SecurityKernelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.kernel = SecurityKernel(
            base_dir=self.base,
            capability_matrix={"organ_06_automation": ["SOCKET_CONNECT", "PLUGIN_LOAD"]},
            protected_paths=[str(self.base / "Constitution.md")],
        )
        self.kernel.unlock("test-master-key")

    def tearDown(self):
        self.tmp.cleanup()

    def test_locked_state_denies_everything(self):
        kernel = SecurityKernel(base_dir=self.base)
        verdict = kernel.authorize_socket_connection(
            SocketAuthRequest("r1", "organ_06_automation", "organ_02_cns", "test")
        )
        self.assertFalse(verdict.authorized)

    def test_authorized_socket_connection(self):
        verdict = self.kernel.authorize_socket_connection(
            SocketAuthRequest("r2", "organ_06_automation", "organ_02_cns", "dispatch")
        )
        self.assertTrue(verdict.authorized)

    def test_unauthorized_capability_denied(self):
        verdict = self.kernel.authorize_socket_connection(
            SocketAuthRequest("r3", "organ_08_execution", "organ_02_cns", "dispatch")
        )
        self.assertFalse(verdict.authorized)

    def test_protected_file_write_blocked(self):
        (self.base / "Constitution.md").write_text("test")
        verdict = self.kernel.check_file_write_permission(
            FilePathPayload(str(self.base / "Constitution.md"), "organ_06_automation")
        )
        self.assertFalse(verdict.permitted)

    def test_pipeline_validation_blocks_dangerous_payload(self):
        verdict = self.kernel.validate_pipeline_data(
            PipelineValidationPayload("p1", "stage1", {"cmd": "eval('1')"}, "organ_06_automation")
        )
        self.assertFalse(verdict.valid)

    def test_token_issuance_masks_to_matrix(self):
        token = self.kernel.get_execution_token(
            CapabilityTokenRequest("organ_06_automation", ["SOCKET_CONNECT", "GOVERNANCE_WRITE"])
        )
        self.assertEqual(token.capabilities_mask & int(Capability.GOVERNANCE_WRITE), 0)

    def test_lockdown_after_repeated_violations(self):
        for i in range(3):
            self.kernel.authorize_socket_connection(
                SocketAuthRequest(f"r{i}", "organ_08_execution", "organ_02_cns", "dispatch")
            )
        self.assertEqual(self.kernel.state.value, "LOCKDOWN")

    def test_audit_chain_integrity(self):
        self.assertTrue(self.kernel.audit.verify_chain())


if __name__ == "__main__":
    unittest.main()
