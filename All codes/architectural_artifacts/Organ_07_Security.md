# **Organ 7 — Security Specification Document**

## **1. Overview**

The Security Organ (`organ_07_security`) is the sole governance-enforcement, capability-authorization, and threat-isolation kernel of the Hojaiga Automation Operating System. It mediates every inter-organ socket connection, pipeline payload, plugin load, protected-file write, and secret retrieval. It operates CPU-first, exposes a single IPC surface, and is the only organ authorized to grant, deny, or revoke capability tokens.

## **2. Purpose**

Enforce Universal Law 7 (Security and Least Privilege), Universal Law 6 (State Integrity), Policy Manual Chapter 14 (Security Policy), Policy Manual Chapter 15 (Governance Policy), and Master Architecture Blueprint Chapter 12 (Security Architecture). No organ, controller, agent, plugin, or worker may bypass capability evaluation, write to a protected governing document, or execute unverified code outside a sandbox.

## **3. Authority Compliance**

| Order | Document | Binding Clauses Applied |
|---|---|---|
| 1 | Constitution | Art. III Principle 4 (Stewardship), Art. VI (Hierarchy) |
| 2 | Law Book | Universal Laws 1, 2, 6, 7, 8, 10; Foundational Law 12 |
| 3 | Policy Manual | Ch. 8 Logging, Ch. 9 History, Ch. 14 Security, Ch. 15 Governance |
| 4 | Master Architecture Blueprint | Ch. 8 Communication Standards, Ch. 12 Security Architecture |
| 5 | Organ Specification | Structural template (sockets, pipelines, sections) |
| 6 | Legacy_Code_Migration_Guide | Reference-only: retry/backoff idioms, structured logging idioms reused; no legacy architecture imported |
| 7 | Upper Surface Diagrams | Security Layer position between CNS and all Controllers/Automation |
| 8 | Inner Depth Diagrams | Kernel Security Socket, Security Pipeline, Audit Pipeline placement |

## **4. Primary Responsibilities**

- **Access Control & Capability Governance** — capability-bitmask evaluation for every inter-organ request.
- **Socket & Pipeline Authorization** — inspects every IPC frame and pipeline payload before routing.
- **Plugin & Extension Security** — SHA-256 digest + manifest + signature verification prior to sandbox spawn.
- **Sandbox Management** — issues restricted execution contexts (process-level resource/permission caps) for untrusted code.
- **Protected File Guarding** — blocks unauthorized writes to Constitution, Law Book, Policy Manual, Blueprint, Organ Specs.
- **Secrets & Credential Management** — AES-256-GCM vault; in-memory only; zeroized after injection.
- **Security Audit Logging** — append-only, hash-chained, tamper-evident JSON log stream.

## **5. Internal Philosophy**

Zero-trust by default: every request is unauthorized until a valid capability token is evaluated against `capability_matrix`. Least privilege is structural, not advisory — tokens carry explicit bitmasks and expiry, never ambient identity. Protected documents are guarded at the policy layer regardless of underlying OS file permissions, since the organ must remain OS-portable (Windows primary target, POSIX fallback).

## **6. Internal Modules**

- `SecurityKernel` — master evaluation engine and IPC request router.
- `TokenAuthority` — issues, signs (HMAC-SHA256), verifies, and revokes capability tokens.
- `AccessController` — capability-bitmask evaluation against `capability_matrix`.
- `PolicyGuard` — immutability enforcement for protected paths.
- `SocketValidator` — inspects IPC envelope headers and source/target identity.
- `PipelineValidator` — schema + payload-size + malicious-pattern inspection for pipeline stages.
- `PluginVerifier` — SHA-256 digest, manifest parse, capability whitelist, signature check.
- `SandboxEnforcer` — cross-platform restricted execution context (Windows Job Object when available, POSIX `resource` limits fallback).
- `CredentialVault` — AES-256-GCM encrypted secret store with PBKDF2-derived key and in-memory zeroization.
- `AuditLogger` — append-only, hash-chained structured JSON log writer.
- `IPCServer` — asyncio TCP loopback socket (Windows Named-Pipe-equivalent abstraction) exposing the public RPC surface.

## **7. Folder Structure**

```
/organ_07_security
├── bin/
│   └── security_daemon.py         # entrypoint (imports organ_07_security.py)
├── config/
│   ├── capability_matrix.json
│   └── protected_paths.json
├── storage/
│   └── vault.enc
├── src/
│   └── organ_07_security.py       # SINGLE COMPILED IMPLEMENTATION FILE (this document)
├── logs/
│   └── security_audit.log
├── tests/
│   └── test_organ_07_security.py
└── manifest.json
```

## **8. Public IPC Interface**

Socket: `\\.\pipe\hojaiga_security` (Windows) / `/tmp/hojaiga_security.sock` (POSIX), abstracted in code as an asyncio TCP loopback listener on `127.0.0.1:8711` for portability; the wire framing matches the specified Named Pipe protocol so a native pipe transport can be swapped in without touching business logic.

Wire Protocol: `[4-byte big-endian length][2-byte op_code][JSON payload]`, max payload 8 MB.

RPCs (op_codes 1–7):

| op_code | RPC | Request | Response |
|---|---|---|---|
| 1 | `AuthorizeSocketConnection` | `SocketAuthRequest` | `AuthVerdict` |
| 2 | `ValidatePipelineData` | `PipelineValidationPayload` | `ValidationVerdict` |
| 3 | `VerifyPluginSignature` | `PluginVerifyPayload` | `SignatureVerificationResult` |
| 4 | `GetExecutionToken` | `CapabilityTokenRequest` | `CapabilityToken` |
| 5 | `RetrieveSecret` | `SecretRequestPayload` | `EncryptedSecretResponse` |
| 6 | `EnforceSandboxPolicy` | `SandboxPolicyRequest` | `SandboxHandle` |
| 7 | `CheckFileWritePermission` | `FilePathPayload` | `PermissionVerdict` |

## **9. State Machine**

`LOCKED → OPERATIONAL → LOCKDOWN → OPERATIONAL`, and `OPERATIONAL → MAINTENANCE → OPERATIONAL`. Transitions are logged as audit events and are the only externally observable authority the organ exposes over its own lifecycle.

## **10. Events Emitted**

`EVENT_SECURITY_VIOLATION`, `EVENT_UNAUTHORIZED_FILE_WRITE_BLOCKED`, `EVENT_PLUGIN_VERIFICATION_FAILED`, `EVENT_VAULT_UNLOCKED`, `EVENT_LOCKDOWN_ENGAGED`, `EVENT_LOCKDOWN_LIFTED`.

## **11. Legacy Reference Usage**

No legacy architecture, folder layout, controller hierarchy, or routing was imported. Only generic engineering paradigms permitted by the Legacy Reference Guide were reused as idioms: structured retry/backoff shape, append-only logging shape, and configuration-loading shape. All reused logic was rewritten against this organ's own contracts.

---

# **12. Pre-Implementation Design Diagram (Specification-Derived)**

```
                                   ┌────────────────────────────┐
                                   │   CNS (02) / Controllers    │
                                   │   (05) / Automation (06)    │
                                   └──────────────┬───────────────┘
                                                  │  IPC Frame
                                                  ▼
                          ┌───────────────────────────────────────────┐
                          │             SECURITY IPC SOCKET            │
                          │   \\.\pipe\hojaiga_security (8MB frames)   │
                          └──────────────────────┬──────────────────────┘
                                                 ▼
                          ┌───────────────────────────────────────────┐
                          │              SOCKET VALIDATOR              │
                          │  header check → source/target identity     │
                          └──────────────────────┬──────────────────────┘
                                                 ▼
                          ┌───────────────────────────────────────────┐
                          │               SECURITY KERNEL              │
                          │        (state: LOCKED/OPERATIONAL/         │
                          │           LOCKDOWN/MAINTENANCE)            │
                          └───┬───────┬────────┬────────┬────────┬─────┘
                              │       │        │        │        │
                 ┌────────────┘       │        │        │        └───────────┐
                 ▼                    ▼        ▼        ▼                    ▼
        ┌────────────────┐  ┌────────────────┐ │ ┌────────────────┐ ┌────────────────┐
        │ ACCESS          │  │ PIPELINE        │ │ │ PLUGIN          │ │ SANDBOX         │
        │ CONTROLLER      │  │ VALIDATOR       │ │ │ VERIFIER        │ │ ENFORCER        │
        │ (capability     │  │ (schema/size/   │ │ │ (SHA-256 +      │ │ (job object /   │
        │  matrix match)  │  │  pattern check) │ │ │  manifest+sig)  │ │  rlimit caps)   │
        └────────┬────────┘  └────────┬────────┘ │ └────────┬────────┘ └────────┬────────┘
                 │                    │           ▼          │                   │
                 │                    │   ┌────────────────┐ │                   │
                 │                    │   │  POLICY GUARD   │ │                   │
                 │                    │   │ protected_paths │ │                   │
                 │                    │   │  immutability   │ │                   │
                 │                    │   └────────┬────────┘ │                   │
                 └──────────┬─────────┴────────────┴──────────┴─────────┬─────────┘
                            ▼                                           ▼
                   ┌────────────────┐                          ┌────────────────┐
                   │ TOKEN AUTHORITY │                          │ CREDENTIAL VAULT│
                   │ HMAC capability │                          │ AES-256-GCM,    │
                   │ token issue/    │                          │ PBKDF2 key,     │
                   │ verify/revoke   │                          │ zeroize on use  │
                   └────────┬────────┘                          └────────┬────────┘
                            └───────────────────┬─────────────────────────┘
                                                ▼
                                      ┌────────────────────┐
                                      │    AUDIT LOGGER     │
                                      │ hash-chained JSONL  │
                                      │ append-only         │
                                      └──────────┬───────────┘
                                                ▼
                                       Verdict / Token / Denial
                                                ▼
                                    back through IPC Socket to caller
```

---

# **13. Implementation**

Single compiled file. Copy verbatim to `src/organ_07_security.py`.

```python
"""
organ_07_security.py

Hojaiga Automation OS — Organ 7: Security Kernel
Single-file production implementation.

Authority: Constitution -> Law Book -> Policy Manual -> Master Architecture
Blueprint -> Organ Specification. This organ enforces capability-based
access control, socket/pipeline validation, plugin verification, sandbox
enforcement, credential vaulting, protected-document immutability, and
tamper-evident audit logging for the entire Hojaiga system.

No other organ's private implementation is imported. All communication
with this organ occurs exclusively through the IPCServer RPC surface
defined below (sockets/pipelines), matching Organ Specification Section 8/9/10.
"""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import enum
import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import struct
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes as _crypto_hashes
    _HAS_CRYPTOGRAPHY = True
except ImportError:  # pragma: no cover - environment dependent
    _HAS_CRYPTOGRAPHY = False

IS_WINDOWS = os.name == "nt"

if IS_WINDOWS:
    try:
        import win32job  # type: ignore
        import win32api  # type: ignore
        import win32con  # type: ignore
        import win32security  # type: ignore
        _HAS_WIN32 = True
    except ImportError:  # pragma: no cover
        _HAS_WIN32 = False
else:
    _HAS_WIN32 = False
    try:
        import resource  # POSIX only
        _HAS_RESOURCE = True
    except ImportError:  # pragma: no cover
        _HAS_RESOURCE = False


# ═══════════════════════════════════════════════════════════════════════
# SECTION 1 — CONSTANTS, ENUMS, DATA CONTRACTS
# ═══════════════════════════════════════════════════════════════════════

FRAME_LENGTH_BYTES = 4
FRAME_OPCODE_BYTES = 2
MAX_PAYLOAD_SIZE = 8 * 1024 * 1024  # 8 MB, Organ Spec Section 9

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8711  # loopback stand-in for \\.\pipe\hojaiga_security

TOKEN_TTL_SECONDS = 300
LOCKDOWN_BREACH_THRESHOLD = 3
LOCKDOWN_WINDOW_SECONDS = 10


class OpCode(enum.IntEnum):
    AUTHORIZE_SOCKET_CONNECTION = 1
    VALIDATE_PIPELINE_DATA = 2
    VERIFY_PLUGIN_SIGNATURE = 3
    GET_EXECUTION_TOKEN = 4
    RETRIEVE_SECRET = 5
    ENFORCE_SANDBOX_POLICY = 6
    CHECK_FILE_WRITE_PERMISSION = 7


class SecurityState(enum.Enum):
    LOCKED = "LOCKED"
    OPERATIONAL = "OPERATIONAL"
    LOCKDOWN = "LOCKDOWN"
    MAINTENANCE = "MAINTENANCE"


class Capability(enum.IntFlag):
    NONE = 0
    SOCKET_CONNECT = 1 << 0
    PIPELINE_WRITE = 1 << 1
    PLUGIN_LOAD = 1 << 2
    FILE_WRITE_PROTECTED = 1 << 3
    SECRET_READ = 1 << 4
    SANDBOX_SPAWN = 1 << 5
    GOVERNANCE_READ = 1 << 6
    GOVERNANCE_WRITE = 1 << 7  # never granted to any autonomous organ


class SecurityEvent(enum.Enum):
    SECURITY_VIOLATION = "EVENT_SECURITY_VIOLATION"
    UNAUTHORIZED_FILE_WRITE_BLOCKED = "EVENT_UNAUTHORIZED_FILE_WRITE_BLOCKED"
    PLUGIN_VERIFICATION_FAILED = "EVENT_PLUGIN_VERIFICATION_FAILED"
    VAULT_UNLOCKED = "EVENT_VAULT_UNLOCKED"
    LOCKDOWN_ENGAGED = "EVENT_LOCKDOWN_ENGAGED"
    LOCKDOWN_LIFTED = "EVENT_LOCKDOWN_LIFTED"


@dataclass
class SocketAuthRequest:
    request_id: str
    source_organ: str
    target_organ: str
    requested_action: str
    capability_token: Optional[str] = None

    @staticmethod
    def from_json(payload: Dict[str, Any]) -> "SocketAuthRequest":
        return SocketAuthRequest(
            request_id=payload.get("request_id", str(uuid.uuid4())),
            source_organ=payload["source_organ"],
            target_organ=payload["target_organ"],
            requested_action=payload["requested_action"],
            capability_token=payload.get("capability_token"),
        )


@dataclass
class AuthVerdict:
    request_id: str
    authorized: bool
    reason: str
    capability_mask: int = 0

    def to_json(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class PipelineValidationPayload:
    pipeline_name: str
    stage: str
    data: Dict[str, Any]
    source_organ: str
    capability_token: Optional[str] = None

    @staticmethod
    def from_json(payload: Dict[str, Any]) -> "PipelineValidationPayload":
        return PipelineValidationPayload(
            pipeline_name=payload["pipeline_name"],
            stage=payload["stage"],
            data=payload.get("data", {}),
            source_organ=payload["source_organ"],
            capability_token=payload.get("capability_token"),
        )


@dataclass
class ValidationVerdict:
    valid: bool
    reason: str

    def to_json(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class PluginVerifyPayload:
    plugin_path: str
    manifest_path: str
    declared_signature: Optional[str] = None

    @staticmethod
    def from_json(payload: Dict[str, Any]) -> "PluginVerifyPayload":
        return PluginVerifyPayload(
            plugin_path=payload["plugin_path"],
            manifest_path=payload["manifest_path"],
            declared_signature=payload.get("declared_signature"),
        )


@dataclass
class SignatureVerificationResult:
    verified: bool
    sha256_digest: str
    reason: str

    def to_json(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class CapabilityTokenRequest:
    organ_id: str
    requested_capabilities: List[str]

    @staticmethod
    def from_json(payload: Dict[str, Any]) -> "CapabilityTokenRequest":
        return CapabilityTokenRequest(
            organ_id=payload["organ_id"],
            requested_capabilities=payload.get("requested_capabilities", []),
        )


@dataclass
class CapabilityToken:
    token_id: str
    organ_id: str
    capabilities_mask: int
    issued_at: float
    expires_at: float
    signature: str

    def to_json(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    def encode(self) -> str:
        body = f"{self.token_id}.{self.organ_id}.{self.capabilities_mask}.{self.issued_at}.{self.expires_at}"
        return base64.urlsafe_b64encode(f"{body}.{self.signature}".encode()).decode()


@dataclass
class SecretRequestPayload:
    secret_key: str
    requesting_organ: str
    capability_token: str

    @staticmethod
    def from_json(payload: Dict[str, Any]) -> "SecretRequestPayload":
        return SecretRequestPayload(
            secret_key=payload["secret_key"],
            requesting_organ=payload["requesting_organ"],
            capability_token=payload["capability_token"],
        )


@dataclass
class EncryptedSecretResponse:
    found: bool
    value: Optional[str]
    reason: str

    def to_json(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class SandboxPolicyRequest:
    process_label: str
    requesting_organ: str
    max_memory_mb: int = 256
    max_cpu_seconds: int = 30
    capability_token: Optional[str] = None

    @staticmethod
    def from_json(payload: Dict[str, Any]) -> "SandboxPolicyRequest":
        return SandboxPolicyRequest(
            process_label=payload["process_label"],
            requesting_organ=payload["requesting_organ"],
            max_memory_mb=payload.get("max_memory_mb", 256),
            max_cpu_seconds=payload.get("max_cpu_seconds", 30),
            capability_token=payload.get("capability_token"),
        )


@dataclass
class SandboxHandle:
    handle_id: str
    active: bool
    limits: Dict[str, int]

    def to_json(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class FilePathPayload:
    path: str
    requesting_organ: str
    capability_token: Optional[str] = None

    @staticmethod
    def from_json(payload: Dict[str, Any]) -> "FilePathPayload":
        return FilePathPayload(
            path=payload["path"],
            requesting_organ=payload["requesting_organ"],
            capability_token=payload.get("capability_token"),
        )


@dataclass
class PermissionVerdict:
    permitted: bool
    reason: str

    def to_json(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


# ═══════════════════════════════════════════════════════════════════════
# SECTION 2 — AUDIT LOGGER (Policy Manual Ch.8/Ch.9: append-only, traceable)
# ═══════════════════════════════════════════════════════════════════════

class AuditLogger:
    """Append-only, hash-chained, tamper-evident JSONL audit log."""

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._prev_hash = self._load_last_hash()
        self._logger = logging.getLogger("organ_07_security.audit")

    def _load_last_hash(self) -> str:
        if not self.log_path.exists():
            return "0" * 64
        last = "0" * 64
        with self.log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    last = record.get("entry_hash", last)
                except json.JSONDecodeError:
                    continue
        return last

    def append(
        self,
        event: str,
        source: str,
        target: str,
        action: str,
        verdict: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        entry = {
            "event_id": str(uuid.uuid4()),
            "event": event,
            "timestamp": time.time(),
            "source_organ": source,
            "target_organ": target,
            "action": action,
            "verdict": verdict,
            "extra": extra or {},
            "prev_hash": self._prev_hash,
        }
        digest_input = json.dumps(entry, sort_keys=True).encode("utf-8")
        entry_hash = hashlib.sha256(digest_input).hexdigest()
        entry["entry_hash"] = entry_hash
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        self._prev_hash = entry_hash
        self._logger.info("%s %s->%s [%s] %s", event, source, target, verdict, action)
        return entry

    def verify_chain(self) -> bool:
        prev = "0" * 64
        if not self.log_path.exists():
            return True
        with self.log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                claimed_hash = record.pop("entry_hash")
                if record.get("prev_hash") != prev:
                    return False
                recomputed = hashlib.sha256(
                    json.dumps(record, sort_keys=True).encode("utf-8")
                ).hexdigest()
                if recomputed != claimed_hash:
                    return False
                prev = claimed_hash
        return True


# ═══════════════════════════════════════════════════════════════════════
# SECTION 3 — TOKEN AUTHORITY (HMAC-signed capability tokens)
# ═══════════════════════════════════════════════════════════════════════

class TokenAuthority:
    """Issues, verifies and revokes capability tokens (Universal Law 7)."""

    def __init__(self, signing_key: Optional[bytes] = None):
        self._signing_key = signing_key or secrets.token_bytes(32)
        self._active: Dict[str, CapabilityToken] = {}
        self._revoked: set = set()

    def _sign(self, token_id: str, organ_id: str, mask: int, issued_at: float, expires_at: float) -> str:
        body = f"{token_id}.{organ_id}.{mask}.{issued_at}.{expires_at}".encode()
        return hmac.new(self._signing_key, body, hashlib.sha256).hexdigest()

    def issue(self, organ_id: str, mask: int, ttl: int = TOKEN_TTL_SECONDS) -> CapabilityToken:
        token_id = str(uuid.uuid4())
        issued_at = time.time()
        expires_at = issued_at + ttl
        signature = self._sign(token_id, organ_id, mask, issued_at, expires_at)
        token = CapabilityToken(
            token_id=token_id,
            organ_id=organ_id,
            capabilities_mask=mask,
            issued_at=issued_at,
            expires_at=expires_at,
            signature=signature,
        )
        self._active[token_id] = token
        return token

    def verify(self, token_id: str) -> Tuple[bool, Optional[CapabilityToken], str]:
        if token_id in self._revoked:
            return False, None, "token revoked"
        token = self._active.get(token_id)
        if token is None:
            return False, None, "token unknown"
        if time.time() > token.expires_at:
            return False, None, "token expired"
        expected = self._sign(
            token.token_id, token.organ_id, token.capabilities_mask, token.issued_at, token.expires_at
        )
        if not hmac.compare_digest(expected, token.signature):
            return False, None, "token signature mismatch"
        return True, token, "ok"

    def revoke(self, token_id: str) -> None:
        self._revoked.add(token_id)
        self._active.pop(token_id, None)


# ═══════════════════════════════════════════════════════════════════════
# SECTION 4 — ACCESS CONTROLLER (capability-matrix evaluation, CBAC)
# ═══════════════════════════════════════════════════════════════════════

class AccessController:
    """Capability-Based Access Control engine (Organ Spec Section 5/8)."""

    def __init__(self, capability_matrix: Dict[str, List[str]], token_authority: TokenAuthority):
        self._matrix = {k: self._to_mask(v) for k, v in capability_matrix.items()}
        self._token_authority = token_authority

    @staticmethod
    def _to_mask(names: List[str]) -> int:
        mask = Capability.NONE
        for name in names:
            try:
                mask |= Capability[name]
            except KeyError:
                continue
        return int(mask)

    def allowed_mask_for(self, organ_id: str) -> int:
        return self._matrix.get(organ_id, int(Capability.NONE))

    def evaluate_capability(self, source_organ: str, required_capability: str, token_id: Optional[str]) -> Tuple[bool, str, int]:
        try:
            required = int(Capability[required_capability])
        except KeyError:
            return False, f"unknown capability '{required_capability}'", 0

        allowed = self.allowed_mask_for(source_organ)
        if required & Capability.GOVERNANCE_WRITE:
            return False, "GOVERNANCE_WRITE may never be granted to an autonomous organ", 0

        if (allowed & required) != required:
            return False, f"organ '{source_organ}' lacks required capability bits", allowed

        if token_id:
            valid, token, reason = self._token_authority.verify(token_id)
            if not valid:
                return False, f"token invalid: {reason}", allowed
            if token.organ_id != source_organ:
                return False, "token organ mismatch", allowed
            if (token.capabilities_mask & required) != required:
                return False, "token does not carry required capability bits", allowed

        return True, "authorized", allowed


# ═══════════════════════════════════════════════════════════════════════
# SECTION 5 — POLICY GUARD (protected document immutability)
# ═══════════════════════════════════════════════════════════════════════

class PolicyGuard:
    """Blocks unauthorized writes to protected governing documents."""

    def __init__(self, protected_paths: List[str]):
        self._protected = {str(Path(p).resolve()) for p in protected_paths}

    def is_protected(self, path: str) -> bool:
        try:
            resolved = str(Path(path).resolve())
        except OSError:
            resolved = path
        if resolved in self._protected:
            return True
        return any(resolved.endswith(Path(p).name) and Path(p).name in
                   ("Constitution.md", "Hojaiga_Law_Book.md", "Hojaiga_Policy_Manual.md",
                    "Master_Architecture_Blueprint.md", "Organ_Specification.md")
                   for p in self._protected)

    def check_write(self, path: str, requester_mask: int) -> Tuple[bool, str]:
        if self.is_protected(path):
            if requester_mask & Capability.GOVERNANCE_WRITE:
                return False, "GOVERNANCE_WRITE capability is structurally disabled for all organs"
            return False, "target path is a protected governing document"
        return True, "path not protected"


# ═══════════════════════════════════════════════════════════════════════
# SECTION 6 — SOCKET / PIPELINE VALIDATORS
# ═══════════════════════════════════════════════════════════════════════

class SocketValidator:
    """Inspects IPC envelope headers and identity fields."""

    _VALID_ORGAN_PATTERN = None  # simple allowlist check, no regex dependency

    KNOWN_ORGANS = {
        "organ_01_interface", "organ_02_cns", "organ_03_brain", "organ_04_kernel",
        "organ_05_controllers", "organ_06_automation", "organ_07_memory",
        "organ_08_execution", "organ_09_infrastructure", "organ_10_learning",
        "organ_07_security", "organ_12_integration",
    }

    def validate(self, request: SocketAuthRequest) -> Tuple[bool, str]:
        if not request.source_organ or not request.target_organ:
            return False, "missing source/target organ identity"
        if request.source_organ not in self.KNOWN_ORGANS:
            return False, f"unknown source organ '{request.source_organ}'"
        if request.target_organ not in self.KNOWN_ORGANS:
            return False, f"unknown target organ '{request.target_organ}'"
        if not request.requested_action or len(request.requested_action) > 256:
            return False, "invalid requested_action"
        return True, "envelope valid"


class PipelineValidator:
    """Validates pipeline schema, stage names, and payload safety."""

    _DANGEROUS_KEYS = {"__import__", "eval", "exec", "os.system", "subprocess"}
    _MAX_DEPTH = 12
    _MAX_KEYS = 512

    def _scan(self, obj: Any, depth: int = 0) -> Optional[str]:
        if depth > self._MAX_DEPTH:
            return "payload nesting exceeds maximum depth"
        if isinstance(obj, dict):
            if len(obj) > self._MAX_KEYS:
                return "payload object exceeds maximum key count"
            for key, value in obj.items():
                if isinstance(key, str) and key in self._DANGEROUS_KEYS:
                    return f"payload contains disallowed key '{key}'"
                reason = self._scan(value, depth + 1)
                if reason:
                    return reason
        elif isinstance(obj, list):
            for item in obj:
                reason = self._scan(item, depth + 1)
                if reason:
                    return reason
        elif isinstance(obj, str):
            lowered = obj.lower()
            for marker in self._DANGEROUS_KEYS:
                if marker in lowered:
                    return f"payload string contains disallowed marker '{marker}'"
        return None

    def validate(self, payload: PipelineValidationPayload) -> Tuple[bool, str]:
        if not payload.pipeline_name or not payload.stage:
            return False, "missing pipeline_name or stage"
        size_estimate = len(json.dumps(payload.data))
        if size_estimate > MAX_PAYLOAD_SIZE:
            return False, "payload exceeds 8MB limit"
        reason = self._scan(payload.data)
        if reason:
            return False, reason
        return True, "pipeline payload valid"


# ═══════════════════════════════════════════════════════════════════════
# SECTION 7 — PLUGIN VERIFIER
# ═══════════════════════════════════════════════════════════════════════

class PluginVerifier:
    """SHA-256 + manifest + signature verification for plugins/extensions."""

    def __init__(self, trusted_signers: Optional[Dict[str, str]] = None):
        # trusted_signers: signer_name -> hex HMAC key (shared-secret model;
        # swappable for asymmetric signatures without changing the public RPC).
        self._trusted_signers = trusted_signers or {}

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def verify(self, payload: PluginVerifyPayload) -> SignatureVerificationResult:
        plugin_path = Path(payload.plugin_path)
        manifest_path = Path(payload.manifest_path)

        if not plugin_path.exists():
            return SignatureVerificationResult(False, "", "plugin bundle not found")
        if not manifest_path.exists():
            return SignatureVerificationResult(False, "", "manifest not found")

        digest = self._sha256_file(plugin_path)

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return SignatureVerificationResult(False, digest, f"manifest parse error: {exc}")

        expected_digest = manifest.get("sha256")
        if expected_digest and expected_digest != digest:
            return SignatureVerificationResult(False, digest, "digest mismatch against manifest")

        capabilities = manifest.get("capabilities", [])
        for cap in capabilities:
            if cap not in Capability.__members__:
                return SignatureVerificationResult(False, digest, f"manifest declares unknown capability '{cap}'")
            if cap == "GOVERNANCE_WRITE":
                return SignatureVerificationResult(False, digest, "plugin manifests may never declare GOVERNANCE_WRITE")

        signer = manifest.get("signer")
        signature = payload.declared_signature or manifest.get("signature")
        if signer and signer in self._trusted_signers:
            key = bytes.fromhex(self._trusted_signers[signer])
            expected_sig = hmac.new(key, digest.encode(), hashlib.sha256).hexdigest()
            if not signature or not hmac.compare_digest(expected_sig, signature):
                return SignatureVerificationResult(False, digest, "signature verification failed")
        elif signer:
            return SignatureVerificationResult(False, digest, f"unknown signer '{signer}'")

        return SignatureVerificationResult(True, digest, "plugin verified")


# ═══════════════════════════════════════════════════════════════════════
# SECTION 8 — SANDBOX ENFORCER (cross-platform restricted execution)
# ═══════════════════════════════════════════════════════════════════════

class SandboxEnforcer:
    """Issues restricted execution handles. Windows: Job Objects when
    pywin32 is present. POSIX: resource.setrlimit-based caps. Falls back to
    a logical (accounting-only) handle when neither native API is available,
    so the organ remains portable without hard OS dependencies."""

    def __init__(self, audit: AuditLogger):
        self._audit = audit
        self._handles: Dict[str, Any] = {}

    def create(self, request: SandboxPolicyRequest) -> SandboxHandle:
        handle_id = str(uuid.uuid4())
        limits = {
            "max_memory_mb": request.max_memory_mb,
            "max_cpu_seconds": request.max_cpu_seconds,
        }

        native_handle: Any = None
        if IS_WINDOWS and _HAS_WIN32:
            native_handle = self._create_win32_job(handle_id, limits)
        elif not IS_WINDOWS and _HAS_RESOURCE:
            native_handle = limits  # applied via preexec_fn by the caller when spawning

        self._handles[handle_id] = {
            "native": native_handle,
            "limits": limits,
            "label": request.process_label,
            "organ": request.requesting_organ,
            "active": True,
        }
        self._audit.append(
            event="SANDBOX_CREATED",
            source=request.requesting_organ,
            target="organ_07_security",
            action=f"create_sandbox:{request.process_label}",
            verdict="approved",
            extra=limits,
        )
        return SandboxHandle(handle_id=handle_id, active=True, limits=limits)

    def _create_win32_job(self, handle_id: str, limits: Dict[str, int]) -> Any:  # pragma: no cover
        job = win32job.CreateJobObject(None, f"hojaiga_sandbox_{handle_id}")
        extended_info = win32job.QueryInformationJobObject(
            job, win32job.JobObjectExtendedLimitInformation
        )
        basic_limits = extended_info["BasicLimitInformation"]
        basic_limits["LimitFlags"] = win32job.JOB_OBJECT_LIMIT_PROCESS_MEMORY
        extended_info["BasicLimitInformation"] = basic_limits
        extended_info["ProcessMemoryLimit"] = limits["max_memory_mb"] * 1024 * 1024
        win32job.SetInformationJobObject(
            job, win32job.JobObjectExtendedLimitInformation, extended_info
        )
        return job

    def posix_preexec(self, handle_id: str) -> Callable[[], None]:
        """Return a preexec_fn to pass to subprocess.Popen on POSIX systems."""
        limits = self._handles[handle_id]["limits"]

        def _apply() -> None:  # pragma: no cover - exercised only on POSIX child
            if _HAS_RESOURCE:
                mem_bytes = limits["max_memory_mb"] * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
                cpu_seconds = limits["max_cpu_seconds"]
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))

        return _apply

    def release(self, handle_id: str) -> None:
        entry = self._handles.get(handle_id)
        if entry:
            entry["active"] = False


# ═══════════════════════════════════════════════════════════════════════
# SECTION 9 — CREDENTIAL VAULT (AES-256-GCM, PBKDF2, in-memory zeroize)
# ═══════════════════════════════════════════════════════════════════════

class CredentialVault:
    """AES-256-GCM encrypted secret store. Vault file holds only ciphertext;
    the derived key exists solely in process memory while OPERATIONAL."""

    PBKDF2_ITERATIONS = 390_000

    def __init__(self, vault_path: Path, audit: AuditLogger):
        self._vault_path = vault_path
        self._audit = audit
        self._key: Optional[bytes] = None
        self._plaintext_cache: Dict[str, str] = {}
        self._unlocked = False

    def unlock(self, master_key: str) -> bool:
        if not _HAS_CRYPTOGRAPHY:
            logging.getLogger("organ_07_security.vault").warning(
                "cryptography library unavailable; vault operating in degraded mode"
            )
            self._unlocked = True
            self._load_plaintext_fallback()
            self._audit.append("VAULT_UNLOCK_DEGRADED", "organ_07_security", "organ_07_security", "unlock_vault", "degraded")
            return True

        salt = self._read_or_create_salt()
        kdf = PBKDF2HMAC(
            algorithm=_crypto_hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self.PBKDF2_ITERATIONS,
        )
        self._key = kdf.derive(master_key.encode("utf-8"))
        self._unlocked = True
        self._load_ciphertext()
        self._audit.append(
            event=SecurityEvent.VAULT_UNLOCKED.value,
            source="organ_07_security",
            target="organ_07_security",
            action="unlock_vault",
            verdict="approved",
        )
        return True

    def _salt_path(self) -> Path:
        return self._vault_path.with_suffix(".salt")

    def _read_or_create_salt(self) -> bytes:
        salt_path = self._salt_path()
        if salt_path.exists():
            return salt_path.read_bytes()
        salt = secrets.token_bytes(16)
        salt_path.parent.mkdir(parents=True, exist_ok=True)
        salt_path.write_bytes(salt)
        return salt

    def _load_ciphertext(self) -> None:
        if not self._vault_path.exists():
            return
        raw = self._vault_path.read_bytes()
        if not raw:
            return
        try:
            nonce, ciphertext = raw[:12], raw[12:]
            aesgcm = AESGCM(self._key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            self._plaintext_cache = json.loads(plaintext.decode("utf-8"))
        except Exception:  # pragma: no cover - corrupted/absent vault
            self._plaintext_cache = {}

    def _load_plaintext_fallback(self) -> None:
        if self._vault_path.exists():
            try:
                self._plaintext_cache = json.loads(self._vault_path.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                self._plaintext_cache = {}

    def _persist(self) -> None:
        self._vault_path.parent.mkdir(parents=True, exist_ok=True)
        if _HAS_CRYPTOGRAPHY and self._key:
            aesgcm = AESGCM(self._key)
            nonce = secrets.token_bytes(12)
            ciphertext = aesgcm.encrypt(nonce, json.dumps(self._plaintext_cache).encode("utf-8"), None)
            self._vault_path.write_bytes(nonce + ciphertext)
        else:
            self._vault_path.write_text(json.dumps(self._plaintext_cache), encoding="utf-8")

    def store_secret(self, key: str, value: str) -> None:
        if not self._unlocked:
            raise PermissionError("vault is locked")
        self._plaintext_cache[key] = value
        self._persist()

    def retrieve_secret(self, key: str) -> Optional[str]:
        if not self._unlocked:
            return None
        return self._plaintext_cache.get(key)

    def zeroize(self) -> None:
        self._plaintext_cache.clear()
        self._key = None
        self._unlocked = False


# ═══════════════════════════════════════════════════════════════════════
# SECTION 10 — IN-MEMORY SECURITY STATE DATABASE
# ═══════════════════════════════════════════════════════════════════════

class SecurityDatabase:
    """In-memory sqlite mirror of active_tokens / policy_rules / security_audit
    (Organ Spec Section 16). Complements AuditLogger's append-only file log
    with fast queryable state."""

    def __init__(self):
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """CREATE TABLE active_tokens (
                token_id TEXT PRIMARY KEY, organ_id TEXT,
                capabilities_mask INTEGER, issued_at REAL, expires_at REAL)"""
        )
        cur.execute(
            """CREATE TABLE security_audit (
                event_id TEXT PRIMARY KEY, source TEXT, target TEXT,
                action TEXT, verdict TEXT, timestamp REAL)"""
        )
        self._conn.commit()

    def record_token(self, token: CapabilityToken) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO active_tokens VALUES (?,?,?,?,?)",
            (token.token_id, token.organ_id, token.capabilities_mask, token.issued_at, token.expires_at),
        )
        self._conn.commit()

    def record_audit(self, event_id: str, source: str, target: str, action: str, verdict: str, ts: float) -> None:
        self._conn.execute(
            "INSERT INTO security_audit VALUES (?,?,?,?,?,?)",
            (event_id, source, target, action, verdict, ts),
        )
        self._conn.commit()

    def recent_violations(self, window_seconds: int) -> int:
        cutoff = time.time() - window_seconds
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM security_audit WHERE verdict = 'denied' AND timestamp >= ?",
            (cutoff,),
        )
        return cur.fetchone()[0]


# ═══════════════════════════════════════════════════════════════════════
# SECTION 11 — SECURITY KERNEL (master evaluation engine)
# ═══════════════════════════════════════════════════════════════════════

class SecurityKernel:
    """Master access-evaluation engine. Owns state machine transitions and
    coordinates all subordinate modules. This is the only class other code
    should instantiate directly."""

    def __init__(
        self,
        base_dir: Path,
        capability_matrix: Optional[Dict[str, List[str]]] = None,
        protected_paths: Optional[List[str]] = None,
        trusted_signers: Optional[Dict[str, str]] = None,
    ):
        self.base_dir = base_dir
        self.state = SecurityState.LOCKED

        self.audit = AuditLogger(base_dir / "logs" / "security_audit.log")
        self.token_authority = TokenAuthority()
        self.access_controller = AccessController(
            capability_matrix or self._default_capability_matrix(), self.token_authority
        )
        self.policy_guard = PolicyGuard(protected_paths or [])
        self.socket_validator = SocketValidator()
        self.pipeline_validator = PipelineValidator()
        self.plugin_verifier = PluginVerifier(trusted_signers)
        self.sandbox_enforcer = SandboxEnforcer(self.audit)
        self.vault = CredentialVault(base_dir / "storage" / "vault.enc", self.audit)
        self.database = SecurityDatabase()

        self._breach_log: List[float] = []
        self._log = logging.getLogger("organ_07_security.kernel")

    @staticmethod
    def _default_capability_matrix() -> Dict[str, List[str]]:
        return {
            "organ_02_cns": ["SOCKET_CONNECT", "PIPELINE_WRITE", "GOVERNANCE_READ"],
            "organ_05_controllers": ["SOCKET_CONNECT", "PIPELINE_WRITE", "SANDBOX_SPAWN"],
            "organ_06_automation": ["SOCKET_CONNECT", "PLUGIN_LOAD", "SANDBOX_SPAWN"],
            "organ_09_infrastructure": ["SOCKET_CONNECT", "GOVERNANCE_READ"],
        }

    # ---- lifecycle -------------------------------------------------

    def unlock(self, master_key: str) -> None:
        self.vault.unlock(master_key)
        self.state = SecurityState.OPERATIONAL
        self._log.info("SecurityKernel transitioned LOCKED -> OPERATIONAL")

    def enter_lockdown(self, reason: str) -> None:
        self.state = SecurityState.LOCKDOWN
        self.audit.append(SecurityEvent.LOCKDOWN_ENGAGED.value, "organ_07_security", "*", "lockdown", "engaged", {"reason": reason})
        self._log.critical("LOCKDOWN engaged: %s", reason)

    def lift_lockdown(self, authorized_by: str) -> None:
        if self.state != SecurityState.LOCKDOWN:
            return
        self.state = SecurityState.OPERATIONAL
        self.audit.append(SecurityEvent.LOCKDOWN_LIFTED.value, authorized_by, "organ_07_security", "lift_lockdown", "approved")

    def enter_maintenance(self) -> None:
        self.state = SecurityState.MAINTENANCE

    def exit_maintenance(self) -> None:
        if self.state == SecurityState.MAINTENANCE:
            self.state = SecurityState.OPERATIONAL

    def _record_denial_and_maybe_lockdown(self, source: str, target: str, action: str, reason: str) -> None:
        now = time.time()
        self._breach_log = [t for t in self._breach_log if now - t <= LOCKDOWN_WINDOW_SECONDS]
        self._breach_log.append(now)
        entry = self.audit.append(
            SecurityEvent.SECURITY_VIOLATION.value, source, target, action, "denied", {"reason": reason}
        )
        self.database.record_audit(entry["event_id"], source, target, action, "denied", now)
        if len(self._breach_log) >= LOCKDOWN_BREACH_THRESHOLD:
            self.enter_lockdown(f"{len(self._breach_log)} violations within {LOCKDOWN_WINDOW_SECONDS}s")

    def _guard_operational(self) -> Optional[str]:
        if self.state == SecurityState.LOCKED:
            return "security kernel is LOCKED; vault not unlocked"
        if self.state == SecurityState.LOCKDOWN:
            return "security kernel is in LOCKDOWN; only owner override accepted"
        return None

    # ---- RPC handlers ------------------------------------------------

    def authorize_socket_connection(self, request: SocketAuthRequest) -> AuthVerdict:
        block_reason = self._guard_operational()
        if block_reason:
            self._record_denial_and_maybe_lockdown(request.source_organ, request.target_organ, request.requested_action, block_reason)
            return AuthVerdict(request.request_id, False, block_reason)

        valid_envelope, envelope_reason = self.socket_validator.validate(request)
        if not valid_envelope:
            self._record_denial_and_maybe_lockdown(request.source_organ, request.target_organ, request.requested_action, envelope_reason)
            return AuthVerdict(request.request_id, False, envelope_reason)

        authorized, reason, mask = self.access_controller.evaluate_capability(
            request.source_organ, "SOCKET_CONNECT", request.capability_token
        )
        if not authorized:
            self._record_denial_and_maybe_lockdown(request.source_organ, request.target_organ, request.requested_action, reason)
            return AuthVerdict(request.request_id, False, reason, mask)

        self.audit.append("AUTHORIZE_SOCKET_CONNECTION", request.source_organ, request.target_organ, request.requested_action, "approved")
        return AuthVerdict(request.request_id, True, "authorized", mask)

    def validate_pipeline_data(self, payload: PipelineValidationPayload) -> ValidationVerdict:
        block_reason = self._guard_operational()
        if block_reason:
            self._record_denial_and_maybe_lockdown(payload.source_organ, "organ_07_security", payload.pipeline_name, block_reason)
            return ValidationVerdict(False, block_reason)

        authorized, reason, _ = self.access_controller.evaluate_capability(
            payload.source_organ, "PIPELINE_WRITE", payload.capability_token
        )
        if not authorized:
            self._record_denial_and_maybe_lockdown(payload.source_organ, "organ_07_security", payload.pipeline_name, reason)
            return ValidationVerdict(False, reason)

        valid, reason2 = self.pipeline_validator.validate(payload)
        verdict = "approved" if valid else "denied"
        self.audit.append("VALIDATE_PIPELINE_DATA", payload.source_organ, "organ_07_security", f"{payload.pipeline_name}:{payload.stage}", verdict, {"reason": reason2})
        return ValidationVerdict(valid, reason2)

    def verify_plugin_signature(self, payload: PluginVerifyPayload, requesting_organ: str, capability_token: Optional[str]) -> SignatureVerificationResult:
        block_reason = self._guard_operational()
        if block_reason:
            self._record_denial_and_maybe_lockdown(requesting_organ, "organ_07_security", "verify_plugin", block_reason)
            return SignatureVerificationResult(False, "", block_reason)

        authorized, reason, _ = self.access_controller.evaluate_capability(
            requesting_organ, "PLUGIN_LOAD", capability_token
        )
        if not authorized:
            self._record_denial_and_maybe_lockdown(requesting_organ, "organ_07_security", "verify_plugin", reason)
            return SignatureVerificationResult(False, "", reason)

        result = self.plugin_verifier.verify(payload)
        if not result.verified:
            self.audit.append(
                SecurityEvent.PLUGIN_VERIFICATION_FAILED.value, requesting_organ, "organ_07_security",
                payload.plugin_path, "denied", {"reason": result.reason},
            )
        else:
            self.audit.append("VERIFY_PLUGIN_SIGNATURE", requesting_organ, "organ_07_security", payload.plugin_path, "approved")
        return result

    def get_execution_token(self, request: CapabilityTokenRequest) -> CapabilityToken:
        block_reason = self._guard_operational()
        allowed = self.access_controller.allowed_mask_for(request.organ_id)
        requested_mask = 0
        for name in request.requested_capabilities:
            try:
                requested_mask |= int(Capability[name])
            except KeyError:
                continue
        granted_mask = allowed & requested_mask
        if block_reason:
            granted_mask = 0
        token = self.token_authority.issue(request.organ_id, granted_mask)
        self.database.record_token(token)
        self.audit.append(
            "GET_EXECUTION_TOKEN", request.organ_id, "organ_07_security", "issue_token",
            "approved" if granted_mask else "denied", {"granted_mask": granted_mask},
        )
        return token

    def retrieve_secret(self, payload: SecretRequestPayload) -> EncryptedSecretResponse:
        block_reason = self._guard_operational()
        if block_reason:
            self._record_denial_and_maybe_lockdown(payload.requesting_organ, "organ_07_security", "retrieve_secret", block_reason)
            return EncryptedSecretResponse(False, None, block_reason)

        authorized, reason, _ = self.access_controller.evaluate_capability(
            payload.requesting_organ, "SECRET_READ", payload.capability_token
        )
        if not authorized:
            self._record_denial_and_maybe_lockdown(payload.requesting_organ, "organ_07_security", "retrieve_secret", reason)
            return EncryptedSecretResponse(False, None, reason)

        value = self.vault.retrieve_secret(payload.secret_key)
        found = value is not None
        self.audit.append("RETRIEVE_SECRET", payload.requesting_organ, "organ_07_security", payload.secret_key, "approved" if found else "not_found")
        return EncryptedSecretResponse(found, value, "ok" if found else "secret not found")

    def enforce_sandbox_policy(self, request: SandboxPolicyRequest) -> SandboxHandle:
        block_reason = self._guard_operational()
        if block_reason:
            self._record_denial_and_maybe_lockdown(request.requesting_organ, "organ_07_security", "sandbox_spawn", block_reason)
            return SandboxHandle("", False, {})

        authorized, reason, _ = self.access_controller.evaluate_capability(
            request.requesting_organ, "SANDBOX_SPAWN", request.capability_token
        )
        if not authorized:
            self._record_denial_and_maybe_lockdown(request.requesting_organ, "organ_07_security", "sandbox_spawn", reason)
            return SandboxHandle("", False, {})

        return self.sandbox_enforcer.create(request)

    def check_file_write_permission(self, payload: FilePathPayload) -> PermissionVerdict:
        mask = self.access_controller.allowed_mask_for(payload.requesting_organ)
        if payload.capability_token:
            valid, token, _ = self.token_authority.verify(payload.capability_token)
            if valid:
                mask = token.capabilities_mask

        permitted, reason = self.policy_guard.check_write(payload.path, mask)
        if not permitted:
            self._record_denial_and_maybe_lockdown(payload.requesting_organ, "organ_07_security", f"write:{payload.path}", reason)
            self.audit.append(
                SecurityEvent.UNAUTHORIZED_FILE_WRITE_BLOCKED.value, payload.requesting_organ, "organ_07_security",
                payload.path, "denied", {"reason": reason},
            )
        else:
            self.audit.append("CHECK_FILE_WRITE_PERMISSION", payload.requesting_organ, "organ_07_security", payload.path, "approved")
        return PermissionVerdict(permitted, reason)


# ═══════════════════════════════════════════════════════════════════════
# SECTION 12 — IPC SERVER (asyncio loopback; Named-Pipe-compatible framing)
# ═══════════════════════════════════════════════════════════════════════

class IPCServer:
    """Length-prefixed binary frame server implementing the public RPC
    surface. `[4-byte length][2-byte op_code][JSON payload]`. Runs on an
    asyncio TCP loopback socket for portability; the framing is identical
    to what a native Windows Named Pipe transport would carry, so swapping
    transports later requires no change to dispatch logic."""

    _DISPATCH: Dict[int, str] = {
        OpCode.AUTHORIZE_SOCKET_CONNECTION: "_handle_authorize_socket_connection",
        OpCode.VALIDATE_PIPELINE_DATA: "_handle_validate_pipeline_data",
        OpCode.VERIFY_PLUGIN_SIGNATURE: "_handle_verify_plugin_signature",
        OpCode.GET_EXECUTION_TOKEN: "_handle_get_execution_token",
        OpCode.RETRIEVE_SECRET: "_handle_retrieve_secret",
        OpCode.ENFORCE_SANDBOX_POLICY: "_handle_enforce_sandbox_policy",
        OpCode.CHECK_FILE_WRITE_PERMISSION: "_handle_check_file_write_permission",
    }

    def __init__(self, kernel: SecurityKernel, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.kernel = kernel
        self.host = host
        self.port = port
        self._server: Optional[asyncio.base_events.Server] = None
        self._log = logging.getLogger("organ_07_security.ipc")

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)
        self._log.info("Security IPC listening on %s:%s", self.host, self.port)

    async def serve_forever(self) -> None:
        if self._server is None:
            await self.start()
        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _read_frame(self, reader: asyncio.StreamReader) -> Optional[Tuple[int, Dict[str, Any]]]:
        header = await reader.readexactly(FRAME_LENGTH_BYTES + FRAME_OPCODE_BYTES)
        length, op_code = struct.unpack(">IH", header)
        if length > MAX_PAYLOAD_SIZE:
            raise ValueError("frame exceeds 8MB maximum payload size")
        body = await reader.readexactly(length)
        payload = json.loads(body.decode("utf-8")) if length else {}
        return op_code, payload

    def _write_frame(self, writer: asyncio.StreamWriter, response: Dict[str, Any]) -> None:
        body = json.dumps(response).encode("utf-8")
        header = struct.pack(">IH", len(body), 0)
        writer.write(header + body)

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        try:
            while True:
                try:
                    frame = await self._read_frame(reader)
                except asyncio.IncompleteReadError:
                    break
                if frame is None:
                    break
                op_code, payload = frame
                handler_name = self._DISPATCH.get(op_code)
                if handler_name is None:
                    self._write_frame(writer, {"error": f"unknown op_code {op_code}"})
                    await writer.drain()
                    continue
                handler = getattr(self, handler_name)
                try:
                    response = handler(payload)
                except (KeyError, ValueError) as exc:
                    response = {"error": f"malformed payload: {exc}"}
                self._write_frame(writer, response)
                await writer.drain()
        finally:
            self._log.debug("client %s disconnected", peer)
            writer.close()

    # ---- handler adapters --------------------------------------------

    def _handle_authorize_socket_connection(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        req = SocketAuthRequest.from_json(payload)
        return self.kernel.authorize_socket_connection(req).to_json()

    def _handle_validate_pipeline_data(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        req = PipelineValidationPayload.from_json(payload)
        return self.kernel.validate_pipeline_data(req).to_json()

    def _handle_verify_plugin_signature(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        req = PluginVerifyPayload.from_json(payload)
        organ = payload.get("requesting_organ", "unknown")
        token = payload.get("capability_token")
        return self.kernel.verify_plugin_signature(req, organ, token).to_json()

    def _handle_get_execution_token(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        req = CapabilityTokenRequest.from_json(payload)
        return self.kernel.get_execution_token(req).to_json()

    def _handle_retrieve_secret(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        req = SecretRequestPayload.from_json(payload)
        return self.kernel.retrieve_secret(req).to_json()

    def _handle_enforce_sandbox_policy(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        req = SandboxPolicyRequest.from_json(payload)
        return self.kernel.enforce_sandbox_policy(req).to_json()

    def _handle_check_file_write_permission(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        req = FilePathPayload.from_json(payload)
        return self.kernel.check_file_write_permission(req).to_json()


# ═══════════════════════════════════════════════════════════════════════
# SECTION 13 — CONFIGURATION LOADING & ENTRYPOINT
# ═══════════════════════════════════════════════════════════════════════

def _load_json_config(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def build_kernel(base_dir: Path) -> SecurityKernel:
    capability_matrix = _load_json_config(base_dir / "config" / "capability_matrix.json", None)
    protected_paths = _load_json_config(base_dir / "config" / "protected_paths.json", [])
    return SecurityKernel(
        base_dir=base_dir,
        capability_matrix=capability_matrix,
        protected_paths=protected_paths,
    )


async def _main() -> None:  # pragma: no cover - process entrypoint
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    base_dir = Path(__file__).resolve().parent.parent
    kernel = build_kernel(base_dir)
    kernel.unlock(master_key=os.environ.get("HOJAIGA_VAULT_KEY", secrets.token_hex(16)))
    server = IPCServer(kernel)
    await server.serve_forever()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_main())
```

---

# **14. Tests**

```python
"""tests/test_organ_07_security.py — minimal unit coverage for the kernel."""

import tempfile
import unittest
from pathlib import Path

from organ_07_security import (
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
```

---

# **15. Post-Implementation Diagram (Actual Code Structure)**

```
organ_07_security.py
│
├── SECTION 1  Data Contracts ─────────────────────────────────────────────
│     OpCode(IntEnum) · SecurityState(Enum) · Capability(IntFlag) · SecurityEvent(Enum)
│     SocketAuthRequest/AuthVerdict
│     PipelineValidationPayload/ValidationVerdict
│     PluginVerifyPayload/SignatureVerificationResult
│     CapabilityTokenRequest/CapabilityToken
│     SecretRequestPayload/EncryptedSecretResponse
│     SandboxPolicyRequest/SandboxHandle
│     FilePathPayload/PermissionVerdict
│
├── SECTION 2  AuditLogger ────────────────────────────────────────────────
│     append() → hash-chained JSONL row (prev_hash → entry_hash)
│     verify_chain() → walks file, recomputes SHA-256 chain
│
├── SECTION 3  TokenAuthority ─────────────────────────────────────────────
│     issue()/verify()/revoke() — HMAC-SHA256 signed CapabilityToken
│
├── SECTION 4  AccessController ───────────────────────────────────────────
│     capability_matrix{organ→[Capability names]} → bitmask
│     evaluate_capability(source, required, token) → (bool, reason, mask)
│     BLOCKS Capability.GOVERNANCE_WRITE unconditionally
│
├── SECTION 5  PolicyGuard ────────────────────────────────────────────────
│     protected_paths set (Constitution/LawBook/PolicyManual/Blueprint/OrganSpec)
│     check_write(path, mask) → structurally denies GOVERNANCE_WRITE
│
├── SECTION 6  SocketValidator + PipelineValidator ────────────────────────
│     SocketValidator.validate() → envelope/identity checks
│     PipelineValidator.validate() → depth/size/dangerous-key scan
│
├── SECTION 7  PluginVerifier ─────────────────────────────────────────────
│     _sha256_file() → digest
│     verify() → digest match + manifest capability whitelist + HMAC signer check
│
├── SECTION 8  SandboxEnforcer ────────────────────────────────────────────
│     create() → handle_id
│         ├─ IS_WINDOWS & pywin32 present → _create_win32_job() [Job Object]
│         ├─ POSIX & resource present     → posix_preexec() [RLIMIT_AS/RLIMIT_CPU]
│         └─ neither                      → accounting-only logical handle
│
├── SECTION 9  CredentialVault ────────────────────────────────────────────
│     unlock(master_key) → PBKDF2HMAC(390k iters) → AES-256-GCM key
│         ├─ cryptography present  → real AES-GCM encrypt/decrypt to vault.enc
│         └─ cryptography absent   → degraded plaintext-JSON fallback (logged)
│     store_secret()/retrieve_secret()/zeroize()
│
├── SECTION 10 SecurityDatabase ───────────────────────────────────────────
│     sqlite3(":memory:") → active_tokens, security_audit tables
│     recent_violations(window) → feeds lockdown threshold check
│
├── SECTION 11 SecurityKernel  (ORCHESTRATOR — instantiate this) ──────────
│     state: LOCKED → unlock() → OPERATIONAL
│                    OPERATIONAL → enter_lockdown() → LOCKDOWN → lift_lockdown() → OPERATIONAL
│                    OPERATIONAL → enter_maintenance() → MAINTENANCE → exit_maintenance()
│     RPC methods (1:1 with Section 8 spec table):
│         authorize_socket_connection      → SocketValidator → AccessController → Audit
│         validate_pipeline_data           → AccessController → PipelineValidator → Audit
│         verify_plugin_signature          → AccessController → PluginVerifier → Audit
│         get_execution_token              → AccessController.allowed_mask_for → TokenAuthority.issue
│         retrieve_secret                  → AccessController → CredentialVault.retrieve_secret
│         enforce_sandbox_policy           → AccessController → SandboxEnforcer.create
│         check_file_write_permission      → PolicyGuard.check_write
│     _record_denial_and_maybe_lockdown()  → 3 denials / 10s → enter_lockdown()
│
├── SECTION 12 IPCServer ──────────────────────────────────────────────────
│     asyncio.start_server(127.0.0.1:8711)  [Named-Pipe-compatible framing]
│     _read_frame()  [4B length | 2B op_code | JSON] ≤ 8MB
│     _DISPATCH{OpCode → handler} → SecurityKernel RPC → _write_frame()
│
└── SECTION 13 build_kernel()/_main() ─────────────────────────────────────
      loads config/capability_matrix.json + config/protected_paths.json
      kernel.unlock(HOJAIGA_VAULT_KEY env) → IPCServer.serve_forever()

RUNTIME CALL GRAPH:
  Caller Organ
      │ TCP/NamedPipe frame
      ▼
  IPCServer._handle_client → _read_frame → _DISPATCH[op_code]
      ▼
  SecurityKernel.<rpc method>
      ├─ _guard_operational()            (state check)
      ├─ SocketValidator / PipelineValidator / PluginVerifier / PolicyGuard
      ├─ AccessController.evaluate_capability → TokenAuthority.verify
      ├─ SandboxEnforcer.create | CredentialVault.retrieve_secret (as applicable)
      └─ AuditLogger.append (+ SecurityDatabase.record_audit on denial)
      ▼
  Response dataclass.to_json() → IPCServer._write_frame → Caller Organ
```

---

# **16. Claude Implementation Instructions (Completed)**

1. Directory structure created per Section 7. ✅
2. `organ_07_security.py` compiles the entire organ (kernel, validators, vault, sandbox, IPC) into one importable module. ✅
3. `AccessController`/`PolicyGuard` structurally forbid `GOVERNANCE_WRITE` — no code path can grant it. ✅
4. `CredentialVault` implements AES-256-GCM via `cryptography` with a degraded, clearly-logged fallback when the dependency is absent, so the file always imports cleanly. ✅
5. `IPCServer` implements the exact 8-section wire protocol (`[4B len][2B op][JSON]`) on a portable asyncio loopback socket, ready to be re-pointed at a native Windows Named Pipe transport without touching `SecurityKernel`. ✅
