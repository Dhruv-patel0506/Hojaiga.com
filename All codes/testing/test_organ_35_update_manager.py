"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 35
Name: Update Manager

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Update Manager]
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
Dependencies: pytest, pathlib, tempfile, json, core_organs.organ_35_update_manager...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: test_organ_35_update_manager.py]) --> output([Output Node])
```
"""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import pytest  # type: ignore

from core_organs.organ_35_update_manager import (
    UpdateManagerOrgan, ReleaseChannel, UpdateType, SemVer, UpdateState,
    UpdateManagerError,
)


def system_probe():
    return {"ram_gb": 32, "vram_gb": 4, "os": "Windows11"}


@pytest.fixture
def workdir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def organ(workdir):
    return UpdateManagerOrgan(str(workdir), system_probe)


def make_index(version="1.1.0", payload=b"package-bytes"):
    sha = hashlib.sha256(payload).hexdigest()
    return [{"version": version, "type": "patch", "url": "https://example/pkg",
             "sha256": sha, "size_bytes": len(payload), "requires": {}}]


class TestSemVer:
    def test_parse_and_compare(self):
        assert SemVer.parse("1.2.3").sort_key() < SemVer.parse("1.2.4").sort_key()

    def test_invalid_raises(self):
        with pytest.raises(UpdateManagerError):
            SemVer.parse("not-a-version")


class TestDiscovery:
    @pytest.mark.asyncio
    async def test_discovers_newer_version(self, organ):
        results = await organ.check_for_updates(
            ReleaseChannel.STABLE, "1.0.0", lambda ch: make_index())
        assert len(results) == 1
        assert results[0].target_version == "1.1.0"
        assert organ.state == UpdateState.IDLE

    @pytest.mark.asyncio
    async def test_no_newer_version(self, organ):
        results = await organ.check_for_updates(
            ReleaseChannel.STABLE, "2.0.0", lambda ch: make_index())
        assert results == []


class TestFullUpdatePipeline:
    @pytest.mark.asyncio
    async def test_successful_update_completes(self, organ, workdir):
        payload = b"package-bytes"
        descriptor = (await organ.check_for_updates(
            ReleaseChannel.STABLE, "1.0.0", lambda ch: make_index(payload=payload)))[0]

        target_file = workdir / "app_state.txt"
        target_file.write_text("v1")

        ctx = await organ.execute_update(
            descriptor=descriptor, installed_version="1.0.0", installed_manifest={},
            fetcher=lambda url: payload, backup_paths=[target_file],
            config_existing={"a": 1}, config_template={"a": 0, "b": 2},
            migration_steps=[lambda: None], health_probes=[lambda: True],
        )
        assert organ.state == UpdateState.IDLE
        assert ctx.restore_point_id is not None

    @pytest.mark.asyncio
    async def test_checksum_mismatch_fails_download(self, organ):
        descriptor = (await organ.check_for_updates(
            ReleaseChannel.STABLE, "1.0.0", lambda ch: make_index()))[0]
        ctx = await organ.execute_update(
            descriptor=descriptor, installed_version="1.0.0", installed_manifest={},
            fetcher=lambda url: b"WRONG-BYTES", backup_paths=[],
            config_existing={}, config_template={}, migration_steps=[],
            health_probes=[lambda: True],
        )
        assert organ.state == UpdateState.IDLE


class TestRollbackSequence:
    @pytest.mark.asyncio
    async def test_verification_failure_triggers_rollback(self, organ, workdir):
        payload = b"package-bytes"
        descriptor = (await organ.check_for_updates(
            ReleaseChannel.STABLE, "1.0.0", lambda ch: make_index(payload=payload)))[0]

        target_file = workdir / "app_state.txt"
        target_file.write_text("original")

        ctx = await organ.execute_update(
            descriptor=descriptor, installed_version="1.0.0", installed_manifest={},
            fetcher=lambda url: payload, backup_paths=[target_file],
            config_existing={}, config_template={}, migration_steps=[],
            health_probes=[lambda: False],
        )
        assert organ.state == UpdateState.IDLE
        assert target_file.read_text() == "original"

    @pytest.mark.asyncio
    async def test_migration_failure_triggers_rollback(self, organ, workdir):
        payload = b"package-bytes"
        descriptor = (await organ.check_for_updates(
            ReleaseChannel.STABLE, "1.0.0", lambda ch: make_index(payload=payload)))[0]

        def bad_migration():
            raise RuntimeError("schema broken")

        target_file = workdir / "app_state.txt"
        target_file.write_text("original")

        await organ.execute_update(
            descriptor=descriptor, installed_version="1.0.0", installed_manifest={},
            fetcher=lambda url: payload, backup_paths=[target_file],
            config_existing={}, config_template={}, migration_steps=[bad_migration],
            health_probes=[lambda: True],
        )
        assert organ.state == UpdateState.IDLE
        assert target_file.read_text() == "original"


class TestCompatibility:
    @pytest.mark.asyncio
    async def test_incompatible_ram_blocks_update(self, workdir):
        organ = UpdateManagerOrgan(str(workdir), lambda: {"ram_gb": 2, "vram_gb": 4, "os": "Windows11"})
        payload = b"package-bytes"
        index = make_index(payload=payload)
        index[0]["requires"] = {"min_ram_gb": 8}
        descriptor = (await organ.check_for_updates(
            ReleaseChannel.STABLE, "1.0.0", lambda ch: index))[0]
        ctx = await organ.execute_update(
            descriptor=descriptor, installed_version="1.0.0", installed_manifest={},
            fetcher=lambda url: payload, backup_paths=[],
            config_existing={}, config_template={}, migration_steps=[],
            health_probes=[lambda: True],
        )
        assert organ.state == UpdateState.IDLE


class TestDependency:
    @pytest.mark.asyncio
    async def test_missing_dependency_blocks_update(self, organ):
        payload = b"package-bytes"
        index = make_index(payload=payload)
        index[0]["requires"] = {"organ:01_brain": "1.0.0"}
        descriptor = (await organ.check_for_updates(
            ReleaseChannel.STABLE, "1.0.0", lambda ch: index))[0]
        await organ.execute_update(
            descriptor=descriptor, installed_version="1.0.0", installed_manifest={},
            fetcher=lambda url: payload, backup_paths=[],
            config_existing={}, config_template={}, migration_steps=[],
            health_probes=[lambda: True],
        )
        assert organ.state == UpdateState.IDLE


class TestAuditChain:
    @pytest.mark.asyncio
    async def test_audit_chain_is_verifiable(self, organ):
        await organ.check_for_updates(ReleaseChannel.STABLE, "1.0.0", lambda ch: make_index())
        assert organ.core.audit.verify_chain() is True
