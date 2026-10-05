# HOJAIGA - PIPELINE 19 CONNECTION STATUS DIAGRAMS (Configuration Manager)

## DIAGRAM 1: BEFORE CONNECTION
```mermaid
sequenceDiagram
    participant O as Organ 20 (Configuration Manager)
    participant C as CNS
    O->>O: Bootstrapping Local Processes
    O-xC: IPC Socket Not Found (Disconnected)
```

## DIAGRAM 2: AFTER CONNECTION
```mermaid
sequenceDiagram
    participant O as Organ 20 (Configuration Manager)
    participant C as CNS
    O->>C: Connect IPC (Named Pipe / Unix Socket)
    C-->>O: Connection Established (ACK)
    O->>C: Emit EVENT_ORGAN_READY
    C-->>O: Register Subscriptions
```

## DIAGRAM 3: SYSTEM BUILD (CUMULATIVE ARCHITECTURE)
```mermaid
graph TD
    CNS((Organ 02: CNS Orchestrator))
    ORG[Configuration Manager (Organ 20)]
    CNS <-->|Bi-directional IPC| ORG
```
