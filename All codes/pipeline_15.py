import sys
import os
import asyncio
import shutil
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'All codes')))

from observability.organ_16_audit_system import AuditSystem, AuditCategory, AuditSeverity, AuditRecordType, ActorIdentity
import core_organs.organ_02_cns_single_file as cns

async def run_pipeline():
    print("Starting pipeline 15: Organ 2 (CNS) -> Organ 16 (Audit System)")
    
    # 1. Initialize CNS
    kernel = cns.CNSKernel()
    await kernel.start()
    print("[CNS] Kernel started and listening.")

    # 2. Initialize Audit System
    storage_dir = "d:/new_automation/scratch_audit"
    archive_dir = "d:/new_automation/scratch_audit_archive"
    os.makedirs(storage_dir, exist_ok=True)
    os.makedirs(archive_dir, exist_ok=True)
    
    audit = AuditSystem(storage_dir=storage_dir, archive_dir=archive_dir)
    print("[Audit System] Facade initialized.")

    # 3. Simulate Connection via CNS Master Socket
    envelope = cns.EventEnvelope(
        topic="audit.ready",
        source_organ="16",
        payload={"status": "online"}
    )
    delivered = await kernel.event_bus.publish(envelope)
    print(f"[CNS] Event 'audit.ready' published to {delivered} subscribers.")

    # 4. Record a mock audit event
    actor = ActorIdentity(actor_id="admin-123", actor_type="SYSTEM")
    print("[Audit System] Recording async audit entry...")
    await audit.record_async(
        category=AuditCategory.CNS,
        severity=AuditSeverity.INFO,
        record_type=AuditRecordType.EVENT,
        source_organ="02",
        actor=actor,
        action="cns.bootstrap",
        summary="CNS completed initial event loop initialization",
        outcome="SUCCESS"
    )

    # 5. Verify integrity of recorded block
    report = audit.verify_integrity()
    print(f"[Audit System] Integrity check report: valid={report.valid}, count={report.verified_records}")

    # 6. Clean up directories & shutdown
    await kernel.shutdown()
    shutil.rmtree(storage_dir, ignore_errors=True)
    shutil.rmtree(archive_dir, ignore_errors=True)
    print("[Pipeline] Connection test successful.")

if __name__ == "__main__":
    # Modern Compliant Pattern (Python 3.11+)
    if sys.platform == "win32" and hasattr(asyncio, "ProactorEventLoop"):
        with asyncio.Runner(loop_factory=asyncio.ProactorEventLoop) as runner:
            runner.run(run_pipeline())
    else:
        asyncio.run(run_pipeline())
