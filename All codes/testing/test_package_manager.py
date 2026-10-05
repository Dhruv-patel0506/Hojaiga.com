"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Core File
Name: test_package_manager.py

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [test_package_manager.py]
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
Dependencies: pytest, pathlib, json, shutil, sys...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: test_package_manager.py]) --> output([Output Node])
```
"""

import json
import shutil
import sys
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # type: ignore
from core_runtime.package_manager import (
    PackageCore, PackageCommandRequest, Operation, Status, DependencyError,
)


def _make_pkg(build_dir: Path, pkg_id: str, version: str, deps: dict | None = None):
    src = build_dir / f"{pkg_id}-{version}-src"
    src.mkdir(parents=True)
    (src / "main.py").write_text(f"NAME='{pkg_id}'\nVERSION='{version}'\n")
    archive = shutil.make_archive(str(build_dir / f"{pkg_id}-{version}"), "zip", src)
    sha = hashlib.sha256(Path(archive).read_bytes()).hexdigest()
    manifest = {
        "package_id": pkg_id, "version": version,
        "dependencies": deps or {}, "sha256": sha,
        "files": ["main.py"], "signature": None,
    }
    return manifest, Path(archive)


@pytest.fixture
def repo_and_root(tmp_path):
    build = tmp_path / "build"
    build.mkdir()
    m_a, a_a = _make_pkg(build, "libcore", "1.0.0")
    m_b, a_b = _make_pkg(build, "toolkit", "2.1.0", {"libcore": ">=1.0.0"})
    source = {
        "libcore": {"1.0.0": {"manifest": m_a, "archive_path": str(a_a)}},
        "toolkit": {"2.1.0": {"manifest": m_b, "archive_path": str(a_b)}},
    }
    return source, tmp_path / "root"


def test_install_resolves_dependencies(repo_and_root):
    source, root = repo_and_root
    core = PackageCore(root, repository_source=source)
    result = core.execute_command(PackageCommandRequest("toolkit", Operation.INSTALL))
    assert result.status == Status.SUCCESS
    assert result.active_version == "2.1.0"
    assert core.registry.get("libcore") is not None
    assert core.registry.get("toolkit") is not None


def test_remove_blocked_by_dependents(repo_and_root):
    source, root = repo_and_root
    core = PackageCore(root, repository_source=source)
    core.execute_command(PackageCommandRequest("toolkit", Operation.INSTALL))
    result = core.execute_command(PackageCommandRequest("libcore", Operation.REMOVE))
    assert result.status == Status.FAILED
    assert "required by" in result.error_message


def test_uninstall_then_reinstall(repo_and_root):
    source, root = repo_and_root
    core = PackageCore(root, repository_source=source)
    core.execute_command(PackageCommandRequest("toolkit", Operation.INSTALL))
    core.execute_command(PackageCommandRequest("toolkit", Operation.REMOVE))
    r = core.execute_command(PackageCommandRequest("libcore", Operation.REMOVE))
    assert r.status == Status.SUCCESS


def test_checksum_mismatch_rejected(repo_and_root):
    source, root = repo_and_root
    source["libcore"]["1.0.0"]["manifest"]["sha256"] = "0" * 64
    core = PackageCore(root, repository_source=source)
    result = core.execute_command(PackageCommandRequest("libcore", Operation.INSTALL))
    assert result.status == Status.FAILED
    assert "Checksum mismatch" in result.error_message


def test_missing_package_rejected(repo_and_root):
    source, root = repo_and_root
    core = PackageCore(root, repository_source=source)
    result = core.execute_command(PackageCommandRequest("ghost", Operation.INSTALL))
    assert result.status == Status.FAILED


def test_circular_dependency_detected(tmp_path):
    build = tmp_path / "build"
    build.mkdir()
    m_a, a_a = _make_pkg(build, "a", "1.0.0", {"b": ">=1.0.0"})
    m_b, a_b = _make_pkg(build, "b", "1.0.0", {"a": ">=1.0.0"})
    source = {
        "a": {"1.0.0": {"manifest": m_a, "archive_path": str(a_a)}},
        "b": {"1.0.0": {"manifest": m_b, "archive_path": str(a_b)}},
    }
    core = PackageCore(tmp_path / "root", repository_source=source)
    result = core.execute_command(PackageCommandRequest("a", Operation.INSTALL))
    assert result.status == Status.FAILED
    assert "Circular" in result.error_message


def test_rollback_restores_previous_version(tmp_path):
    build = tmp_path / "build"
    build.mkdir()
    m_v1, a_v1 = _make_pkg(build, "app", "1.0.0")
    m_v2, a_v2 = _make_pkg(build, "app", "2.0.0")
    source = {"app": {
        "1.0.0": {"manifest": m_v1, "archive_path": str(a_v1)},
        "2.0.0": {"manifest": m_v2, "archive_path": str(a_v2)},
    }}
    core = PackageCore(tmp_path / "root", repository_source=source)
    core.execute_command(PackageCommandRequest("app", Operation.INSTALL, target_version="1.0.0"))
    core.execute_command(PackageCommandRequest("app", Operation.UPGRADE, target_version="2.0.0"))
    assert core.registry.get("app").version == "2.0.0"  # type: ignore
    result = core.execute_command(PackageCommandRequest("app", Operation.ROLLBACK))
    assert result.status == Status.SUCCESS
    assert result.active_version == "1.0.0"
    assert core.registry.get("app").version == "1.0.0"  # type: ignore


def test_audit_log_append_only(repo_and_root):
    source, root = repo_and_root
    core = PackageCore(root, repository_source=source)
    core.execute_command(PackageCommandRequest("libcore", Operation.INSTALL))
    log_path = root / "audit.log"
    lines_before = log_path.read_text().splitlines()
    core.execute_command(PackageCommandRequest("libcore", Operation.INSTALL, force_reinstall=True))
    lines_after = log_path.read_text().splitlines()
    assert len(lines_after) > len(lines_before)
    assert lines_after[: len(lines_before)] == lines_before
