# Organ 28 — Package Manager

**Authority chain:** Constitution → Law Book → Diagrams → Legacy Guide → Policy Manual → Master Blueprint → Organ Specification → PACKAGE_MANAGER.md

## Responsibility
Sole authority for discovery, installation, upgrade, downgrade, removal, rollback,
and integrity of all packages. No other organ may write to `packages/`.

## Sockets
- `PackageSocket` — `PackageCommandRequest` in / `PackageCommandResult` out
- `RepositorySocket` — discovery queries (`RepositoryManager.query`)
- `InstallationSocket` — install/uninstall/rollback execution
- `AuditSocket` — append-only transaction log (`audit.log`)

## Pipelines
`DiscoveryPipeline → ValidationPipeline (checksum+signature) → InstallationPipeline
(stage → sandbox → atomic swap) → RegistrationPipeline → AuditPipeline`
Failure at any stage → `RecoveryPipeline` (atomic rollback of staging/live swap).

## Modules (single file `package_manager.py`)
PackageCore, RepositoryManager, DependencyResolver, IntegrityVerifier,
SandboxRunner, PackageInstaller, PackageUninstaller, RollbackManager,
PackageRegistry (SQLite), AuditManager.

## Public Contract
```python
core = PackageCore(root=Path("./pkgmgr_data"), repository_source={...})
result = core.execute_command(
    PackageCommandRequest(package_id="toolkit", operation=Operation.INSTALL)
)
```

## Failure Recovery
- Checksum/signature mismatch → `IntegrityError`, transaction aborted, no state change.
- Circular/conflicting dependencies → `DependencyError`, no installs performed.
- Interrupted atomic swap → staging dir discarded, `.bak` restored (Law 8: Failure Transparency).
- Reverse-dependency block on removal unless `force_reinstall=True`.

## Compliance
- Universal Law 6 (State Integrity): SQLite registry + atomic file swap.
- Universal Law 7 (Least Privilege): installer only touches `packages/<id>/`.
- Universal Law 8 (Recovery): `RollbackManager` restores prior manifest/version.
- Foundational Law 7 (Append-Only History): `AuditManager` and `history` table never overwritten.
- Hardware target: CPU-only, no GPU allocation (GPU reserved for Brain).

## Not Implemented (deferred — Future Expansion)
P2P repositories, cloud marketplace hubs, AI-assisted resolution, hot-patching —
per §19 of PACKAGE_MANAGER.md, hooks exist via pluggable `repository_source`,
`sig_fn`, and `test_fn` without core rewrites.
