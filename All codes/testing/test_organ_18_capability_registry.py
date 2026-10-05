"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 18
Name: Capability Registry

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Capability Registry]
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
Dependencies: core_organs.organ_18_capability_registry, unittest, uuid...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: test_organ_18_capability_registry.py]) --> output([Output Node])
```
"""

import uuid
import unittest

from core_organs.organ_18_capability_registry import (
    CapabilityRegistryCore,
    CapabilitySpecDTO,
    ProviderType,
    PermissionLevel,
    SearchQueryDTO,
    HealthStatus,
    UnresolvedCapabilityException,
    PerformanceMetrics,
)


def make_spec(name="automation.web.playwright.navigate", provider="organ.automation", version="2.4.1", **kw) -> CapabilitySpecDTO:
    defaults = dict(
        capability_name=name,
        description="Navigate a browser to a URL",
        provider=provider,
        provider_type=ProviderType.ORGAN,
        version=version,
        tags=["browser", "navigate"],
        category="Automation/Web",
        owner="organ.automation",
        permission_level=PermissionLevel.INTERNAL,
        permissions=[],
    )
    defaults.update(kw)
    return CapabilitySpecDTO(**defaults)


class CapabilityRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.core = CapabilityRegistryCore()

    def test_register_and_resolve(self):
        self.assertTrue(self.core.register(make_spec()))
        query = SearchQueryDTO(name="automation.web.playwright.navigate", caller_permissions=["automation:web:execute"])
        handle = self.core.process_query(query)
        self.assertEqual(handle.selected_version, "2.4.1")
        self.assertEqual(handle.provider_endpoint, "organ.automation::automation.web.playwright.navigate")

    def test_duplicate_registration_rejected(self):
        self.assertTrue(self.core.register(make_spec()))
        self.assertFalse(self.core.register(make_spec()))

    def test_reserved_namespace_rejected_without_key(self):
        spec = make_spec(name="kernel.boot.start", provider="rogue.plugin")
        self.assertFalse(self.core.register(spec))

    def test_reserved_namespace_allowed_with_trusted_key(self):
        spec = make_spec(name="kernel.boot.start", provider="kernel.core", provider_secret_key="hojaiga-root-key")
        self.assertTrue(self.core.register(spec))

    def test_deregister_tombstones_capability(self):
        spec = make_spec()
        self.core.register(spec)
        self.assertTrue(self.core.deregister(spec.capability_id, ""))
        query = SearchQueryDTO(name=spec.capability_name)
        with self.assertRaises(UnresolvedCapabilityException):
            self.core.process_query(query)

    def test_unresolved_capability_raises(self):
        with self.assertRaises(UnresolvedCapabilityException):
            self.core.process_query(SearchQueryDTO(name="nonexistent.capability"))

    def test_ranking_prefers_healthier_provider(self):
        spec_a = make_spec(provider="provider.a", version="1.0.0", performance_metrics=PerformanceMetrics(p95_latency_ms=2.0))
        spec_b = make_spec(provider="provider.b", version="1.0.0", performance_metrics=PerformanceMetrics(p95_latency_ms=2.0))
        self.core.register(spec_a)
        self.core.register(spec_b)
        rec_b = self.core.db.lookup_by_name(spec_b.capability_name)[1]
        self.core.db.update(rec_b.capability_id, health_status=HealthStatus.UNHEALTHY)
        handle = self.core.process_query(SearchQueryDTO(name=spec_a.capability_name, required_health=(HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY)))
        self.assertEqual(handle.provider_endpoint.split("::")[0], "provider.a")

    def test_user_pin_affects_ranking(self):
        spec_a = make_spec(provider="provider.a", version="1.0.0")
        spec_b = make_spec(provider="provider.b", version="1.0.0")
        self.core.register(spec_a)
        self.core.register(spec_b)
        self.core.pin_provider("provider.b")
        handle = self.core.process_query(SearchQueryDTO(name=spec_a.capability_name))
        self.assertEqual(handle.provider_endpoint.split("::")[0], "provider.b")

    def test_cache_hit_returns_same_handle(self):
        self.core.register(make_spec())
        query = SearchQueryDTO(name="automation.web.playwright.navigate")
        h1 = self.core.process_query(query)
        h2 = self.core.process_query(query)
        self.assertEqual(h1.auth_token, h2.auth_token)

    def test_fallback_resolution(self):
        self.core.register(make_spec(name="automation.web.fallback.navigate", provider="organ.fallback"))
        handle = self.core.resolve_with_fallback(
            SearchQueryDTO(name="automation.web.primary.navigate"),
            fallback_names=["automation.web.fallback.navigate"],
        )
        self.assertEqual(handle.capability_name, "automation.web.fallback.navigate")

    def test_capability_alias_resolution(self):
        self.core.register(make_spec(name="media.screen_recording", provider="organ.media"))
        self.core.capability_alias.add_alias("record screen", "media.screen_recording")
        
        query = SearchQueryDTO(name="record screen")
        handle = self.core.process_query(query)
        self.assertEqual(handle.capability_name, "media.screen_recording")

    def test_application_alias_resolution(self):
        self.core.register(make_spec(name="app.local.obs_studio", provider="OBS", provider_type=ProviderType.APPLICATION))
        self.core.application_alias.add_alias("obs", "app.local.obs_studio")
        
        query = SearchQueryDTO(name="obs")
        handle = self.core.process_query(query)
        self.assertEqual(handle.capability_name, "app.local.obs_studio")


    def test_permission_denied_excludes_provider(self):
        spec = make_spec(permission_level=PermissionLevel.GOVERNANCE)
        self.core.register(spec)
        with self.assertRaises(UnresolvedCapabilityException):
            self.core.process_query(SearchQueryDTO(name=spec.capability_name, caller_scope=PermissionLevel.PUBLIC))

    def test_audit_chain_verifiable(self):
        self.core.register(make_spec())
        self.assertTrue(self.core.audit.verify_chain())

    def test_recovery_pipeline_clears_cache(self):
        self.core.register(make_spec())
        self.core.process_query(SearchQueryDTO(name="automation.web.playwright.navigate"))
        result = self.core.recover()
        self.assertTrue(result["cache_cleared"])

    def test_dependency_gate_blocks_resolution(self):
        spec = make_spec(name="automation.web.dependent.action", dependencies=["automation.web.missing.dependency"])
        self.core.register(spec)
        with self.assertRaises(UnresolvedCapabilityException):
            self.core.process_query(SearchQueryDTO(name=spec.capability_name))


if __name__ == "__main__":
    unittest.main()
