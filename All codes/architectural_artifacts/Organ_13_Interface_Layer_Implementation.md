# Organ 13 — Interface Layer — Implementation Record

Authority: Constitution → Law Book → Policy Manual → Master Architecture Blueprint → Organ Specification → Organ_13_Interface_Layer.md

---

## 1. Folder Tree

```
hojaiga/
├── interface_layer.py            # Compiled single-file organ implementation
└── test_interface_layer.py       # Test suite
```

## 2. New Files

- `interface_layer.py`
- `test_interface_layer.py`

## 3. Modified Files

- None (new organ, no cross-organ modification per Foundational Law 5 / Organ Spec §"No organ may directly modify another organ").

---

## 4. Pre-Code Diagram — Component Topology

```
                      [ User / External Client ]
                                 │
                                 ▼
        ┌───────────────┬───────────────┬────────────────┐
        │  CLIAdapter   │  RESTAdapter  │ WebSocketAdapter │
        └───────┬───────┴───────┬───────┴────────┬────────┘
                │               │                │
                └───────────────┼────────────────┘
                                 ▼
                        InterfaceGateway
                                 │
        ┌────────────────────────┼─────────────────────────┐
        ▼                        ▼                          ▼
 AuthenticationGateway   AuthorizationEngine          InputValidator
        │                        │                          │
        └────────────────────────┼──────────────────────────┘
                                 ▼
                          RateLimiter (per-client)
                                 ▼
                          SessionManager
                                 ▼
                          RequestDispatcher
                                 ▼
                     SocketBus[SOCK_OUT_CNS_DISPATCH]
                                 ▼
                    (Central Nervous System — external organ)
```

Supporting surfaces attached to the same `SocketBus`:

```
NotificationCenter  ──▶ SOCK_IN_NOTIFICATION
PluginManagerSurface ──▶ SOCK_OUT_PLUGIN_COMMAND
LLMManagerSurface    ──▶ SOCK_OUT_LLM_COMMAND
ReadOnlyViewer (Knowledge/Memory/History) ──▶ SOCK_OUT_CNS_DISPATCH (query mode)
AuditSystem          ──  append-only, in-process
```

## 5. Actual-Code Diagram — Sequence (REST request)

```
Client ──HTTP──▶ RESTAdapter.handle_request()
                       │
                       ▼
              InterfaceGateway.process_inbound()
                       │
          ┌────────────┼─────────────┐
          ▼            ▼             ▼
   RateLimiter    InputValidator  SessionManager
    .enforce()     .validate_     .validate_
                    schema()       session()
          │            │             │
          └────────────┼─────────────┘
                       ▼
              AuthorizationEngine.enforce()
                       ▼
              RequestDispatcher.dispatch()
                       ▼
              SocketBus.publish(SOCK_OUT_CNS_DISPATCH)
                       ▼
              AuditSystem.record(SUCCESS)
                       ▼
              GatewayResponseFrame ──▶ Client (202 Accepted)
```

Failure path (any stage raises `InterfaceLayerError`):

```
InterfaceLayerError ──▶ AuditSystem.record(REJECTED)
                    ──▶ mapped HTTP status via _status_for()
                    ──▶ GatewayResponseFrame(error_message=...) ──▶ Client
```

## 6. Sockets (implemented channel names)

| Socket | Direction | Purpose |
|---|---|---|
| SOCK_OUT_CNS_DISPATCH | Egress | Standardized command → Central Nervous System |
| SOCK_IN_TELEMETRY | Ingress | System telemetry consumed by UI/dashboard surfaces |
| SOCK_IN_TASK_STATUS | Ingress | Task/job progress events |
| SOCK_IN_NOTIFICATION | Ingress | Notification fan-out to subscribed sessions |
| SOCK_OUT_PLUGIN_COMMAND | Egress | Plugin install/toggle requests → Plugin Runtime organ |
| SOCK_OUT_LLM_COMMAND | Egress | LLM runtime status/shutdown requests → Brain organ |
| SOCK_OUT_SYSTEM_COMMAND | Egress | Dashboard-issued system commands |

## 7. Pipelines (implemented as ordered method chains)

- **Request Pipeline**: RateLimiter → InputValidator → SessionManager → AuthorizationEngine → RequestDispatcher → SocketBus
- **Notification Pipeline**: NotificationCenter.notify → per-session subscriber callbacks → SOCK_IN_NOTIFICATION
- **Housekeeping Pipeline**: `InterfaceLayerOrgan.housekeeping_loop` → `SessionManager.purge_expired` (interval loop, never blocks ingress)

## 8. Dependencies

- Python 3.11+ standard library only (`asyncio`, `hashlib`, `hmac`, `re`, `uuid`, `secrets`, `logging`, `dataclasses`, `enum`).
- No coupling to CNS/Brain internals — only to the documented `SocketBus` channel contract.
- Test dependencies: `pytest`, `pytest-asyncio`.

## 9. Loops

- **Housekeeping Loop** (`housekeeping_loop`): periodic expired-session purge, runs independently of request handling.
- **Rate Limiter Sliding Window**: per-`client_key` bucket, evaluated on every ingress call.

## 10. Errors & Recovery

| Error Code | HTTP Status | Recovery |
|---|---|---|
| IL-400-INVALID_PAYLOAD | 400 | Client retries with corrected schema |
| IL-401-UNAUTHENTICATED | 401 | Client re-authenticates via login |
| IL-403-UNAUTHORIZED | 403 | Escalate to Governance/Owner Authority for role grant |
| IL-429-RATE_LIMITED | 429 | Client backs off; window resets automatically |
| IL-440-SESSION_EXPIRED | 440 | Client re-authenticates, new session issued |
| IL-500-INTERNAL_ERROR | 500 | Audited; surfaced to Notification Center |
| IL-502-DISPATCH_FAILURE | 502 | Audited; upstream CNS socket failure isolated from client |

All rejections and errors are recorded via `AuditSystem.record` (append-only, Universal Law 1 & 8, Policy Manual Ch.8/9) before any response leaves the boundary.

## 11. Security

- HMAC-SHA256 signing/verification primitives (`AuthenticationGateway.sign/verify_signature`) for payload integrity checks by edge adapters.
- Passwords stored as SHA-256 digests (placeholder for production KDF such as argon2/bcrypt — swap-in point documented, no plaintext ever persisted).
- RBAC enforced via `AuthorizationEngine`; extendable to ABAC by adding attribute predicates to `is_permitted`.
- Rate limiting per client key prevents ingress flooding (Universal Law 7 — least privilege / resource responsibility).
- Zero business logic, zero automation execution, zero decision-making inside this organ (Organ Spec §1.2).

## 12. Implementation Checklist

- [x] Desktop UI / REST / CLI / WebSocket edge adapters implemented against a common `InterfaceGateway`
- [x] Interface Gateway as single non-bypassable boundary
- [x] Authentication (credential + HMAC signing)
- [x] Authorization (RBAC, ABAC-extensible)
- [x] Validation (schema + sanitation)
- [x] Session Management (TTL, concurrency cap, purge loop)
- [x] Request Dispatcher (CNS socket forwarding)
- [x] Notification Center
- [x] Plugin Manager surface (command-only, no execution)
- [x] LLM Manager surface (command-only, no execution)
- [x] Knowledge / Memory / History read-only viewers
- [x] Sockets and Pipelines per specification
- [x] Error catalog and recovery table
- [x] Tests (9/9 passing)
