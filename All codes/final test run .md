bsolutely. What you want now is **not another individual test**. You want one **master certification prompt** that tells Antigravity:

1. inspect the real V2 implementation;  
2. run every existing V2 certification/regression test;  
3. test the actual runtime end-to-end;  
4. test autonomy, Eye, CDP, GUI-CDP, recovery, checkpointing, branching, verification, audit, concurrency, browser isolation, resources, Excel, impossible tasks, etc.;  
5. **do not fake or weaken anything**;  
6. identify every genuine missing piece;  
7. make the necessary architectural/code changes;  
8. rerun the entire certification from scratch;  
9. continue fixing and retesting until every mandatory gate passes;  
10. produce a final evidence package and certificate;  
11. after that, declare the V2 architecture **validated and ready for practical workflows**.

One important wording change I strongly recommend: don't certify it as "bug-free forever." Certify it as **architecturally validated for transition to real-world practical workflows**. If you later change the architecture or add a new capability, that naturally creates a new regression obligation.

Here is the **single master prompt** I'd give Antigravity.

---

# **HOJAIGA V2 — MASTER FINAL CERTIFICATION, REPAIR & ACCEPTANCE PROTOCOL**

## **PURPOSE**

This is the **FINAL V2 ARCHITECTURAL CERTIFICATION AND ACCEPTANCE TEST**.

This prompt supersedes and consolidates all previous V2 certification prompts and requirements.

The objective is to establish a hard boundary between:

> **V2 Architecture Validation**

and

> **Real-World Practical Workflow Execution**

The goal is NOT to obtain a convenient PASS.

The goal is to determine, using the **real Hojaiga V2 runtime and real implementation**, whether the architecture is genuinely capable of executing autonomous computer-use workflows safely, correctly, verifiably, recoverably, and concurrently.

You must inspect the implementation, execute the runtime, test the real behavior, identify deficiencies, repair genuine defects where necessary, and then perform a complete final certification regression.

Do not assume anything works because a module exists.

Do not assume anything works because a previous test passed.

Do not assume anything works because an event was emitted.

Do not assume anything works because a controller returned `SUCCESS`.

Prove actual behavior.

---

# **0\. FINAL CERTIFICATION RULE**

There are only two final outcomes:

### **PASS**

\========================================================  
        HOJAIGA V2 FINAL SYSTEM CERTIFICATION  
\========================================================

RUNTIME INTEGRITY          PASS  
BROWSER AUTONOMY           PASS  
BRAIN / MODEL              PASS  
EYE / PERCEPTION           PASS  
UI EXPLORATION             PASS  
APP SELECTION              PASS  
CDP EXECUTION              PASS  
GUI-CDP / DAP              PASS  
CHILD WINDOW HANDLING      PASS  
POPUP / ERROR HANDLING     PASS  
WORKFLOW COMPILATION       PASS  
DECISION ENGINE            PASS  
TASK ORCHESTRATION         PASS  
AGENT EXECUTION            PASS  
BRANCHING                  PASS  
CONVERGENCE                PASS  
FAILURE DETECTION          PASS  
FAILURE RECOVERY           PASS  
CHECKPOINT RECOVERY        PASS  
VERIFICATION               PASS  
AUDIT / OBSERVABILITY      PASS  
STATE ISOLATION             PASS  
EVENT ISOLATION             PASS  
BROWSER ISOLATION          PASS  
RESOURCE ISOLATION         PASS  
PARALLEL EXECUTION         PASS  
CONCURRENCY                PASS  
DUPLICATE EVENT SAFETY     PASS  
OUT-OF-ORDER SAFETY        PASS  
STRESS                     PASS  
EXCEL / DATA WORKFLOW      PASS  
MULTI-SURFACE CONTINUITY   PASS  
NATURAL-LANGUAGE ROBUSTNESS PASS  
UNEXPECTED UI ADAPTATION   PASS  
IMPOSSIBLE-TASK HANDLING   PASS  
END-TO-END AUTONOMY        PASS  
FINAL REGRESSION           PASS

\========================================================  
      HOJAIGA V2 STATUS: VALIDATED  
\========================================================

V2 ARCHITECTURE:  
VALIDATED

V2 AUTONOMOUS COMPUTER-USE:  
VALIDATED

STATUS:  
READY FOR REAL-WORLD PRACTICAL WORKFLOW TESTING

NO FURTHER ARCHITECTURAL CERTIFICATION REQUIRED  
UNLESS THE ARCHITECTURE OR CERTIFIED CAPABILITIES CHANGE.  
\========================================================

### **FAIL**

HOJAIGA V2 FINAL SYSTEM CERTIFICATION: FAIL

The report must identify exactly what failed and why.

---

# **1\. ABSOLUTE RULES**

These rules are mandatory.

## **1.1 REAL RUNTIME ONLY**

Use the real:

* `HojaigaRuntimeInstance`  
* Interface  
* CNS  
* EventBus  
* Brain  
* Model/LLM  
* Memory  
* Knowledge  
* Workflow Compiler  
* Decision Engine  
* Security/Governance  
* Task Orchestrator  
* Agents  
* Controllers  
* Browser Controller  
* Chrome/CDP  
* GUI Controller  
* GUI-CDP/DAP  
* Eye/Vision  
* UI Explorer  
* App Scanner  
* Popup Handler  
* Recovery  
* Checkpoint system  
* Verification  
* Audit  
* Resource Manager  
* parallel execution/resource pools  
* Excel/data/document capabilities

Do not replace real components with mocks merely to obtain PASS.

Mocks may only be used for isolated unit testing where the existing architecture already legitimately uses them.

They may NOT be used to claim that the real runtime capability works.

---

# **2\. NO FAKE SUCCESS**

Immediate certification failure if you discover:

* unconditional `success=True`;  
* fake SUCCESS events;  
* fake completion;  
* simulated browser results presented as real results;  
* fake Eye observations;  
* fake verification;  
* fake recovery;  
* manually injected completion events;  
* hardcoded test-specific business actions;  
* mocked controllers replacing real execution;  
* test harness performing the business operation;  
* bypassing CNS/EventBus;  
* bypassing the Task Orchestrator;  
* bypassing the real controllers;  
* bypassing verification;  
* claiming success because an action was attempted rather than because the outcome exists.

The certification must prove **physical/environmental/data effects**.

---

# **3\. PHASE 0 — PRESERVE THE BASELINE**

Before modifying anything:

1. Inspect the repository.  
2. Determine the current git branch.  
3. Record the exact commit/hash.  
4. Record working-tree status.  
5. Identify all V2 runtime modules.  
6. Identify all existing V2 tests.  
7. Identify existing certification scripts.  
8. Identify existing browser/GUI/CDP test infrastructure.  
9. Identify existing Excel/data tests.  
10. Identify all previously certified paths.

Create:

v2\_pre\_certification\_baseline.json  
v2\_pre\_certification\_baseline.md

Record:

* commit hash;  
* branch;  
* timestamp;  
* runtime version;  
* test commands discovered;  
* existing test results;  
* existing known failures;  
* existing modifications.

Do not destroy existing work.

---

# **4\. PHASE 1 — COMPLETE ARCHITECTURE DISCOVERY**

Trace the actual V2 dependency graph.

Do not rely solely on documentation.

Determine:

Interface  
   ↓  
CNS / EventBus  
   ↓  
Brain  
   ↓  
Memory / Knowledge  
   ↓  
LLM  
   ↓  
Workflow Compiler  
   ↓  
Decision Engine  
   ↓  
Security / Capability  
   ↓  
Task Orchestrator  
   ↓  
Agent  
   ↓  
Environment  
   ↓  
Controller  
   ↓  
Browser / GUI / CDP / DAP  
   ↓  
Verification  
   ↓  
Checkpoint  
   ↓  
Completion  
   ↓  
Audit

For every component determine:

* implementation;  
* registration;  
* initialization;  
* dependencies;  
* EventBus topics;  
* inputs;  
* outputs;  
* task identity;  
* correlation identity;  
* session identity;  
* error propagation;  
* recovery path;  
* whether actually reachable;  
* whether actually used;  
* whether optional;  
* whether bypassed;  
* why bypassed.

Generate:

v2\_system\_capability\_inventory.json  
v2\_system\_capability\_inventory.md  
---

# **5\. PHASE 2 — RUN ALL EXISTING CERTIFICATION TESTS FIRST**

Before changing architecture, discover and execute every relevant existing test.

At minimum locate and run, if present:

test\_v2\_validation.py  
test\_v2\_final\_certification.py  
test\_v2\_branching.py

and all existing tests corresponding to:

* browser autonomy;  
* real verification;  
* recovery;  
* checkpoint recovery;  
* branching;  
* convergence;  
* runtime startup;  
* CNS/EventBus;  
* orchestration;  
* CDP;  
* GUI-CDP/DAP;  
* Eye;  
* Excel;  
* resource management;  
* concurrency.

Do not invent that a test passed.

Capture actual output.

Record:

TEST  
COMMAND  
START TIME  
END TIME  
EXIT CODE  
PASS/FAIL  
ERROR  
TRACE  
---

# **6\. PHASE 3 — GAP ANALYSIS**

After the baseline tests and architectural inspection, produce a complete gap matrix.

For every requirement:

Capability  
Required?  
Implementation exists?  
Reachable?  
Actually exercised?  
Evidence?  
PASS / FAIL / PARTIAL / NOT TESTED  
Defect?  
Severity  
Required repair?

Do not immediately modify code just to make a test pass.

First understand the failure.

Classify every issue as:

REAL ARCHITECTURAL DEFECT  
IMPLEMENTATION DEFECT  
INTEGRATION DEFECT  
MODEL/PLANNING DEFECT  
CONTROLLER DEFECT  
EYE/PERCEPTION DEFECT  
VERIFICATION DEFECT  
CONCURRENCY DEFECT  
TEST INFRASTRUCTURE DEFECT  
ENVIRONMENTAL LIMITATION  
NOT ACTUALLY REQUIRED  
---

# **7\. PHASE 4 — REPAIR MISSING CAPABILITIES**

After the first complete test pass/fail analysis:

Fix genuine defects.

Rules:

* preserve previously working functionality;  
* do not weaken assertions;  
* do not remove failing tests;  
* do not convert failures into warnings;  
* do not suppress errors;  
* do not fabricate results;  
* do not hardcode test-specific behavior;  
* do not bypass the architecture;  
* do not make unrelated refactors;  
* do not modify already-certified functionality unless required to fix a genuine defect.

For every modification record:

FILE  
CHANGE  
REASON  
DEFECT ADDRESSED  
EXPECTED EFFECT  
REGRESSION RISK

Generate:

v2\_repair\_log.md  
---

# **8\. PHASE 5 — BRAIN / MODEL AUTONOMY**

Submit genuine natural-language objectives.

Do NOT provide low-level instructions such as:

* click this selector;  
* click these coordinates;  
* use this controller;  
* open this exact application;  
* execute these exact actions.

The runtime must determine:

USER OBJECTIVE  
↓  
INTENT  
↓  
REASONING  
↓  
PLAN  
↓  
WORKFLOW  
↓  
TASKS  
↓  
EXECUTION

Prove that model output actually influences execution.

A model response that is ignored while hardcoded code performs the task is FAIL.

---

# **9\. PHASE 6 — EYE / PERCEPTION CERTIFICATION**

The Eye is a HARD certification gate.

Prove:

* current screen acquisition;  
* browser-state observation;  
* application UI observation;  
* visible-control identification;  
* active-window detection;  
* UI-state interpretation;  
* dynamic state changes;  
* child-window detection;  
* popup detection;  
* stale-state avoidance;  
* observation timestamps;  
* observation-to-action relationship.

Test:

SCREEN A  
↓  
OBSERVE  
↓  
UI CHANGES  
↓  
SCREEN B  
↓  
OBSERVE AGAIN  
↓  
REASON  
↓  
ACT  
↓  
VERIFY

The runtime must use actual Eye information.

Simply returning an image from an Eye function is insufficient.

---

# **10\. PHASE 7 — CDP CERTIFICATION**

Using the real Chrome/CDP runtime, prove:

* navigation;  
* DOM inspection;  
* interaction;  
* state change;  
* result extraction;  
* verification.

The action must originate from the actual V2 execution chain.

---

# **11\. PHASE 8 — GUI-CDP / DAP CERTIFICATION**

Where appropriate, prove that GUI-CDP/DAP can perform genuine GUI-level execution.

Verify:

runtime decision  
↓  
GUI-CDP/DAP  
↓  
real UI interaction  
↓  
environment change  
↓  
Eye observation  
↓  
verification

Do not mark this PASS merely because the module exists.

---

# **12\. PHASE 9 — INTELLIGENT APPLICATION SELECTION**

Create a task where multiple installed applications could potentially solve the objective.

Do not specify the application.

The Brain must determine the appropriate environment/tool.

Record:

* candidate applications;  
* selected application;  
* reasoning/evidence;  
* launch;  
* execution;  
* verification.

Selection must not be hardcoded.

---

# **13\. PHASE 10 — UI EXPLORATION**

After application launch, prove that the runtime can inspect and understand the application.

Verify:

* active window;  
* visible controls;  
* actionable elements;  
* application state;  
* relevant UI regions.

Do not supply every coordinate in advance.

---

# **14\. PHASE 11 — CHILD WINDOWS / POPUPS**

Test:

* new browser tab;  
* child window;  
* modal;  
* dialog;  
* popup;  
* secondary surface.

Prove:

MAIN WINDOW  
↓  
ACTION  
↓  
NEW WINDOW  
↓  
DETECT  
↓  
RESOLVE ACTIVE SURFACE  
↓  
INTERACT  
↓  
VERIFY  
↓  
CONTINUE

The runtime must not blindly continue operating against stale context.

---

# **15\. PHASE 12 — REAL FAILURE / RECOVERY**

Use a genuine failure.

Example:

real controller action  
↓  
missing selector  
↓  
real controller failure  
↓  
TASK\_FAILED  
↓  
diagnosis  
↓  
recovery  
↓  
alternative plan  
↓  
retry  
↓  
verification  
↓  
SUCCESS

Recovery must be performed by the real runtime.

---

# **16\. PHASE 13 — CHECKPOINT RECOVERY**

Create:

STEP A ✓  
STEP B ✓  
STEP C ✗  
STEP D

Cause a real failure after a valid checkpoint.

Verify that recovery resumes from the appropriate checkpoint rather than unnecessarily restarting.

Verify checkpoint identity and state integrity.

---

# **17\. PHASE 14 — BRANCHING / CONVERGENCE**

Test:

TASK  
 ├── MEMORY  
 ├── KNOWLEDGE  
 └── TOOL  
       ↓  
CONVERGENCE  
       ↓  
COMPILATION  
       ↓  
EXECUTION  
       ↓  
VERIFICATION

Verify:

* independent branch state;  
* correct pending branches;  
* branch completion;  
* convergence;  
* no premature completion;  
* duplicate branch completion safety.

---

# **18\. PHASE 15 — CONCURRENCY CERTIFICATION**

This is mandatory.

Launch at least six independent tasks concurrently:

TASK-A  
TASK-B  
TASK-C  
TASK-D  
TASK-E  
TASK-F

Use unique:

* task IDs;  
* correlation IDs;  
* session IDs;  
* agent IDs;  
* browser contexts where required.

Required patterns:

### **TASK-A**

Simple successful browser task.

### **TASK-B**

Intentional failure followed by recovery:

FAILED  
→ BLOCKED  
→ RECOVERING  
→ RETRIED  
→ SUCCESS

### **TASK-C**

Independent successful browser task.

### **TASK-D**

Conditional/multi-branch task.

### **TASK-E**

Failure \+ alternative recovery.

### **TASK-F**

Successful task executing while another task is recovering.

---

# **19\. EVENT ISOLATION**

For every event verify:

event.task\_id  
\==  
receiving\_task.task\_id

Prove:

* A cannot advance B;  
* B cannot complete A;  
* recovery from C cannot affect D;  
* one completion cannot satisfy another task's branch.

Any cross-task event consumption \= FAIL.

---

# **20\. STATE ISOLATION**

For every concurrent task independently track:

* state;  
* pending branches;  
* retries;  
* recovery state;  
* checkpoint;  
* execution context;  
* result.

Prove:

STATE-A ≠ STATE-B  
STATE-B ≠ STATE-C  
...

No state contamination is allowed.

---

# **21\. BROWSER SESSION ISOLATION**

Prove:

* task-specific browser context;  
* page/session ownership;  
* DOM isolation;  
* navigation isolation;  
* recovery-session binding.

Specifically test:

TASK-A selector  
cannot affect TASK-B

TASK-A navigation  
cannot navigate TASK-B

TASK-A DOM  
cannot satisfy TASK-B

TASK-A recovery  
cannot operate TASK-B browser  
---

# **22\. CONCURRENT FAILURE \+ SUCCESS**

Mandatory scenario:

TASK-A → FAIL

TASK-B → SUCCESS

while:

TASK-A → RECOVERY

and:

TASK-B → COMPLETION

Expected:

TASK-A:  
FAILED  
→ BLOCKED  
→ RECOVERING  
→ RETRIED  
→ SUCCESS

TASK-B:  
RUNNING  
→ SUCCESS

A failure in A must never block B.

---

# **23\. COMPLETION ORDER TEST**

Repeat concurrent workloads multiple times.

Completion order must be allowed to vary naturally.

Final correctness must remain identical regardless of ordering.

The runtime must not depend on one lucky event sequence.

---

# **24\. DUPLICATE EVENT TEST**

Under concurrency test controlled duplicate events.

Examples:

KNOWLEDGE\_COMPLETED  
KNOWLEDGE\_COMPLETED

and:

TASK\_COMPLETED  
TASK\_COMPLETED

Verify:

* no duplicate compilation;  
* no duplicate terminal completion;  
* no state corruption;  
* no cross-task impact.

---

# **25\. OUT-OF-ORDER EVENT TEST**

Test invalid ordering:

COMPILATION\_COMPLETED  
before  
COMPILATION\_STARTED

for TASK-A while TASK-B legitimately executes.

The invalid A event must not affect B.

---

# **26\. STRESS TEST**

After the six-task test passes:

Run at least 20 concurrent tasks.

Mix:

* success;  
* failure;  
* recovery;  
* branching;  
* multi-branch;  
* no-branch;  
* delayed completion.

Track:

* deadlocks;  
* races;  
* event cross-talk;  
* state contamination;  
* browser contamination;  
* resource leaks;  
* incorrect completion.

A stress failure is a certification failure unless clearly demonstrated to be an external environmental limitation rather than a V2 defect.

---

# **27\. RESOURCE MANAGEMENT**

During concurrency verify:

* allocation;  
* ownership;  
* isolation;  
* release;  
* cleanup;  
* controller association;  
* agent association;  
* browser association.

One task failure must not corrupt another task's resources.

---

# **28\. MULTI-SURFACE CONTINUITY**

Test transitions between:

Browser  
Desktop GUI  
Application  
Child Window  
Dialog  
CDP  
GUI-CDP/DAP  
Excel/Data

where applicable.

The task objective must remain intact across surface changes.

---

# **29\. PARALLEL LEAD \+ EXCEL WORKFLOW**

Create a controlled practical workflow requiring:

1. research;  
2. lead identification;  
3. qualification;  
4. structured records;  
5. Excel output.

Allow appropriate concurrent execution.

The runtime should determine the decomposition.

Conceptually:

USER OBJECTIVE  
       ↓  
    BRAIN  
       ↓  
 ┌───────────────┐  
 │               │  
Research       Data/Excel  
 │               │  
 └───────┬───────┘  
         ↓  
 Synchronization  
         ↓  
 Final Workbook

Do not hardcode that exact decomposition.

Inspect the resulting workbook independently.

Verify that the workbook contains actual runtime-generated data.

---

# **30\. VERIFICATION INDEPENDENCE**

Never equate:

Controller SUCCESS

with:

Requested outcome exists

Every major operation must be independently verified.

Use:

ACTION  
↓  
ACTUAL ENVIRONMENT  
↓  
OBSERVATION  
↓  
VERIFICATION  
↓  
COMPLETION

False verification \= FAIL.

---

# **31\. AUDIT / OBSERVABILITY**

Every major operation must be traceable.

Capture:

run\_id  
parent\_run\_id  
task\_id  
correlation\_id  
session\_id  
event\_id  
timestamp  
event\_type  
source  
destination  
agent  
controller  
action  
state  
branch  
browser/session  
status  
error  
recovery  
checkpoint  
verification  
result

The audit trail must correspond to actual execution.

---

# **32\. NATURAL-LANGUAGE ROBUSTNESS**

Test equivalent objectives expressed differently.

For example:

Find the requested information and organize it.

Research the information, then structure the results.

Gather the relevant records and put them into the spreadsheet.

The runtime should understand semantic intent rather than relying on one exact string.

---

# **33\. UNEXPECTED UI CHANGE**

During execution alter the controlled environment.

Examples:

* selector changes;  
* button moves;  
* dialog appears;  
* extra element appears;  
* page state changes.

The runtime must obtain fresh state and adapt.

Expected:

OBSERVE  
↓  
DETECT CHANGE  
↓  
REASON  
↓  
ADAPT  
↓  
EXECUTE  
↓  
VERIFY

Blind replay \= FAIL.

---

# **34\. IMPOSSIBLE TASK TEST**

Submit a task that genuinely cannot be completed.

The runtime must not hallucinate success.

Expected:

TASK  
↓  
ATTEMPT  
↓  
EVIDENCE OF IMPOSSIBILITY  
↓  
FAIL / ESCALATE / REPORT

Fabricated SUCCESS \= immediate certification failure.

---

# **35\. TEST-3 / END-TO-END PRACTICAL AUTONOMY**

Run one final integrated workflow combining as many real capabilities as safely applicable:

Natural-language objective  
        ↓  
Brain reasoning  
        ↓  
Intent normalization  
        ↓  
App/tool selection  
        ↓  
Workflow compilation  
        ↓  
Task decomposition  
        ↓  
Eye perception  
        ↓  
UI exploration  
        ↓  
Browser / GUI execution  
        ↓  
CDP / GUI-CDP where appropriate  
        ↓  
Child-window handling  
        ↓  
Popup/error handling  
        ↓  
Parallel work  
        ↓  
Data collection  
        ↓  
Excel/data output  
        ↓  
Controlled failure  
        ↓  
Recovery  
        ↓  
Fresh perception  
        ↓  
Continue  
        ↓  
Independent verification  
        ↓  
Audit  
        ↓  
Completion

The harness may observe.

The harness must NOT perform the task for Hojaiga.

The test specifies the desired outcome, not the low-level route.

---

# **36\. REAL-TIME STATE / IDENTITY INTEGRITY**

For every task continuously validate:

task\_id  
correlation\_id  
session\_id  
agent\_id  
browser\_context  
controller  
state  
result

No ambiguity is allowed.

---

# **37\. EXISTING V2 EXECUTION-FLOW REGRESSION**

The existing V2 execution flow demonstrated through the current runtime visualization/HTML flow must remain valid.

Verify that the actual runtime can produce the established successful path, including where applicable:

System Boot  
↓  
Interface  
↓  
CNS  
↓  
Brain  
↓  
Memory / Knowledge  
↓  
LLM  
↓  
Workflow Compiler  
↓  
Decision Engine  
↓  
Security / Capability  
↓  
Task Orchestrator  
↓  
Agent  
↓  
Perception  
↓  
Controller  
↓  
CDP  
↓  
Checkpoint / Verification  
↓  
Completion

Also verify the real recovery path.

The visualization is evidence of event flow, but **the visualization itself is not proof of functionality**.

The underlying physical execution must be validated.

---

# **38\. FINAL REGRESSION**

After all repairs and after all capability tests pass, run the entire regression suite again.

At minimum:

test\_v2\_validation.py  
test\_v2\_final\_certification.py  
test\_v2\_branching.py

plus:

* all browser tests;  
* Eye tests;  
* recovery tests;  
* checkpoint tests;  
* concurrency tests;  
* resource tests;  
* Excel/data tests;  
* integration tests;  
* all newly created certification tests.

No previously validated functionality may regress.

---

# **39\. FINAL RE-TEST MUST START CLEAN**

The final certification must be performed against:

* clean runtime state;  
* fresh test data;  
* fresh task IDs;  
* fresh correlation IDs;  
* fresh browser sessions;  
* no stale checkpoints;  
* no stale completion state;  
* no leftover task state;  
* no test artifacts that could falsely satisfy verification.

Where possible, repeat critical tests more than once.

---

# **40\. CERTIFICATION EVIDENCE STANDARD**

A capability can only be marked PASS when there is evidence.

Acceptable evidence includes:

* actual runtime trace;  
* EventBus trace;  
* browser/CDP trace;  
* screenshot/observation evidence;  
* actual DOM/environment state;  
* actual generated workbook;  
* audit record;  
* checkpoint record;  
* independent verification;  
* timestamps proving concurrency;  
* task/session correlation;  
* actual source-code path;  
* test output.

Do not mark something PASS merely because the code appears logically correct.

---

# **41\. REQUIRED FINAL ARTIFACTS**

Generate all of the following:

v2\_pre\_certification\_baseline.json  
v2\_pre\_certification\_baseline.md

v2\_system\_capability\_inventory.json  
v2\_system\_capability\_inventory.md

v2\_repair\_log.md  
v2\_gap\_analysis.md

v2\_final\_system\_acceptance\_trace.json  
v2\_final\_system\_acceptance\_graph.md  
V2\_FINAL\_SYSTEM\_ACCEPTANCE\_REPORT.md

v2\_concurrency\_certification\_trace.json  
v2\_concurrency\_certification\_graph.md  
v2\_concurrency\_certification\_report.md

v2\_final\_practical\_workflow\_output.xlsx

V2\_FINAL\_CERTIFICATE.md

Where applicable, also preserve:

screenshots/  
traces/  
logs/  
browser evidence/  
test outputs/  
---

# **42\. FINAL ACCEPTANCE REPORT**

`V2_FINAL_SYSTEM_ACCEPTANCE_REPORT.md` must contain:

| Capability | Required | Tested | Real Evidence | Result |
| ----- | ----- | ----- | ----- | ----- |
| Runtime startup | YES |  |  |  |
| CNS/EventBus | YES |  |  |  |
| Brain/Model | YES |  |  |  |
| Intent normalization | YES |  |  |  |
| Workflow compilation | YES |  |  |  |
| Decision making | YES |  |  |  |
| Memory/Knowledge | CONDITIONAL |  |  |  |
| Security/Governance | CONDITIONAL |  |  |  |
| Task orchestration | YES |  |  |  |
| Agent execution | YES |  |  |  |
| Browser/CDP | YES |  |  |  |
| GUI-CDP/DAP | YES |  |  |  |
| Eye/Vision | YES |  |  |  |
| UI exploration | YES |  |  |  |
| App selection | YES |  |  |  |
| Child-window handling | YES |  |  |  |
| Popup handling | YES |  |  |  |
| Failure detection | YES |  |  |  |
| Recovery | YES |  |  |  |
| Checkpoint recovery | YES |  |  |  |
| Branching | YES |  |  |  |
| Convergence | YES |  |  |  |
| Parallel execution | YES |  |  |  |
| Concurrency | YES |  |  |  |
| Resource management | YES |  |  |  |
| Excel/data workflow | YES |  |  |  |
| Verification | YES |  |  |  |
| Audit | YES |  |  |  |
| State isolation | YES |  |  |  |
| Event isolation | YES |  |  |  |
| Browser isolation | YES |  |  |  |
| Impossible-task handling | YES |  |  |  |
| Natural-language robustness | YES |  |  |  |
| Unexpected UI adaptation | YES |  |  |  |
| End-to-end workflow | YES |  |  |  |

---

# **43\. CONCURRENCY CERTIFICATION MATRIX**

`v2_concurrency_certification_report.md` must contain:

| Task | Pattern | Expected | Actual | Result |
| ----- | ----- | ----- | ----- | ----- |
| A | Success | SUCCESS |  |  |
| B | Failure \+ Recovery | SUCCESS |  |  |
| C | Independent Success | SUCCESS |  |  |
| D | Branching | SUCCESS |  |  |
| E | Failure \+ Alternative Recovery | SUCCESS |  |  |
| F | Concurrent Success | SUCCESS |  |  |

Also report:

* event isolation;  
* state isolation;  
* browser isolation;  
* branch isolation;  
* recovery isolation;  
* resource isolation;  
* completion-order tests;  
* duplicate-event tests;  
* out-of-order-event tests;  
* 20-task stress test;  
* deadlock detection;  
* race detection.

---

# **44\. CERTIFICATION GRAPH**

Generate:

v2\_final\_system\_acceptance\_graph.md

and:

v2\_concurrency\_certification\_graph.md

Show actual execution relationships.

Example:

USER  
 ↓  
INTERFACE  
 ↓  
CNS / EVENTBUS  
 ↓  
BRAIN  
 ├── MEMORY  
 ├── KNOWLEDGE  
 └── LLM  
 ↓  
WORKFLOW COMPILER  
 ↓  
DECISION ENGINE  
 ↓  
SECURITY / CAPABILITY  
 ↓  
TASK ORCHESTRATOR  
 ├── TASK A  
 ├── TASK B  
 ├── TASK C  
 └── ...  
 ↓  
AGENTS  
 ↓  
ENVIRONMENT CONTROLLERS  
 ├── BROWSER  
 ├── CDP  
 ├── GUI  
 └── GUI-CDP/DAP  
 ↓  
EYE / OBSERVATION  
 ↓  
VERIFICATION  
 ↓  
CHECKPOINT  
 ↓  
AUDIT  
 ↓  
COMPLETION

The graph must distinguish actual execution from merely available components.

---

# **45\. FINAL CERTIFICATE**

Only if **every mandatory gate passes**, create:

V2\_FINAL\_CERTIFICATE.md

Use:

\========================================================  
             HOJAIGA V2 FINAL CERTIFICATE  
\========================================================

CERTIFICATION:  
FINAL SYSTEM ACCEPTANCE

RUNTIME:  
Hojaiga V2

COMMIT:  
\<exact tested commit hash\>

CERTIFICATION DATE:  
\<timestamp\>

\--------------------------------------------------------  
CORE CAPABILITIES  
\--------------------------------------------------------

Runtime Integrity             PASS  
Brain / Model                 PASS  
Intent / Planning             PASS  
Workflow Compilation          PASS  
Task Orchestration            PASS  
Agent Execution                PASS

\--------------------------------------------------------  
COMPUTER USE  
\--------------------------------------------------------

Eye / Perception              PASS  
UI Exploration                PASS  
Browser Autonomy              PASS  
CDP                            PASS  
GUI-CDP / DAP                  PASS  
App Selection                  PASS  
Child Windows                 PASS  
Popup Handling                PASS  
Unexpected UI Adaptation      PASS

\--------------------------------------------------------  
RELIABILITY  
\--------------------------------------------------------

Failure Detection             PASS  
Failure Recovery              PASS  
Checkpoint Recovery            PASS  
Branching                      PASS  
Convergence                    PASS  
Independent Verification       PASS  
Impossible Task Handling       PASS

\--------------------------------------------------------  
CONCURRENCY  
\--------------------------------------------------------

Task Isolation                PASS  
Event Isolation               PASS  
State Isolation               PASS  
Browser Isolation             PASS  
Branch Isolation              PASS  
Recovery Isolation            PASS  
Resource Isolation            PASS  
Parallel Execution             PASS  
Duplicate Event Safety         PASS  
Out-of-Order Event Safety      PASS  
Stress Test                    PASS

\--------------------------------------------------------  
DATA / PRACTICAL EXECUTION  
\--------------------------------------------------------

Excel/Data Workflow            PASS  
Multi-Surface Continuity       PASS  
Audit / Observability          PASS  
End-to-End Practical Workflow  PASS

\--------------------------------------------------------  
REGRESSION  
\--------------------------------------------------------

Existing V2 Tests              PASS  
Final Certification Tests      PASS  
Concurrency Tests              PASS  
No Regression                  PASS

\========================================================

HOJAIGA V2 STATUS:

                VALIDATED

\========================================================

The Hojaiga V2 architecture has successfully passed  
the final architectural and autonomous computer-use  
certification using the real runtime.

The system is approved to transition from:

ARCHITECTURE VALIDATION

to:

REAL-WORLD PRACTICAL WORKFLOW VALIDATION.

No further architectural certification is required  
unless the certified architecture or capabilities are  
subsequently modified or a new capability is introduced.

\========================================================  
---

# **46\. IF CERTIFICATION FAILS**

If anything fails, DO NOT create a PASS certificate.

Instead produce:

V2\_FINAL\_CERTIFICATION\_FAILURE.md

Include:

* failed capability;  
* exact test;  
* expected behavior;  
* actual behavior;  
* event sequence;  
* task ID;  
* correlation ID;  
* session ID;  
* responsible component;  
* root cause;  
* severity;  
* proposed fix;  
* files requiring modification;  
* regression risk.

Then return to:

PHASE 4 — REPAIR

and repeat the complete certification cycle.

---

# **47\. ITERATIVE REPAIR LOOP**

The agent is authorized to perform this cycle:

DISCOVER  
   ↓  
BASELINE  
   ↓  
TEST EVERYTHING  
   ↓  
ANALYZE  
   ↓  
IDENTIFY REAL DEFECTS  
   ↓  
REPAIR  
   ↓  
REGRESSION  
   ↓  
FULL CERTIFICATION  
   ↓  
FAIL?  
 ┌───────┴───────┐  
YES              NO  
 ↓                ↓  
REPAIR         CERTIFY  
 ↓                ↓  
RETEST          STOP

Do not stop after fixing only the first failure.

Do not stop after one successful test.

Do not declare PASS until the **complete final suite** passes.

---

# **48\. DO NOT GAME THE CERTIFICATION**

Never:

* weaken assertions;  
* delete tests;  
* skip failed tests;  
* convert errors to warnings;  
* alter expected results merely to match actual results;  
* hardcode success;  
* hardcode task routes;  
* hardcode selectors solely for certification;  
* inject fake events;  
* manually complete tasks;  
* fake Eye observations;  
* fake verification;  
* suppress race conditions;  
* hide exceptions;  
* ignore deadlocks;  
* ignore cross-task contamination;  
* claim an environmental limitation without evidence.

If the environment genuinely prevents a test, explicitly document it and determine whether that prevents certification.

---

# **49\. FINAL PRACTICAL-READINESS DECISION**

The final question is:

> Can Hojaiga V2 now accept a natural-language objective and autonomously determine, execute, observe, adapt, recover, verify, audit, and complete the appropriate computer-use workflow through the real architecture?

And:

> Can multiple independent workflows execute concurrently without contaminating one another?

And:

> Can the runtime honestly report failure when the requested outcome cannot be achieved?

If the answer is demonstrated by real evidence for every mandatory capability:

V2 VALIDATED

At that point, stop creating arbitrary synthetic architectural certification tests.

Transition to real Hojaiga practical workloads.

Future testing should be limited to:

* regression testing after code changes;  
* newly introduced capabilities;  
* newly discovered production defects;  
* domain-specific workflow validation.

---

# **50\. FINAL INSTRUCTION**

**Do the work.**

Do not merely explain how the certification could be performed.

Inspect the actual repository.

Run the actual runtime.

Run the actual tests.

Trace the actual dependency graph.

Exercise the real browser and computer-use paths.

Exercise the real Eye.

Exercise real recovery.

Exercise real checkpointing.

Exercise real branching.

Exercise real concurrency.

Exercise real Excel/data output.

Inspect actual outcomes independently.

Repair genuine deficiencies.

Rerun the complete suite.

Continue until either:

### **A.**

Every mandatory certification gate passes and the evidence supports:

HOJAIGA V2 FINAL SYSTEM ACCEPTANCE: PASS

or:

### **B.**

A genuine unresolved blocker remains, in which case clearly identify it and do not claim certification.

**Do not optimize for PASS. Optimize for truth.**

When — and only when — every mandatory requirement has passed on the real V2 runtime, create the final certificate and state:

HOJAIGA V2: VALIDATED

READY FOR REAL-WORLD PRACTICAL WORKFLOW TESTING.  
---

## **One thing I'd change about your plan**

This prompt gives you the **final architectural gate** you're looking for. After it passes, I would genuinely treat V2 as *certified* and stop doing endless "does the architecture work?" tests.

The important boundary is:

**V2 certification ≠ every future workflow will succeed.**

It means the machinery needed to execute those workflows has been demonstrated to work: planning, perception, execution, verification, recovery, isolation, concurrency, etc.

So once Antigravity gives you that PASS certificate, your next move can be exactly what you were aiming for:

> **Give Hojaiga the actual master lead-generation task.**

And if that real task exposes a bug, that's a **practical workflow bug/regression**, not a reason to invent another 47-page architecture certification every Tuesday. 😄

This is the version I'd use as the **single final master prompt**.

