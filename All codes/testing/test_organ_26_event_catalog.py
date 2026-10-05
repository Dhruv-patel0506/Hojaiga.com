"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 26
Name: Event Catalog

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Event Catalog]
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
Dependencies: pytest, asyncio, core_organs.organ_26_event_catalog...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: test_organ_26_event_catalog.py]) --> output([Output Node])
```
"""

import asyncio
import pytest  # type: ignore

from core_organs.organ_26_event_catalog import (
    EventCatalog, EventManifest, EventCategory, EventPriority,
    PermissionLevel, SecurityClassification,
)


@pytest.fixture
def catalog() -> EventCatalog:
    cat = EventCatalog()
    cat.register_event(EventManifest(
        eventName="PLAYWRIGHT.PAGE.LOADED",
        category=EventCategory.PLAYWRIGHT,
        description="Fires when a page finishes loading.",
        payloadSchema={"required": ["url"], "properties": {"url": {"type": "string"}},
                       "additionalProperties": False},
        allowedProducers={"browser_runtime"},
        allowedConsumers={"execution_controller", "verification_engine"},
    ))
    return cat


def test_registration_rejects_duplicates(catalog: EventCatalog):
    with pytest.raises(ValueError):
        catalog.register_event(EventManifest(
            eventName="PLAYWRIGHT.PAGE.LOADED", category=EventCategory.PLAYWRIGHT,
            description="dup", payloadSchema={}, allowedProducers=set(), allowedConsumers=set(),
        ))


def test_registration_rejects_bad_name(catalog: EventCatalog):
    with pytest.raises(ValueError):
        catalog.register_event(EventManifest(
            eventName="bad-name", category=EventCategory.PLAYWRIGHT,
            description="x", payloadSchema={}, allowedProducers=set(), allowedConsumers=set(),
        ))


def test_build_envelope_unregistered_raises(catalog: EventCatalog):
    with pytest.raises(ValueError):
        catalog.build_envelope(event_name="NOT.REGISTERED", producer="x", consumer=[], payload={})


@pytest.mark.asyncio
async def test_publish_valid_event_delivers(catalog: EventCatalog):
    received = []

    async def handler(event):
        received.append(event)

    catalog.subscribe("PLAYWRIGHT.PAGE.LOADED", handler)
    envelope = catalog.build_envelope(
        event_name="PLAYWRIGHT.PAGE.LOADED", producer="browser_runtime",
        consumer=["execution_controller"], payload={"url": "https://example.com"},
    )
    result = await catalog.publish(envelope)
    assert result.valid
    assert len(received) == 1
    assert catalog.get_metrics()["delivered"] == 1


@pytest.mark.asyncio
async def test_publish_invalid_payload_goes_to_dlq(catalog: EventCatalog):
    envelope = catalog.build_envelope(
        event_name="PLAYWRIGHT.PAGE.LOADED", producer="browser_runtime",
        consumer=["execution_controller"], payload={"wrong_field": 1},
    )
    result = await catalog.publish(envelope)
    assert not result.valid
    assert catalog.get_metrics()["rejected"] == 1
    assert len(catalog.history.dlq_snapshot()) == 1


@pytest.mark.asyncio
async def test_publish_unauthorized_producer_rejected(catalog: EventCatalog):
    envelope = catalog.build_envelope(
        event_name="PLAYWRIGHT.PAGE.LOADED", producer="untrusted_plugin",
        consumer=["execution_controller"], payload={"url": "https://example.com"},
    )
    result = await catalog.publish(envelope)
    assert not result.valid
    assert any("not authorized" in e for e in result.errors)


@pytest.mark.asyncio
async def test_replay_by_correlation_id(catalog: EventCatalog):
    envelope = catalog.build_envelope(
        event_name="PLAYWRIGHT.PAGE.LOADED", producer="browser_runtime",
        consumer=["execution_controller"], payload={"url": "https://example.com"},
    )
    await catalog.publish(envelope)
    replayed = catalog.replay(correlation_id=envelope.correlationId)
    assert len(replayed) >= 1
    assert replayed[0].correlationId == envelope.correlationId


@pytest.mark.asyncio
async def test_recovery_manager_replays_dlq_once_fixed(catalog: EventCatalog):
    bad_envelope = catalog.build_envelope(
        event_name="PLAYWRIGHT.PAGE.LOADED", producer="browser_runtime",
        consumer=["execution_controller"], payload={"wrong_field": 1},
    )
    await catalog.publish(bad_envelope)
    replayed_count = await catalog.recovery.replay_dlq()
    assert replayed_count == 0  # still invalid, remains poisoned


def test_wildcard_subscription_matches_category():
    catalog = EventCatalog()
    catalog.register_event(EventManifest(
        eventName="SYSTEM.BOOT.STARTED", category=EventCategory.SYSTEM,
        description="boot started", payloadSchema={"required": [], "properties": {}},
        allowedProducers=set(), allowedConsumers=set(),
    ))
    received = []

    async def handler(event):
        received.append(event)

    catalog.subscribe("SYSTEM.*", handler)
    envelope = catalog.build_envelope(
        event_name="SYSTEM.BOOT.STARTED", producer="kernel", consumer=[], payload={},
    )
    asyncio.run(catalog.publish(envelope))
    assert len(received) == 1


def test_bootstrap_events_preregistered():
    catalog = EventCatalog()
    assert catalog.registry.exists("SYSTEM.CRASHED")
    assert catalog.registry.exists("SECURITY.ALERT")
