# HOJAIGA - PIPELINE 20 CONNECTION STATUS DIAGRAMS (Configuration Schema)

## DIAGRAM 1: BEFORE CONNECTION
```mermaid
sequenceDiagram
    participant O as Organ 21 (Configuration Schema)
    participant C as CNS
    O->>O: Bootstrapping Local Processes
    O-xC: IPC Socket Not Found (Disconnected)
```

## DIAGRAM 2: AFTER CONNECTION
```mermaid
sequenceDiagram
    participant O as Organ 21 (Configuration Schema)
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
    ORG[Configuration Schema (Organ 21)]
    CNS <-->|Bi-directional IPC| ORG
```
