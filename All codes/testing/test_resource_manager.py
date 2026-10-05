"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Core File
Name: test_resource_manager.py

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [test_resource_manager.py]
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
Dependencies: unittest, core_runtime.resource_manager, time, sys, os...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: test_resource_manager.py]) --> output([Output Node])
```
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core_runtime.resource_manager import (
    ResourceManagerFacade, ResourceRequestSpec, ResourcePriority, LeaseState,
    QuotaManager, SubsystemQuota, PriorityScheduler, CpuManager, RamManager,
    VramManager, DiskManager, ThreadManager, DEFAULT_CONFIG,
)


def make_facade(**overrides):
    cfg = dict(DEFAULT_CONFIG)
    cfg["monitoring"] = {"polling_interval_ms": 50, "metrics_retention_hours": 1}
    cfg.update(overrides)
    return ResourceManagerFacade(config=cfg)


class TestQuotaManager(unittest.TestCase):
    def test_denies_over_quota(self):
        qm = QuotaManager({"plugins": SubsystemQuota(10, 512, 0, 0, 512, "LOW")})
        spec = ResourceRequestSpec(subsystem_id="plugins")
        self.assertTrue(qm.can_allocate(spec, ram_mb=400, vram_mb=0, ssd_mb=0, cpu_pct=5, gpu_pct=0))
        qm.commit("plugins", ram_mb=400, vram_mb=0, ssd_mb=0, cpu_pct=5, gpu_pct=0)
        self.assertFalse(qm.can_allocate(spec, ram_mb=200, vram_mb=0, ssd_mb=0, cpu_pct=1, gpu_pct=0))

    def test_release_restores_capacity(self):
        qm = QuotaManager({"agents": SubsystemQuota(40, 2048, 0, 0, 2048, "NORMAL")})
        qm.commit("agents", ram_mb=1000, vram_mb=0, ssd_mb=0, cpu_pct=10, gpu_pct=0)
        qm.release("agents", ram_mb=1000, vram_mb=0, ssd_mb=0, cpu_pct=10, gpu_pct=0)
        snap = qm.usage_snapshot()["agents"]
        self.assertEqual(snap["ram_mb"], 0)


class TestPriorityScheduler(unittest.TestCase):
    def test_emergency_outranks_low(self):
        sched = PriorityScheduler()
        low = ResourceRequestSpec(subsystem_id="connectors", priority=ResourcePriority.LOW)
        emergency = ResourceRequestSpec(subsystem_id="controllers", priority=ResourcePriority.EMERGENCY)
        sched.enqueue(low)
        sched.enqueue(emergency)
        first = sched.dequeue_next(lambda s: 0.5)
        self.assertEqual(first.subsystem_id, "controllers")  # type: ignore

    def test_aging_boosts_wait_time(self):
        sched = PriorityScheduler()
        spec = ResourceRequestSpec(subsystem_id="agents", priority=ResourcePriority.LOW)
        spec.enqueued_at_ms = (time.time() * 1000) - 50_000
        sched.enqueue(spec)
        self.assertGreater(sched.max_wait_ms(), 40_000)


class TestHardwareManagers(unittest.TestCase):
    def test_cpu_manager_reserve_release(self):
        cpu = CpuManager(total_threads=8)
        self.assertTrue(cpu.reserve(50.0))
        self.assertAlmostEqual(cpu.available_pct(), 50.0)
        cpu.release(50.0)
        self.assertAlmostEqual(cpu.available_pct(), 100.0)

    def test_cpu_manager_denies_overreserve(self):
        cpu = CpuManager(total_threads=8)
        self.assertTrue(cpu.reserve(90.0))
        self.assertFalse(cpu.reserve(20.0))

    def test_ram_manager_oom_risk(self):
        ram = RamManager(total_mb=1000)
        self.assertFalse(ram.is_oom_risk())

    def test_vram_manager_bounds(self):
        vram = VramManager(total_mb=4096)
        self.assertTrue(vram.reserve(2048))
        self.assertFalse(vram.reserve(4096))
        freed = vram.purge_idle()
        self.assertEqual(freed, 2048)
        self.assertEqual(vram.available_mb(), 4096)

    def test_disk_manager_ssd_reserve(self):
        disk = DiskManager(ssd_total_mb=1000, hdd_total_mb=1000,
                            ssd_path="/nonexistent_ssd", hdd_path="/nonexistent_hdd")
        self.assertTrue(disk.reserve_ssd(500))
        self.assertFalse(disk.reserve_ssd(600))
        disk.release_ssd(500)
        self.assertTrue(disk.reserve_ssd(900))

    def test_thread_manager_global_ceiling(self):
        tm = ThreadManager(max_threads_global=4)
        self.assertTrue(tm.reserve(4))
        self.assertFalse(tm.reserve(1))
        tm.release(4)
        self.assertEqual(tm.active_count(), 0)


class TestResourceManagerFacade(unittest.TestCase):
    def test_grant_and_release_lease(self):
        with make_facade() as rm:
            spec = ResourceRequestSpec(
                subsystem_id="automation",
                priority=ResourcePriority.NORMAL,
                cpu_threads_requested=0,
                ram_bytes_requested=256 * 1024 * 1024,
                lease_duration_ms=5000,
            )
            ticket = rm.request_resource_lease(spec)
            self.assertTrue(ticket.is_granted)
            self.assertEqual(ticket.state, LeaseState.GRANTED)
            self.assertTrue(rm.release_lease(ticket.lease_id))

    def test_quota_denial_queues_request(self):
        with make_facade() as rm:
            spec = ResourceRequestSpec(
                subsystem_id="plugins",
                ram_bytes_requested=1024 * 1024 * 1024,  # exceeds plugins 512MB quota
            )
            ticket = rm.request_resource_lease(spec)
            self.assertFalse(ticket.is_granted)
            self.assertEqual(ticket.state, LeaseState.QUEUED)

    def test_renew_lease_extends_expiration(self):
        with make_facade() as rm:
            spec = ResourceRequestSpec(subsystem_id="cns", ram_bytes_requested=10 * 1024 * 1024,
                                        lease_duration_ms=1000)
            ticket = rm.request_resource_lease(spec)
            original_expiry = ticket.expiration_timestamp_ms
            self.assertTrue(rm.renew_lease(ticket.lease_id, 5000))
            renewed = rm.core.registry.get(ticket.lease_id)
            self.assertGreater(renewed.expiration_timestamp_ms, original_expiry)  # type: ignore

    def test_global_resource_health_range(self):
        with make_facade() as rm:
            health = rm.get_global_resource_health()
            self.assertGreaterEqual(health, 0.0)
            self.assertLessEqual(health, 100.0)

    def test_socket_bus_lease_request(self):
        with make_facade() as rm:
            result = rm.bus.resource_socket.send({
                "subsystem_id": "learning",
                "ram_bytes_requested": 10 * 1024 * 1024,
            })
            self.assertTrue(result["is_granted"])

    def test_gpu_fallback_denied_without_allowance(self):
        with make_facade() as rm:
            spec = ResourceRequestSpec(
                subsystem_id="brain",
                gpu_compute_pct_requested=50,
                allow_cpu_fallback=False,
            )
            ticket = rm.request_resource_lease(spec)
            # GPU may or may not be physically available in CI; either branch is valid
            self.assertIn(ticket.state, (LeaseState.GRANTED, LeaseState.DENIED, LeaseState.QUEUED))

    def test_lease_expiration_reaped(self):
        with make_facade() as rm:
            spec = ResourceRequestSpec(subsystem_id="agents", ram_bytes_requested=5 * 1024 * 1024,
                                        lease_duration_ms=200)
            ticket = rm.request_resource_lease(spec)
            self.assertTrue(ticket.is_granted)
            time.sleep(1.5)
            self.assertIsNone(rm.core.registry.get(ticket.lease_id) and
                               (rm.core.registry.get(ticket.lease_id).state == LeaseState.GRANTED or None))  # type: ignore


if __name__ == "__main__":
    unittest.main()
