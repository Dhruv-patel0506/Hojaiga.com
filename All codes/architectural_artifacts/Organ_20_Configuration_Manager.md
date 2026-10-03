# Organ 20 — Configuration Manager

**Version:** 1.0
**Authority:** Master Architecture Blueprint → Organ Specification
**Status:** Implemented

---

## Metadata

| Field | Value |
|---|---|
| Organ ID | 20 |
| Name | Configuration Manager |
| Layer | Core Service Layer |
| Language | Python 3.11+ |
| Source | `configuration_manager.py` |
| Tests | `test_configuration_manager.py` (9/9 passing) |

---

## Purpose

Single source of truth for configuration across Hojaiga. All organs, runtimes, connectors, and shared services retrieve configuration exclusively through this organ. Direct file access by other organs is prohibited.

---

## Responsibilities

- Load, validate, cache, and serve configuration payloads.
- Enforce JSON-Schema-style rules (required fields, types, ranges, enums, dependencies, deprecations).
- Apply environment variable overrides (`HOJAIGA_<COMPONENT>_<KEY>`).
- Resolve `secret://` references to vault-proxy handles (never plaintext).
- Track semantic versions and revision history per component.
- Run migrations between config versions.
- Create/restore checksummed backups.
- Dispatch live-reload notifications to subscribers.
- Append-only audit logging of every operation.

---

## Internal Modules

| Class | Responsibility |
|---|---|
| `ConfigurationManager` | Core orchestrator (get/set/rollback/backup/reload). |
| `ConfigRegistry` | Component ID → file path index. |
| `ConfigCache` | In-memory resolved payload cache. |
| `SchemaManager` | Schema storage + validation engine. |
| `ConfigValidator` | Schema + dependency enforcement. |
| `EnvironmentManager` | Env var override resolution. |
| `SecretsReferenceManager` | `secret://` URI → proxy handle. |
| `VersionManager` | SemVer bump + history + rollback. |
| `MigrationManager` | Registered up/down transforms. |
| `BackupManager` | Snapshot create/restore with SHA-256 verification. |
| `LiveReloadManager` | Subscriber registration + dispatch with ACK. |
| `AuditLog` | Append-only JSONL audit trail. |

---

## Public Interfaces (Socket: `ConfigSocket`, v1)

| Message Type | Input | Output |
|---|---|---|
| `GET` | `{component_id, category, environment, user_id}` | `{status, payload}` |
| `SET` | `{component_id, category, payload}` | `{status}` |
| `VALIDATE` | `{category, payload}` | `{is_valid, errors, warnings}` |
| `RELOAD` | `{component_id}` | `{acknowledged}` |

Errors raise `ConfigError(status, message)` with `ConfigStatus`: `SUCCESS`, `INVALID_SCHEMA`, `NOT_FOUND`, `PERMISSION_DENIED`, `TIMEOUT`, `CONFLICT`.

---

## Pipeline (`ConfigPipeline`)

`run_get(request)` → cache check → disk read → validate → migrate → resolve secrets → apply env overrides → cache write → audit.

`run_set(request, payload)` → validate → backup pre-image → version bump → write → cache invalidate → live-reload dispatch → audit.

---

## Data Contracts

```python
ConfigRequest(component_id, category="default", environment="production", user_id="system")
ValidationResult(is_valid, errors, warnings)
ConfigRecord(component_id, payload, version, checksum, updated_at)
```

---

## State Management

- Cache: thread-safe (`RLock`), keyed `component_id:environment`.
- Version history: in-memory per-component list, monotonic patch bump.
- Storage: atomic write via temp file + `Path.replace`.

---

## Security

- No plaintext secrets ever cached or written — resolved to proxy handles only.
- Backups checksummed (SHA-256); restore aborts on mismatch.
- Least-privilege: organ exposes only socket methods above; no filesystem access is granted to callers.

---

## Failure Recovery

- Missing config → falls back to registered defaults, else `NOT_FOUND`.
- Invalid schema → rejected before write, audited.
- Corrupt backup → restore aborted, `INVALID_SCHEMA` raised.
- Reload dispatch failures do not block `SET`; partial ACKs logged.

---

## Logging / Audit

Append-only JSONL at `<base_dir>/audit/config_audit.jsonl`. Fields: `id`, `ts`, `action`, `component_id`, `status`, `detail`.

---

## Performance Targets

| Metric | Target |
|---|---|
| Cache read | <0.1 ms |
| Disk fetch + parse | <5 ms |
| Schema validation | <2 ms |
| Live reload propagation | <10 ms |
| Memory footprint | <64 MB RSS |

---

## Testing

`test_configuration_manager.py` covers: set/get, invalid rejection, not-found, cache hit, rollback, backup/restore, secrets resolution, socket GET/SET, live-reload subscriber ACK. All 9 tests pass.

---

## Extension Points

- Register additional schemas via `register_schema(category, schema)`.
- Register migrations via `register_migration(category, to_version, fn)`.
- Subscribe organs to live reload via `subscribe(component_id, callback)`.

---

## Implementation Checklist

- [x] Configuration Loading
- [x] Validation
- [x] Schema Enforcement
- [x] Defaults
- [x] Environment Overrides
- [x] Secrets References
- [x] Runtime Updates
- [x] Hot Reload
- [x] Versioning
- [x] Change Events
- [x] Rollback
- [x] Socket
- [x] Pipeline
- [x] Error Handling
- [x] Audit Logging
- [x] Testing
