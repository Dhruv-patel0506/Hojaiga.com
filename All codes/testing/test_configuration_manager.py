"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Core File
Name: test_configuration_manager.py

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [test_configuration_manager.py]
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
Dependencies: unittest, pathlib, tempfile, shutil, core_organs.organ_20_configuration_manager...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: test_configuration_manager.py]) --> output([Output Node])
```
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from core_organs.organ_20_configuration_manager import (
    ConfigError, ConfigRequest, ConfigStatus, ConfigurationManager,
)


class ConfigurationManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.mgr = ConfigurationManager(base_dir=self.tmp)
        self.mgr.register_schema("core", {
            "required": ["mode"],
            "properties": {
                "mode": {"type": "string", "enum": ["cpu", "gpu"]},
                "threads": {"type": "integer", "minimum": 1, "maximum": 32},
            },
        })
        self.mgr.register_defaults("core", {"threads": 4})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_set_then_get(self):
        req = ConfigRequest(component_id="brain", category="core")
        status = self.mgr.set_configuration(req, {"mode": "cpu", "threads": 8})
        self.assertEqual(status, ConfigStatus.SUCCESS)
        result = self.mgr.get_configuration(req)
        self.assertEqual(result["mode"], "cpu")
        self.assertEqual(result["threads"], 8)

    def test_invalid_schema_rejected(self):
        req = ConfigRequest(component_id="brain", category="core")
        status = self.mgr.set_configuration(req, {"mode": "invalid"})
        self.assertEqual(status, ConfigStatus.INVALID_SCHEMA)

    def test_not_found_raises(self):
        req = ConfigRequest(component_id="ghost", category="core")
        with self.assertRaises(ConfigError):
            self.mgr.get_configuration(req)

    def test_cache_hit(self):
        req = ConfigRequest(component_id="brain", category="core")
        self.mgr.set_configuration(req, {"mode": "cpu"})
        first = self.mgr.get_configuration(req)
        second = self.mgr.get_configuration(req)
        self.assertEqual(first, second)

    def test_rollback(self):
        req = ConfigRequest(component_id="brain", category="core")
        self.mgr.set_configuration(req, {"mode": "cpu"})
        self.mgr.set_configuration(req, {"mode": "gpu"})
        record = self.mgr.rollback_configuration("brain")
        self.assertIsNotNone(record)
        self.assertEqual(record.payload["mode"], "cpu")

    def test_backup_and_restore(self):
        req = ConfigRequest(component_id="brain", category="core")
        self.mgr.set_configuration(req, {"mode": "cpu"})
        path = self.mgr.create_backup("brain")
        self.mgr.set_configuration(req, {"mode": "gpu"})
        self.mgr.restore_backup("brain", path)
        result = self.mgr.get_configuration(req)
        self.assertEqual(result["mode"], "cpu")

    def test_secrets_resolution(self):
        req = ConfigRequest(component_id="db", category="misc")
        self.mgr.set_configuration(req, {"password": "secret://vault/db_pw"})
        result = self.mgr.get_configuration(req)
        self.assertTrue(result["password"]["__secret_ref__"])

    def test_socket_get_set(self):
        self.mgr.socket.request("SET", {
            "component_id": "brain", "category": "core", "payload": {"mode": "cpu"},
        })
        resp = self.mgr.socket.request("GET", {"component_id": "brain", "category": "core"})
        self.assertEqual(resp["status"], "SUCCESS")

    def test_live_reload_subscriber(self):
        received = {}

        def on_reload(component_id, payload):
            received["mode"] = payload["mode"]
            return True

        self.mgr.subscribe("brain", on_reload)
        req = ConfigRequest(component_id="brain", category="core")
        self.mgr.set_configuration(req, {"mode": "gpu"})
        self.assertEqual(received["mode"], "gpu")


if __name__ == "__main__":
    unittest.main()
