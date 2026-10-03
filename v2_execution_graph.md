```mermaid
graph TD
  interface["Interface <br/> SUCCESS"]:::s_interface
  classDef s_interface fill:#4CAF50,color:white
  interface --> cns
  cns["CNS <br/> SUCCESS"]:::s_cns
  classDef s_cns fill:#4CAF50,color:white
  cns --> brain
  brain["Brain <br/> SUCCESS"]:::s_brain
  classDef s_brain fill:#4CAF50,color:white
  brain --> memory
  memory["Memory/Knowledge <br/> SKIPPED"]:::s_memory
  classDef s_memory fill:#FFC107,color:black
  memory --> compiler
  compiler["Workflow Compiler <br/> SKIPPED"]:::s_compiler
  classDef s_compiler fill:#FFC107,color:black
  compiler --> decision
  decision["Decision Engine <br/> SKIPPED"]:::s_decision
  classDef s_decision fill:#FFC107,color:black
  decision --> security
  security["Security/Governance <br/> SKIPPED"]:::s_security
  classDef s_security fill:#FFC107,color:black
  security --> orchestrator
  orchestrator["Task Orchestrator <br/> SKIPPED"]:::s_orchestrator
  classDef s_orchestrator fill:#FFC107,color:black
  orchestrator --> agent
  agent["Agent <br/> SKIPPED"]:::s_agent
  classDef s_agent fill:#FFC107,color:black
  agent --> controller
  controller["Controller <br/> SKIPPED"]:::s_controller
  classDef s_controller fill:#FFC107,color:black
  controller --> verification
  verification["Verification <br/> SKIPPED"]:::s_verification
  classDef s_verification fill:#FFC107,color:black
  verification --> audit
  audit["Audit <br/> SUCCESS"]:::s_audit
  classDef s_audit fill:#4CAF50,color:white
  audit --> completion
  completion["Completion <br/> SKIPPED"]:::s_completion
  classDef s_completion fill:#FFC107,color:black
```