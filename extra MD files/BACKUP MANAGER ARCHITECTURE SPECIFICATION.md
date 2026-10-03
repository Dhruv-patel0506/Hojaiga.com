# **BACKUP MANAGER ARCHITECTURE SPECIFICATION**

## **1\. PURPOSE**

The Backup Manager is the exclusive, authoritative system component responsible for creating, validating, storing, managing, and cataloging system backups and restore points for the Hojaiga Automation Operating System (AOS).

The Backup Manager operates strictly within the boundary of backup creation, preservation, and verification. It strictly delegates all restoration and disaster recovery procedures to the **Recovery Manager**. It acts on triggers from the **Update Manager** (for pre-update snapshots) and supplies verified backup payload paths to the **Recovery Manager** when requested.

## **2\. HIGH LEVEL ARCHITECTURE**

**System Integration Flow**

Plaintext  
Update Manager  
      │  
      ▼ (Requests Pre-Update Backup)  
Backup Manager ──────────┐  
      │                  │  
Create Restore Point     │ (Verification & Storage)  
      │                  │  
      ▼                  ▼  
Package Manager     Recovery Manager (Invoked on failure)  
      │  
      ▼  
Verification

**Internal Core Flow**

Plaintext  
System Components  
      ↓  
Backup Manager  
      ↓  
Backup Planner  
      ↓  
Snapshot Engine  
      ↓  
Compression Engine  
      ↓  
Encryption Engine  
      ↓  
Integrity Verification  
      ↓  
Backup Catalog  
      ↓  
Backup Storage  
      ↓  
Recovery Manager (Read-Only access to payloads)

## **3\. RESPONSIBILITIES**

* Create full backups, incremental backups, and differential backups.  
* Generate instantaneous restore points triggered by systemic changes.  
* Verify backup integrity through cryptographic hashing and simulated mounting.  
* Compress backup data utilizing configurable algorithms (LZ4, ZSTD, gzip).  
* Encrypt backup data at rest via AES-256-GCM.  
* Maintain an immutable, queryable Backup Catalog.  
* Manage retention policies, auto-cleaning, and rotation rules.  
* Export and import backups securely across system boundaries.  
* Support local, external, offline, and network storage targets.  
* Prevent corrupted backups from being registered in the Catalog.  
* Generate structured backup reports, metrics, and audit trails.

## **4\. BACKUP TYPES**

The Backup Manager inherently supports the following execution profiles:

| Backup Type | Definition |
| :---- | :---- |
| **Full Backup** | Complete byte-for-byte or file-level copy of the targeted volume/dataset. |
| **Incremental Backup** | Delta of changes strictly since the last backup of any type. |
| **Differential Backup** | Delta of changes strictly since the last Full Backup. |
| **Restore Point** | Instantaneous, read-only snapshot generated prior to state-altering operations. |
| **Configuration Backup** | Isolated backup of system configuration files (/etc, YAML/JSON matrices). |
| **Workflow Backup** | Isolated backup of automation workflows and state machines. |
| **Knowledge Backup** | Backup of semantic databases, vector stores, and structured knowledge bases. |
| **Memory Backup** | Snapshot of active agentic memory arrays and conversational states. |
| **Package Backup** | Archive of installed binaries, libraries, and their manifest states. |
| **Plugin Backup** | Snapshot of active plugins and their localized configurations. |
| **Connector Backup** | Archive of third-party API connectors, credentials (encrypted), and schemas. |
| **LLM Runtime Backup** | Snapshot of prompt templates, custom weights (LoRA), and inference configs. |
| **System Snapshot** | Full OS-level atomic snapshot via underlying filesystem (e.g., BTRFS/ZFS). |
| **Emergency Snapshot** | Unscheduled, high-priority snapshot triggered by anomaly detection systems. |
| **Manual Backup** | User-triggered backup execution with custom parameters. |
| **Scheduled Backup** | CRON-driven execution based on Backup Scheduler policies. |
| **Cold Backup** | Backup taken while the target subsystems are halted to guarantee consistency. |
| **Hot Backup** | Backup taken while the system is active, utilizing VSS/LVM/BTRFS snapshotting. |

## **5\. STORAGE TARGETS**

Supported destinations for backup payloads:

* **Local SSD:** Primary, high-speed NVMe/SATA storage for immediate restore points.  
* **External HDD:** USB-attached sequential storage for large-capacity archiving.  
* **External SSD:** High-speed portable media for exported encrypted archives.  
* **NAS:** Network Attached Storage via NFS/SMB/iSCSI protocols.  
* **Network Share:** Local subnet shared folders for distributed redundancy.  
* **Offline Archive:** Removable media (LTO tape, disconnected drives) for air-gapped security.  
* **Encrypted Archive:** Logical targets requiring key-pair unlocking prior to write/read.  
* **Future Cloud Storage:** Abstraction layer prepared for S3, Azure Blob, and GCS integrations.

## **6\. BACKUP METADATA**

Every backup registered in the Backup Catalog must contain the following strict schema:

* **Backup ID:** UUIDv4 unique identifier.  
* **Backup Name:** Human-readable nomenclature (e.g., pre-update-v2.1.4).  
* **Backup Type:** Enum mapped to Backup Types (Section 4).  
* **Creation Time:** ISO 8601 UTC timestamp.  
* **Creator:** Triggering entity (System, Admin User, Update Manager, Schedule).  
* **System Version:** AOS version at the time of backup.  
* **Configuration Version:** Hash of the configuration state.  
* **Package Version:** Hash of the package manifest.  
* **Workflow Version:** Hash of the active workflow repository.  
* **Knowledge Version:** Timestamp/Hash of the knowledge base state.  
* **Compression Method:** Algorithm used (None, LZ4, ZSTD).  
* **Encryption Method:** Cipher suite used (None, AES-256-GCM, ChaCha20).  
* **Checksum:** Cryptographic hash of the unencrypted payload (SHA-256).  
* **Hash:** Cryptographic hash of the final stored payload/file (SHA-384).  
* **Storage Location:** URI of the backup target (e.g., local:///mnt/backups/vol1).  
* **Size:** Integer byte count.  
* **Retention Policy:** Assigned rule (Daily, Permanent, etc.).  
* **Expiration Date:** ISO 8601 UTC timestamp for automated pruning (Null for Permanent).  
* **Verification Status:** Enum (PENDING, VERIFIED, CORRUPTED).  
* **Documentation Reference:** URL/Path to generation logs and audit trails.

## **7\. BACKUP MODULES**

### **7.1 Backup Core**

* **Purpose:** Central orchestrator for the Backup Manager ecosystem.  
* **Responsibilities:** Route requests, manage module lifecycles, enforce inter-module sequence.  
* **Inputs:** Internal method calls from Sockets.  
* **Outputs:** Orchestration commands to child engines.  
* **Dependencies:** Configuration Interface, Audit Manager.  
* **Sockets:** Backup Socket.  
* **Pipelines:** Backup Request Pipeline.  
* **Failure Modes:** Core panic, thread exhaustion.  
* **Recovery:** Service restart via AOS Watchdog; state reconstruction from Catalog.  
* **Future Expansion:** Distributed multi-node orchestration.

### **7.2 Backup Planner**

* **Purpose:** Determine the optimal execution strategy for a given backup request.  
* **Responsibilities:** Calculate deltas, determine hot/cold status, map dependencies.  
* **Inputs:** Backup Request metadata, Current System State.  
* **Outputs:** Backup Execution Plan (JSON).  
* **Dependencies:** Storage Manager, Metadata Manager.  
* **Sockets:** None.  
* **Pipelines:** Backup Request Pipeline.  
* **Failure Modes:** Dependency resolution failure, path not found.  
* **Recovery:** Abort and log; fallback to Full Backup strategy.  
* **Future Expansion:** ML-driven predictive planning based on system I/O load.

### **7.3 Snapshot Engine**

* **Purpose:** Capture atomic point-in-time state of the filesystem or dataset.  
* **Responsibilities:** Quiesce I/O, execute filesystem snapshot (BTRFS/LVM), release I/O.  
* **Inputs:** Execution Plan.  
* **Outputs:** Path to frozen Snapshot.  
* **Dependencies:** Underlying OS filesystem utilities.  
* **Sockets:** Snapshot Socket.  
* **Pipelines:** Snapshot Pipeline.  
* **Failure Modes:** Filesystem lock failure, insufficient space.  
* **Recovery:** Timeout and release I/O locks, trigger Emergency Storage Alert.  
* **Future Expansion:** Application-aware snapshotting (VSS equivalent).

### **7.4 Backup Scheduler**

* **Purpose:** Execute time-based or event-based backup jobs.  
* **Responsibilities:** Parse CRON expressions, manage job queues, trigger Backup Core.  
* **Inputs:** Configuration schedules, Time signals.  
* **Outputs:** Job execution triggers.  
* **Dependencies:** AOS Time Service, Configuration Interface.  
* **Sockets:** None.  
* **Pipelines:** Backup Request Pipeline.  
* **Failure Modes:** Missed triggers due to system sleep/halt.  
* **Recovery:** Execute missed jobs immediately upon wake if within threshold.  
* **Future Expansion:** Dynamic scheduling based on system idle times.

### **7.5 Compression Manager**

* **Purpose:** Reduce physical footprint of backup payloads.  
* **Responsibilities:** Stream data through compression algorithms, verify output integrity.  
* **Inputs:** Raw Snapshot Data Stream.  
* **Outputs:** Compressed Data Stream.  
* **Dependencies:** Multi-core processing units.  
* **Sockets:** Compression Socket.  
* **Pipelines:** Compression Pipeline.  
* **Failure Modes:** Memory exhaustion, CPU thermal throttling.  
* **Recovery:** Graceful degradation to lower compression ratio or None.  
* **Future Expansion:** Hardware-accelerated compression (QAT).

### **7.6 Encryption Manager**

* **Purpose:** Secure backup data against unauthorized access.  
* **Responsibilities:** Generate/retrieve keys, stream encrypt data, sign payloads.  
* **Inputs:** Compressed Data Stream, Key Management Service credentials.  
* **Outputs:** Encrypted Data Stream, Digital Signatures.  
* **Dependencies:** AOS Key Management Service (KMS).  
* **Sockets:** Encryption Socket.  
* **Pipelines:** Encryption Pipeline.  
* **Failure Modes:** KMS unreachable, key rotation failure.  
* **Recovery:** Halt backup, alert admin. Never write unencrypted data if policy requires it.  
* **Future Expansion:** Post-quantum cryptographic algorithms.

### **7.7 Integrity Validator**

* **Purpose:** Guarantee cryptographic and structural integrity of data during creation.  
* **Responsibilities:** Calculate checksums in flight, compare pre/post processing hashes.  
* **Inputs:** Data streams at various pipeline stages.  
* **Outputs:** Hash values, Boolean Validation flags.  
* **Dependencies:** Cryptographic libraries.  
* **Sockets:** Validation Socket.  
* **Pipelines:** Validation Pipeline.  
* **Failure Modes:** Bit-flip in RAM during hash generation.  
* **Recovery:** Request pipeline stage retry.  
* **Future Expansion:** ECC memory monitoring integration.

### **7.8 Metadata Manager**

* **Purpose:** Aggregate and structure data about the backup.  
* **Responsibilities:** Compile the Metadata Schema (Section 6), format as JSON/BSON.  
* **Inputs:** Outputs from all other modules.  
* **Outputs:** Complete Metadata Object.  
* **Dependencies:** System Information APIs.  
* **Sockets:** None.  
* **Pipelines:** Catalog Pipeline.  
* **Failure Modes:** Missing field data.  
* **Recovery:** Insert null or UNKNOWN, flag for manual audit.  
* **Future Expansion:** Distributed Ledger metadata registration.

### **7.9 Backup Catalog**

* **Purpose:** Central database of all backups and their locations.  
* **Responsibilities:** Store metadata, provide query interface, maintain state.  
* **Inputs:** Metadata Objects, Query Requests.  
* **Outputs:** Search results, Backup IDs.  
* **Dependencies:** Local embedded database (SQLite/DuckDB).  
* **Sockets:** Catalog Socket.  
* **Pipelines:** Catalog Pipeline.  
* **Failure Modes:** Database corruption.  
* **Recovery:** Rebuild from metadata files stored alongside physical backups.  
* **Future Expansion:** Graph database for differential chain resolution.

### **7.10 Retention Manager**

* **Purpose:** Enforce lifecycle rules on existing backups.  
* **Responsibilities:** Evaluate expiration dates, flag backups for deletion.  
* **Inputs:** Backup Catalog records, Time signals.  
* **Outputs:** Deletion queues.  
* **Dependencies:** Backup Catalog, Configuration Interface.  
* **Sockets:** None.  
* **Pipelines:** None.  
* **Failure Modes:** Deleting actively used/locked backups.  
* **Recovery:** Strict dependency checking before deletion command.  
* **Future Expansion:** Policy-as-code custom retention scripts.

### **7.11 Rotation Manager**

* **Purpose:** Manage tiered backup storage schemes (e.g., Grandfather-Father-Son).  
* **Responsibilities:** Promote/demote backups between retention tiers.  
* **Inputs:** Retention Manager queues.  
* **Outputs:** Tier update commands to Catalog.  
* **Dependencies:** Retention Manager.  
* **Sockets:** None.  
* **Pipelines:** None.  
* **Failure Modes:** Tier collapse logic errors.  
* **Recovery:** Audit log reversal of tier assignments.  
* **Future Expansion:** Cloud-tiering automated migration.

### **7.12 Import Manager**

* **Purpose:** Ingest foreign or offline backups into the AOS ecosystem.  
* **Responsibilities:** Validate external payload, extract metadata, register to Catalog.  
* **Inputs:** External file paths, USB mount points.  
* **Outputs:** Catalog Registration, internal storage path.  
* **Dependencies:** Storage Manager, Verification Engine.  
* **Sockets:** Backup Socket (Import mode).  
* **Pipelines:** Export/Import Pipeline.  
* **Failure Modes:** Corrupt external media, version mismatch.  
* **Recovery:** Reject import, generate error report.  
* **Future Expansion:** Peer-to-peer secure import over network.

### **7.13 Export Manager**

* **Purpose:** Package backups for external storage or migration.  
* **Responsibilities:** Bundle backup \+ metadata, enforce export encryption.  
* **Inputs:** Backup ID, Target Destination.  
* **Outputs:** Exported archive file.  
* **Dependencies:** Backup Catalog, Storage Manager.  
* **Sockets:** Backup Socket (Export mode).  
* **Pipelines:** Export Pipeline.  
* **Failure Modes:** Target destination full/disconnected.  
* **Recovery:** Queue export, retry on connection.  
* **Future Expansion:** Direct-to-S3 secure streaming.

### **7.14 Storage Manager**

* **Purpose:** Interface with physical and logical storage mediums.  
* **Responsibilities:** Mount/unmount targets, write streams to disk, manage I/O.  
* **Inputs:** Final Encrypted Stream, Storage Target URI.  
* **Outputs:** Physical file creation, byte written confirmation.  
* **Dependencies:** Host OS storage stack.  
* **Sockets:** Storage Socket.  
* **Pipelines:** Storage Pipeline.  
* **Failure Modes:** Disk full, write error, bus disconnect.  
* **Recovery:** Pause stream, alert, wait for target remediation.  
* **Future Expansion:** Multi-path I/O (MPIO) support.

### **7.15 Verification Engine**

* **Purpose:** Post-storage validation to guarantee restorable data.  
* **Responsibilities:** Read backup from storage, decrypt, decompress, verify against hash.  
* **Inputs:** Stored Backup File.  
* **Outputs:** Verification Status Update to Catalog.  
* **Dependencies:** Storage Manager, Encryption Manager.  
* **Sockets:** Validation Socket.  
* **Pipelines:** Verification Pipeline.  
* **Failure Modes:** Verification failure (data corruption detected).  
* **Recovery:** Mark backup CORRUPTED, trigger immediate replacement backup.  
* **Future Expansion:** Automated test-restore into sandbox VM.

### **7.16 Metrics Manager**

* **Purpose:** Track performance and capacity statistics.  
* **Responsibilities:** Measure throughput, deduplication ratios, compression ratios, time-to-backup.  
* **Inputs:** Telemetry from all pipelines.  
* **Outputs:** Timeseries data.  
* **Dependencies:** AOS Telemetry System.  
* **Sockets:** None.  
* **Pipelines:** None.  
* **Failure Modes:** Metric buffer overflow.  
* **Recovery:** Drop oldest metrics; do not block backup execution.  
* **Future Expansion:** Predictive capacity planning dashboards.

### **7.17 Audit Manager**

* **Purpose:** Provide non-repudiation and compliance tracking.  
* **Responsibilities:** Log who triggered what backup, policy changes, and deletions.  
* **Inputs:** Module state changes, User Contexts.  
* **Outputs:** Immutable audit log entries.  
* **Dependencies:** AOS Logging Subsystem.  
* **Sockets:** Audit Socket.  
* **Pipelines:** None.  
* **Failure Modes:** Cannot write to secure log.  
* **Recovery:** Cache in memory, halt system if cache exceeds threshold (strict security mode).  
* **Future Expansion:** Syslog/SIEM forwarding.

### **7.18 Configuration Interface**

* **Purpose:** Surface tunable parameters to the OS and Administrators.  
* **Responsibilities:** Validate config changes, hot-reload settings.  
* **Inputs:** Config files, API calls.  
* **Outputs:** Parsed Configuration Objects.  
* **Dependencies:** None.  
* **Sockets:** Configuration Socket.  
* **Pipelines:** None.  
* **Failure Modes:** Malformed configuration syntax.  
* **Recovery:** Reject change, revert to last known good configuration.  
* **Future Expansion:** Centralized configuration management (Consul/etcd).

## **8\. BACKUP LIFECYCLE**

1. **Backup Requested:** Originates from user, schedule, or system (Update Manager).  
2. **Validation:** Request is authenticated and validated against policies.  
3. **Snapshot:** Point-in-time filesystem/state freeze occurs.  
4. **Compression:** Snapshot data is reduced.  
5. **Encryption:** Compressed data is secured.  
6. **Integrity Verification:** In-flight checksums calculated.  
7. **Storage:** Stream is written to designated target(s).  
8. **Catalog Registration:** Metadata is committed to the database.  
9. **Verification:** Storage medium is read back to confirm integrity.  
10. **Ready For Recovery:** State updated in Catalog; Recovery Manager notified of availability.

**Exception Handling:**

* **Validation Failure:** Request rejected, audit logged.  
* **Storage Failure:** Retry loop initialized (3 attempts). If fail, abort and trigger Manual Intervention.  
* **Verification Failure:** Backup marked Corrupt. Re-trigger Backup Lifecycle from Step 3\.

## **9\. BACKUP VALIDATION**

Validation is strictly enforced across multiple dimensions:

* **Checksum/Hash:** SHA-256 pre-encryption, SHA-384 post-encryption.  
* **Integrity:** Structural headers of TAR/ZSTD/AES blocks are verified.  
* **Compression/Encryption:** Magic byte checking on streams.  
* **Metadata:** JSON schema validation (Required fields present).  
* **Version Compatibility:** Ensure AOS version matches backup manifest rules.  
* **Storage Accessibility:** Pre-flight Read/Write/Execute permission checks on target directories.  
* **Backup Completeness:** Byte count matching between Snapshot Engine output and Storage Manager input.

## **10\. RETENTION POLICIES**

The Retention Manager executes the following supported paradigms:

* **Daily:** Retain X daily backups.  
* **Weekly:** Retain X weekly backups (usually Sunday 00:00).  
* **Monthly:** Retain X monthly backups (1st of month).  
* **Yearly:** Retain X yearly backups.  
* **Manual/Permanent:** Never delete unless explicitly overridden by Administrator.  
* **Archive:** Moved to slow storage, exempted from automatic deletion.  
* **Automatic Cleanup:** Purges oldest unprotected backup when Storage Target reaches 90% capacity.  
* **Rotation Rules:** Enforces Grandfather-Father-Son (GFS) promotion logic.

## **11\. RESTORE POINTS**

Restore Points are instantaneous, optimized backups strictly utilized for rollback capability.

**Triggers:**

* System Updates (Requested by Update Manager)  
* Configuration Changes  
* Package Installation (Requested by Package Manager)  
* Plugin Installation  
* Connector Installation  
* Schema Migration  
* Database Migration  
* Manual Requests  
* Emergency Operations

*Implementation Note:* Restore points heavily leverage underlying filesystem copy-on-write (COW) capabilities to ensure sub-second generation times.

## **12\. SOCKETS**

| Socket Name | Purpose | Direction | Auth | Validation | Timeout | Retry | Version | Logging | Security |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| **Backup Socket** | Primary API for backup requests | IN/OUT | RBAC | Schema | 30s | 0 | v1 | TRACE | TLS 1.3 |
| **Snapshot Socket** | Interface to OS fs tools | OUT | Root | Path | 60s | 3 | v1 | DEBUG | IPC Local |
| **Storage Socket** | I/O streaming to disks | OUT | IAM | Mount | None | 5 | v1 | INFO | Kernel Auth |
| **Validation Socket** | Checksum verification | IN/OUT | None | Hash | 300s | 1 | v1 | DEBUG | Memory Isolate |
| **Compression Socket** | Data reduction routing | IN/OUT | None | Stream | None | 0 | v1 | DEBUG | None |
| **Encryption Socket** | KMS and cipher operations | IN/OUT | KMS Token | KeyPair | 10s | 3 | v1 | WARN | Secure Enclave |
| **Catalog Socket** | Database transactions | IN/OUT | Internal | SQL/ORM | 5s | 5 | v1 | INFO | Encrypted DB |
| **Audit Socket** | Security event logging | OUT | System | Format | 2s | 10 | v1 | TRACE | WORM Storage |
| **Config Socket** | Policy modification | IN | Admin | JSON Schema | 5s | 0 | v1 | INFO | Signed Payload |

## **13\. PIPELINES**

| Pipeline | Source | Destination | Payload | Validation | Retry | Timeout | Recovery | Version |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| **Backup Request** | Ext. Systems | Backup Core | JSON Command | Schema | 0 | 5s | Drop | 1.0 |
| **Snapshot** | Snapshot Engine | Comp. Engine | Raw Bytes | Fsck check | 2 | 120s | Abort | 1.0 |
| **Compression** | Comp. Engine | Enc. Engine | LZ4/ZSTD Bytes | Magic Bytes | 0 | None | Passthrough | 1.0 |
| **Encryption** | Enc. Engine | Storage Mgr | AES Bytes | Auth Tag | 1 | None | Abort | 1.0 |
| **Validation** | Core | Validator | Hash Strings | SHA Match | 1 | 30s | Re-hash | 1.0 |
| **Catalog** | Metadata Mgr | DB Engine | JSON Record | Constraint | 3 | 10s | Cache | 1.0 |
| **Storage** | Enc. Engine | Disk/NAS | Data Stream | I/O success | 5 | 30s/mb | Alt Target | 1.0 |
| **Verification** | Storage Mgr | Validator | Stored Bytes | SHA Match | 3 | None | Mark Corrupt | 1.0 |
| **Export** | Storage Mgr | Ext. Drive | Enc. Archive | Byte Count | 2 | None | Resume | 1.0 |
| **Recovery Prep** | Catalog | Recovery Mgr | Metadata \+ Path | ACL Check | 0 | 10s | Deny | 1.0 |

## **14\. SECURITY**

* **Backup Authentication:** All API calls require active JWT/RBAC tokens with backup:create or backup:manage scopes.  
* **Encryption:** AES-256-GCM enforced for all non-local backups. Keys managed exclusively by AOS KMS.  
* **Access Control:** The physical backup directory (e.g., /var/lib/hojaiga/backups) is restricted to root:root with 700 permissions.  
* **Integrity Verification:** Multi-stage hashing prevents data injection.  
* **Tamper Detection:** Catalog database is protected by an HMAC signature. Modifications outside the application space invalidate the catalog.  
* **Permission Validation:** Storage targets are tested for proper ownership prior to write execution.  
* **Secure Storage:** Audit logs are written to WORM (Write Once Read Many) compliant targets where available.  
* **Audit Logging:** Every lifecycle transition emits an immutable log entry.

## **15\. LOGGING**

The Backup Manager generates structured JSON logs categorized into:

* **Backup Logs:** Orchestration, state changes, durations.  
* **Snapshot Logs:** Filesystem locks, sync times, volume names.  
* **Validation Logs:** Hash comparisons, block verifications.  
* **Storage Logs:** Throughput (MB/s), IOPS, target latencies.  
* **Verification Logs:** Post-backup read integrity checks.  
* **Export Logs:** Transfer rates, target media serial numbers.  
* **Audit Logs:** Security events, user triggers, policy modifications.  
* **Metrics:** Prometheus-compatible time-series exports.  
* **Version History:** Record of AOS version against Backup Manager module versions.

## **16\. CONFIGURATION**

Configuration is managed via backup\_config.yaml:

* **Backup Schedule:** CRON definitions for automated routines.  
* **Compression Policies:** Enable/Disable, Algorithm preference, CPU thread limits.  
* **Encryption Policies:** KMS endpoint, fallback keys, algorithm selection.  
* **Retention Policies:** GFS parameters, disk space thresholds.  
* **Storage Locations:** Primary and secondary URI definitions, mount parameters.  
* **Verification Policies:** Inline vs. Post-process verification toggle.  
* **Logging Levels:** TRACE, DEBUG, INFO, WARN, ERROR, FATAL per module.  
* **Recovery Preparation Policies:** Pre-warming procedures for rapid restore operations.

## **17\. MERMAID DIAGRAMS**

### **17.1 Overall Backup Manager Architecture**

Code snippet  
graph TD  
    A\[Update Manager / System\] \--\>|Request| B(Backup Core)  
    B \--\> C{Backup Planner}  
    C \--\> D\[Snapshot Engine\]  
    D \--\> E\[Compression Engine\]  
    E \--\> F\[Encryption Engine\]  
    F \--\> G\[Storage Manager\]  
    G \--\> H\[(Storage Targets)\]  
      
    B \-.-\> I\[Metadata Manager\]  
    I \--\> J\[(Backup Catalog)\]  
      
    G \-.-\> K\[Verification Engine\]  
    K \-.-\> J  
      
    J \-.-\> L\[Recovery Manager\]  
    H \-.-\> L

### **17.2 Backup Lifecycle**

Code snippet  
stateDiagram-v2  
    \[\*\] \--\> Validation  
    Validation \--\> Snapshot : Approved  
    Validation \--\> \[\*\] : Rejected  
    Snapshot \--\> Compression  
    Compression \--\> Encryption  
    Encryption \--\> Storage  
    Storage \--\> CatalogRegistration  
    CatalogRegistration \--\> Verification  
    Verification \--\> ReadyForRecovery : Success  
    Verification \--\> Corrupted : Failure  
    ReadyForRecovery \--\> \[\*\]

### **17.3 Snapshot Flow**

Code snippet  
sequenceDiagram  
    participant BC as Backup Core  
    participant SE as Snapshot Engine  
    participant OS as OS Filesystem  
    BC-\>\>SE: Trigger Snapshot(Target)  
    SE-\>\>OS: Quiesce I/O (Freeze)  
    OS--\>\>SE: I/O Locked  
    SE-\>\>OS: Execute COW Snapshot  
    OS--\>\>SE: Snapshot Created (UUID)  
    SE-\>\>OS: Release I/O (Thaw)  
    OS--\>\>SE: I/O Active  
    SE--\>\>BC: Return Snapshot Path

### **17.4 Backup Verification**

Code snippet  
graph LR  
    A\[Storage Target\] \--\>|Read Stream| B(Storage Manager)  
    B \--\> C(Decryption)  
    C \--\> D(Decompression)  
    D \--\> E{Integrity Validator}  
    E \--\>|Hash Match| F\[Catalog: VERIFIED\]  
    E \--\>|Hash Mismatch| G\[Catalog: CORRUPTED\]

### **17.5 Backup Storage**

Code snippet  
graph TD  
    A\[Storage Manager\] \--\> B{Protocol Router}  
    B \--\>|Local FS| C\[(Local NVMe)\]  
    B \--\>|USB| D\[(External HDD)\]  
    B \--\>|SMB/NFS| E\[(NAS Share)\]  
    B \--\>|S3 Abstraction| F\[(Cloud Storage)\]

### **17.6 Retention Policy Flow**

Code snippet  
graph TD  
    A(Time Trigger) \--\> B\[Retention Manager\]  
    B \--\> C{Query Catalog}  
    C \--\> D\[Expired Backups List\]  
    D \--\> E\[Storage Manager\]  
    E \--\> F\[Delete Physical Files\]  
    F \--\> G\[Remove from Catalog\]

### **17.7 Restore Point Generation**

Code snippet  
sequenceDiagram  
    participant UM as Update Manager  
    participant BM as Backup Manager  
    participant PM as Package Manager  
    UM-\>\>BM: Pre-Update Restore Point Req.  
    BM-\>\>BM: Execute Hot Snapshot  
    BM-\>\>BM: Catalog Restore Point  
    BM--\>\>UM: Success (Backup ID)  
    UM-\>\>PM: Proceed with Update

### **17.8 Deployment Diagram**

Code snippet  
deploymentDiagram  
    node "AOS Host Environment" {  
        node "Backup Manager Daemon" {  
            component "Core Pipeline"  
            component "Catalog SQLite"  
        }  
    }  
    node "Storage Environment" {  
        database "Local /var/backups"  
        database "Attached Network Storage"  
    }  
    "Backup Manager Daemon" \-- "Encrypted I/O" \--\> "Storage Environment"

### **17.9 Folder Diagram**

Code snippet  
mindmap  
  root((Backup Manager))  
    src  
      core  
      engines  
      managers  
      pipelines  
      sockets  
    config  
      policies  
    tests  
      unit  
      integration

## **18\. ASCII DIAGRAMS**

### **18.1 Complete Backup Manager Architecture**

Plaintext  
\+-------------------------------------------------------------+  
|                     BACKUP MANAGER                          |  
|                                                             |  
|  \+--------+    \+-----------+    \+-------------+             |  
|  | Planner|---\>| Snapshot  |---\>| Compression |             |  
|  \+--------+    \+-----------+    \+-------------+             |  
|                                        |                    |  
|  \+--------+    \+-----------+    \+-------------+             |  
|  | Catalog|\<---| Validator |\<---| Encryption  |             |  
|  \+--------+    \+-----------+    \+-------------+             |  
|      |                                 |                    |  
|      v                                 v                    |  
|  \+--------+                     \+-------------+             |  
|  |Recovery| (Read Only Path)    | Storage Mgr |             |  
|  |Manager |\<--------------------|             |             |  
|  \+--------+                     \+-------------+             |  
\+-------------------------------------------------------------+

### **18.2 Backup Pipeline**

Plaintext  
\[Data Source\] \-\> \[Snapshot\] \-\> \[Compress LZ4\] \-\> \[Encrypt AES\] \-\> \[Hash SHA\] \-\> \[Storage\]

### **18.3 Snapshot Process**

Plaintext  
(1) Lock Target Dir \---\> (2) Execute LVM/BTRFS Snap \---\> (3) Unlock Dir \---\> (4) Return Snap Mount

### **18.4 Storage Hierarchy**

Plaintext  
\[ Tier 1: Local SSD \] \----\> Instant Restore Points (Max 3 days)  
       |  
       v  
\[ Tier 2: NAS / HDD \] \----\> Full/Differential Archives (Max 90 days)  
       |  
       v  
\[ Tier 3: Offline \] \------\> Yearly / Permanent Airgapped

### **18.5 Retention Flow**

Plaintext  
Cron Trigger \-\> Fetch Expired IDs \-\> Delete Storage Blob \-\> Verify Deletion \-\> Purge Catalog Row

### **18.6 Verification Process**

Plaintext  
\[Storage Target\] \-\> Read Chunk \-\> Decrypt \-\> Hash Match? \-\> Yes (Continue) / No (Flag Corrupt)

### **18.7 Restore Point Flow**

Plaintext  
Event(Update) \-\> Request Trigger \-\> Lock System State \-\> Snap \-\> Catalog UUID \-\> Return OK \-\> Execute Event

### **18.8 Component Relationships**

Plaintext  
\[Update Mgr\] \---requests---\> \[Backup Core\] \<---reads--- \[Recovery Mgr\]  
                                   |  
                             \[Storage Mgr\]  
                                   |  
                             \[Target Disk\]

## **19\. FOLDER STRUCTURE**

Plaintext  
/hojaiga/aos/src/backup\_manager/  
├── core/                  \# Main orchestration and lifecycle logic  
│   ├── backup\_core.rs  
│   └── planner.rs  
├── engines/               \# Processing units  
│   ├── snapshot/  
│   ├── compression/  
│   ├── encryption/  
│   └── verification/  
├── managers/              \# State and policy controllers  
│   ├── retention.rs  
│   ├── rotation.rs  
│   ├── storage.rs  
│   └── metadata.rs  
├── catalog/               \# Database and indexing  
│   ├── db.rs  
│   ├── schema.sql  
│   └── queries.rs  
├── interfaces/            \# Sockets and external communication  
│   ├── sockets/  
│   ├── api.rs  
│   └── cli.rs  
├── pipelines/             \# Stream processing definitions  
│   ├── request\_pipe.rs  
│   └── storage\_pipe.rs  
├── utils/                 \# Helpers  
│   ├── hashing.rs  
│   └── metrics.rs  
└── tests/                 \# QA  
    ├── unit/  
    └── integration/

## **20\. IMPLEMENTATION GUIDE**

* **Class Responsibilities:** strictly adhere to the boundaries defined in Section 7\. A Manager handles state and routing; an Engine performs heavy computation/I/O.  
* **Public Interfaces:** The Backup Manager exposes REST/gRPC endpoints bound strictly to the Backup Socket and Config Socket. Direct database or filesystem access by other system organs is strictly prohibited.  
* **Internal Interfaces:** Communication between modules utilizes memory-safe channels (e.g., Rust mpsc) to prevent blocking the main orchestration thread.  
* **Configuration Files:** Base configuration must reside in /etc/hojaiga/backup/backup\_config.yaml.  
* **Naming Convention:** All physical backup files must follow: YYYYMMDD-HHMMSS\_UUID\_\[type\].hosbak  
* **Coding Standards:** Strict memory safety (Rust preferred). Explicit error handling required for all I/O and cryptographic operations. Silent failures are prohibited.  
* **Testing Strategy:** 100% unit test coverage on all cryptographic and hashing modules. Integration tests must utilize virtual loopback devices to simulate disk full and I/O failure scenarios.  
* **Performance Targets:**  
  * Restore Point Generation (Hot): \< 500ms.  
  * Compression Throughput: \> 500MB/s (LZ4).  
  * Encryption Throughput: \> 1GB/s (AES-NI hardware accelerated).

## **21\. FUTURE COMPATIBILITY**

Architecture is designed to seamlessly integrate:

* **Distributed Backups:** Sharding of backup payloads across multiple AOS nodes.  
* **Cloud Backups:** S3-compatible API plugins for Storage Manager.  
* **Remote Backup Servers:** Dedicated AOS-Backup appliances receiving network streams.  
* **Snapshot Replication:** Native BTRFS/ZFS send/receive protocols across network.  
* **Cross-Machine Restore:** Hardware-agnostic payload restructuring.  
* **Incremental Sync:** Continuous Data Protection (CDP) byte-level syncing.  
* **Encrypted Off-site Backups:** Zero-knowledge architectural enforcement.  
* **Future Organ Backups:** Dynamic capability to backup newly registered system components.  
* **Future Plugin/Connector Backups:** Isolated sandbox backups for third-party extensions.

