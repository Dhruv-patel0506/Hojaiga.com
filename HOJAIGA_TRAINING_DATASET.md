# Hojaiga System Training Dataset
## Full System Testing - Easy to Hard Progression

**Version:** 1.0  
**Date:** 2026-09-29  
**Purpose:** Comprehensive training dataset for Hojaiga system testing from basic functionality to complex scenarios

---

## Dataset Structure

This training dataset is organized into four difficulty levels:
- **Level 1: Easy** - Basic component functionality and isolated unit tests
- **Level 2: Medium** - Integration tests and organ interactions
- **Level 3: Hard** - Complex workflows and system-wide scenarios
- **Level 4: Expert** - Edge cases, stress tests, and recovery scenarios

Each test case includes:
- Test ID
- Description
- Pre-conditions
- Test Steps
- Expected Results
- Success Criteria
- Related Organs/Components

---

## Level 1: Easy Tests (Basic Functionality)

### Test E001: Brain Gatekeeper Basic Authentication
**Test ID:** E001  
**Difficulty:** Easy  
**Component:** Brain_Gatekeeper.py  

**Description:** Verify that the Gatekeeper properly validates authentication tokens for Ollama API requests.

**Pre-conditions:**
- Gatekeeper server is running on port 11435
- Ollama service is running on port 11434
- Secret passcode is set to "339680"

**Test Steps:**
1. Send a POST request to `http://127.0.0.1:11435/api/chat` without authentication header
2. Verify 401 Unauthorized response
3. Send same request with `X-Hojaiga-Validation: 339680` header
4. Verify successful response from Ollama

**Expected Results:**
- Step 1: Response code 401 with "Unauthorized" message
- Step 3: Response code 200 with valid Ollama response

**Success Criteria:**
- Unauthorized requests are blocked
- Authorized requests pass through to Ollama
- Authentication headers are properly checked

**Related Components:** Brain_Gatekeeper.py, organ_01_brain.py

---

### Test E002: Basic CNS Event Subscription
**Test ID:** E002  
**Difficulty:** Easy  
**Component:** organ_02_cns_single_file.py  

**Description:** Test basic event subscription functionality in the Central Nervous System.

**Pre-conditions:**
- CNS system is initialized
- EventBus is running

**Test Steps:**
1. Connect to CNS using `connect_to_organ` function
2. Subscribe to a basic event type (e.g., "SYSTEM_START")
3. Trigger a SYSTEM_START event
4. Verify event is received by subscriber

**Expected Results:**
- Connection established successfully
- Subscription confirmation received
- Event is delivered to subscriber within 100ms

**Success Criteria:**
- Event subscription works without errors
- Events are delivered in correct order
- No memory leaks from subscription

**Related Components:** organ_02_cns_single_file.py, organ_99_visual_adapter.py

---

### Test E003: Memory Storage and Retrieval
**Test ID:** E003  
**Difficulty:** Easy  
**Component:** organ_03_memory.py  

**Description:** Test basic memory write and read operations.

**Pre-conditions:**
- Memory organ is initialized
- Storage backend is available

**Test Steps:**
1. Store a simple key-value pair: `test_key = "test_value"`
2. Retrieve the value using the same key
3. Verify the retrieved value matches the stored value
4. Delete the key
5. Attempt retrieval and verify key no longer exists

**Expected Results:**
- Step 2: Retrieved value equals "test_value"
- Step 5: Retrieval returns None or appropriate "not found" indicator

**Success Criteria:**
- Write operations complete successfully
- Read operations return correct data
- Delete operations properly remove data

**Related Components:** organ_03_memory.py, database_manager.py

---

### Test E004: Knowledge Base Simple Query
**Test ID:** E004  
**Difficulty:** Easy  
**Component:** organ_04_knowledge.py  

**Description:** Test basic knowledge base query functionality.

**Pre-conditions:**
- Knowledge base is initialized with sample data
- At least 10 knowledge entries exist

**Test Steps:**
1. Query knowledge base for a known term (e.g., "Hojaiga")
2. Verify relevant results are returned
3. Query for non-existent term
4. Verify empty result set

**Expected Results:**
- Step 2: Returns at least 1 relevant result with confidence score > 0.5
- Step 4: Returns empty result set or no matches

**Success Criteria:**
- Knowledge queries execute without errors
- Relevant results are ranked appropriately
- Non-existent queries return empty results

**Related Components:** organ_04_knowledge.py, organ_knowledge_manager.py

---

### Test E005: Security Gatekeeper Basic Check
**Test ID:** E005  
**Difficulty:** Easy  
**Component:** organ_07_security.py  

**Description:** Test basic security validation for a safe operation.

**Pre-conditions:**
- Security organ is initialized
- Basic security rules are loaded

**Test Steps:**
1. Request security validation for a safe operation (e.g., "read_system_status")
2. Verify approval is granted
3. Request validation for a clearly unsafe operation (e.g., "delete_system_files")
4. Verify denial

**Expected Results:**
- Step 2: Validation returns APPROVED
- Step 4: Validation returns DENIED with reason

**Success Criteria:**
- Safe operations are approved
- Unsafe operations are blocked
- Security decisions are logged

**Related Components:** organ_07_security.py, Brain_Gatekeeper.py

---

### Test E006: Controller Basic Command
**Test ID:** E006  
**Difficulty:** Easy  
**Component:** organ_05_controllers.py  

**Description:** Test basic controller command execution.

**Pre-conditions:**
- Controller organ is running
- A test controller is available

**Test Steps:**
1. Send a basic command to controller (e.g., "status")
2. Verify command acknowledgment
3. Verify response contains expected status information

**Expected Results:**
- Command is acknowledged within 50ms
- Response contains valid status data
- No errors in controller logs

**Success Criteria:**
- Commands are processed correctly
- Responses are well-formed
- Controller remains stable after command

**Related Components:** organ_05_controllers.py, organ_01_brain.py

---

### Test E007: Database Connection Test
**Test ID:** E007  
**Difficulty:** Easy  
**Component:** database_manager.py  

**Description:** Test basic database connectivity and operations.

**Pre-conditions:**
- Database is running
- DatabaseManager is initialized

**Test Steps:**
1. Create DatabaseManager instance
2. Test database connection with ping
3. Create a test table
4. Insert a test record
5. Query the record
6. Clean up (drop table)

**Expected Results:**
- Step 2: Connection successful
- Step 5: Retrieved record matches inserted data

**Success Criteria:**
- Database connection is stable
- Basic CRUD operations work
- Cleanup completes without errors

**Related Components:** database_manager.py, organ_03_memory.py

---

### Test E008: Configuration Manager Load
**Test ID:** E008  
**Difficulty:** Easy  
**Component:** organ_20_configuration_manager.py  

**Description:** Test configuration loading and validation.

**Pre-conditions:**
- Configuration file exists (runtime_config.yaml)
- Configuration manager is available

**Test Steps:**
1. Load configuration from file
2. Verify configuration structure matches schema
3. Access a known configuration value
4. Modify a configuration value in memory
5. Verify change is reflected

**Expected Results:**
- Configuration loads without errors
- Schema validation passes
- Modified value is accessible

**Success Criteria:**
- Configuration loading works
- Schema validation catches invalid configs
- Runtime modifications are reflected

**Related Components:** organ_20_configuration_manager.py, organ_21_configuration_schema.py

---

### Test E009: Visual Perception Basic Image Processing
**Test ID:** E009  
**Difficulty:** Easy  
**Component:** organ_31_visual_perception.py  

**Description:** Test basic image processing capabilities.

**Pre-conditions:**
- Visual perception organ is initialized
- Test image is available

**Test Steps:**
1. Load a test image (simple geometric shapes)
2. Perform basic object detection
3. Verify detected objects match expected shapes
4. Test image classification

**Expected Results:**
- Image loads successfully
- At least 2 objects are detected
- Classification confidence > 0.7 for correct class

**Success Criteria:**
- Image processing completes without errors
- Object detection accuracy > 80%
- Processing time < 2 seconds for test image

**Related Components:** organ_31_visual_perception.py, organ_31_vision_health_monitor.py

---

### Test E010: Agent Basic Task Assignment
**Test ID:** E010  
**Difficulty:** Easy  
**Component:** organ_10_agents.py  

**Description:** Test basic agent task assignment and status reporting.

**Pre-conditions:**
- Agent system is running
- At least one agent is available

**Test Steps:**
1. List available agents
2. Assign a simple task to an agent (e.g., "echo hello")
3. Monitor agent status
4. Verify task completion
5. Check agent returns to idle state

**Expected Results:**
- Agent list is non-empty
- Task is accepted
- Agent status transitions: IDLE -> BUSY -> IDLE
- Task result matches expected output

**Success Criteria:**
- Agents accept tasks correctly
- Status transitions are accurate
- Task results are correct

**Related Components:** organ_10_agents.py, organ_38_task_orchestrator.py

---

## Level 2: Medium Tests (Integration)

### Test M001: Multi-Organ Event Flow
**Test ID:** M001  
**Difficulty:** Medium  
**Component:** CNS + Multiple Organs  

**Description:** Test event propagation across multiple organs in the system.

**Pre-conditions:**
- CNS is running
- At least 3 organs are connected (Brain, Memory, Knowledge)
- All organs are healthy

**Test Steps:**
1. Inject a complex event into CNS (e.g., "USER_QUERY" with payload)
2. Verify event is received by Brain organ
3. Verify Brain organ processes and forwards to Memory
4. Verify Memory stores event context
5. Verify Knowledge organ is queried for relevant information
6. Verify final response is generated and returned

**Expected Results:**
- Event propagates through all organs in correct order
- Each organ processes event appropriately
- Final response is coherent and complete
- Processing completes within 5 seconds

**Success Criteria:**
- Event flow follows expected path
- All organs participate correctly
- No organs are skipped or hang
- Response quality is acceptable

**Related Components:** organ_02_cns_single_file.py, organ_01_brain.py, organ_03_memory.py, organ_04_knowledge.py

---

### Test M002: Vision System Integration
**Test ID:** M002  
**Difficulty:** Medium  
**Component:** Visual Perception + LLM Runtime  

**Description:** Test integration between visual perception and LLM processing.

**Pre-conditions:**
- Visual perception organ is running
- LLM runtime is available
- Test image with text content is available

**Test Steps:**
1. Capture or load an image containing text
2. Process image through visual perception
3. Extract detected text/objects
4. Send extracted data to LLM for analysis
5. Verify LLM provides meaningful analysis

**Expected Results:**
- Image is processed successfully
- Text/objects are extracted with accuracy > 75%
- LLM receives data in correct format
- LLM analysis is relevant to image content

**Success Criteria:**
- Vision-to-LLM pipeline works end-to-end
- Data format conversion is correct
- Analysis quality is acceptable
- Total processing time < 10 seconds

**Related Components:** organ_31_visual_perception.py, organ_14_llm_runtime_single_file.py, organ_37_llm_gateway.py

---

### Test M003: Chrome CDP Basic Automation
**Test ID:** M003  
**Difficulty:** Medium  
**Component:** organ_19_chrome_cdp_runtime.py  

**Description:** Test basic Chrome automation using CDP (Chrome DevTools Protocol).

**Pre-conditions:**
- Chrome browser is installed
- Chrome can be launched with remote debugging
- CDP runtime organ is initialized

**Test Steps:**
1. Launch Chrome with CDP enabled
2. Navigate to a simple test page (e.g., example.com)
3. Wait for page load
4. Extract page title
5. Take a screenshot
6. Close Chrome

**Expected Results:**
- Chrome launches successfully
- Page loads within 5 seconds
- Page title is extracted correctly
- Screenshot is captured and saved
- Chrome closes cleanly

**Success Criteria:**
- CDP connection is stable
- Basic navigation works
- Page data extraction works
- Clean shutdown is achieved

**Related Components:** organ_19_chrome_cdp_runtime.py, organ_40_app_launcher.py

---

### Test M004: Popup Handler Integration
**Test ID:** M004  
**Difficulty:** Medium  
**Component:** organ_29_popup_handler.py + Gatekeeper  

**Description:** Test popup detection and handling integrated with Gatekeeper.

**Pre-conditions:**
- Popup handler is running
- Gatekeeper is running
- Test application that generates popups is available

**Test Steps:**
1. Start application that generates popups
2. Wait for popup to appear
3. Verify popup is detected by handler
4. Verify popup event is sent to Gatekeeper
5. Verify Gatekeeper logs popup event
6. Verify appropriate action is suggested/executed

**Expected Results:**
- Popup is detected within 2 seconds of appearance
- Event data includes correct coordinates and title
- Gatekeeper receives and logs event
- Action suggestion is relevant to popup type

**Success Criteria:**
- Popup detection works reliably
- Event data is accurate
- Integration with Gatekeeper is stable
- Action suggestions are useful

**Related Components:** organ_29_popup_handler.py, Brain_Gatekeeper.py, organ_30_app_scanner.py

---

### Test M005: Learning System Integration
**Test ID:** M005  
**Difficulty:** Medium  
**Component:** organ_08_learning.py + Memory + Knowledge  

**Description:** Test learning system integration with memory and knowledge base.

**Pre-conditions:**
- Learning organ is initialized
- Memory and knowledge organs are available
- Training data is available

**Test Steps:**
1. Provide learning system with a set of example patterns
2. Trigger learning process
3. Verify patterns are stored in memory
4. Verify knowledge base is updated with learned insights
5. Test system's ability to apply learned patterns to new data

**Expected Results:**
- Learning process completes without errors
- Patterns are stored with appropriate metadata
- Knowledge base contains new entries
- New data is processed using learned patterns
- Accuracy improves after learning

**Success Criteria:**
- Learning pipeline works end-to-end
- Memory integration is stable
- Knowledge base updates correctly
- Learned patterns are applicable

**Related Components:** organ_08_learning.py, organ_03_memory.py, organ_04_knowledge.py, organ_ml.py

---

### Test M006: Task Orchestration Multi-Step
**Test ID:** M006  
**Difficulty:** Medium  
**Component:** organ_38_task_orchestrator.py  

**Description:** Test orchestration of multi-step tasks across multiple organs.

**Pre-conditions:**
- Task orchestrator is running
- Multiple organs are available
- Test workflow is defined

**Test Steps:**
1. Define a 3-step workflow (e.g., Gather Data -> Process -> Report)
2. Submit workflow to orchestrator
3. Monitor execution of each step
4. Verify step transitions occur correctly
5. Verify final result is aggregated properly
6. Check for proper error handling if step fails

**Expected Results:**
- Workflow is accepted and scheduled
- Steps execute in defined order
- Each step receives required inputs
- Final result is complete
- Failed steps trigger appropriate error handling

**Success Criteria:**
- Workflow execution is reliable
- Step dependencies are respected
- Data flows correctly between steps
- Error handling is appropriate

**Related Components:** organ_38_task_orchestrator.py, organ_36_workflow_compiler.py, organ_22_decision_engine.py

---

### Test M007: Recovery Coordinator Basic
**Test ID:** M007  
**Difficulty:** Medium  
**Component:** centralized_recovery_coordinator.py  

**Description:** Test basic recovery coordination when an organ fails.

**Pre-conditions:**
- Recovery coordinator is running
- At least 3 organs are active
- One organ can be safely stopped

**Test Steps:**
1. Monitor system health
2. Gracefully stop one organ (e.g., Knowledge)
3. Verify failure is detected by recovery coordinator
4. Verify recovery attempt is initiated
5. Restart the stopped organ
6. Verify system returns to healthy state

**Expected Results:**
- Failure is detected within 5 seconds
- Recovery coordinator logs the failure
- Recovery attempt is made
- System acknowledges organ restart
- System returns to healthy state

**Success Criteria:**
- Failure detection is timely
- Recovery coordination works
- System can recover from single organ failure
- No data corruption occurs

**Related Components:** centralized_recovery_coordinator.py, organ_17_backup_manager.py, organ_35_update_manager.py

---

### Test M008: External Connector API Call
**Test ID:** M008  
**Difficulty:** Medium  
**Component:** organ_15_external_connectors.py  

**Description:** Test external API integration through connectors.

**Pre-conditions:**
- External connector organ is initialized
- Test API endpoint is available (e.g., a public REST API)
- Network connectivity is available

**Test Steps:**
1. Configure connector for test API
2. Make a simple GET request
3. Verify response is received
4. Parse response data
5. Make a POST request with test data
6. Verify response acknowledges the data

**Expected Results:**
- Connector configuration is valid
- GET request returns 200 status
- Response data is parseable
- POST request succeeds
- Response acknowledges sent data

**Success Criteria:**
- External API calls work
- Response handling is correct
- Error handling works for failed requests
- Authentication is handled if required

**Related Components:** organ_15_external_connectors.py, organ_01_brain.py

---

### Test M009: Capability Registry Query
**Test ID:** M009  
**Difficulty:** Medium  
**Component:** organ_18_capability_registry.py  

**Description:** Test capability registry for discovering and querying system capabilities.

**Pre-conditions:**
- Capability registry is initialized
- Multiple organs have registered their capabilities
- Registry contains at least 10 capabilities

**Test Steps:**
1. Query registry for all capabilities
2. Verify list is comprehensive
3. Query for specific capability (e.g., "vision_processing")
4. Verify capability details are returned
5. Query for non-existent capability
6. Verify empty result

**Expected Results:**
- All capabilities are listed
- Specific capability query returns detailed info
- Non-existent query returns empty
- Capability metadata is complete

**Success Criteria:**
- Registry accurately reflects system capabilities
- Queries are efficient
- Capability metadata is useful

**Related Components:** organ_18_capability_registry.py, organ_33_system_manifest.py

---

### Test M010: Teaching Void Basic Lesson
**Test ID:** M010  
**Difficulty:** Medium  
**Component:** organ_34_teaching_void.py  

**Description:** Test basic teaching void functionality with a simple lesson.

**Pre-conditions:**
- Teaching void organ is initialized
- Voice system is available (optional)
- Display system is available

**Test Steps:**
1. Start a teaching lesson with simple topic (e.g., "What is 2+2?")
2. Verify void visualization appears
3. Verify content is displayed on void
4. Test navigation controls (pan, zoom)
5. End lesson and verify cleanup

**Expected Results:**
- Lesson starts successfully
- Void appears with correct visual style
- Content is readable and accurate
- Navigation works smoothly
- Cleanup completes without errors

**Success Criteria:**
- Teaching void launches correctly
- Content display works
- Navigation is responsive
- System remains stable

**Related Components:** organ_34_teaching_void.py, organ_34_hojaiga_avatar.py, ai_teaching_assistant.py

---

## Level 3: Hard Tests (Complex Scenarios)

### Test H001: Full Autonomy Task Execution
**Test ID:** H001  
**Difficulty:** Hard  
**Component:** Full System  

**Description:** Test complete autonomous execution of a complex multi-step task.

**Pre-conditions:**
- All core organs are running and healthy
- System is in autonomous mode
- Complex task is defined (e.g., "Research weather in 3 cities and create report")

**Test Steps:**
1. Submit complex task to Brain
2. Monitor task decomposition
3. Verify sub-tasks are assigned to appropriate organs
4. Monitor execution across multiple organs
5. Verify intermediate results are stored
6. Verify final result is aggregated
7. Verify quality checks pass
8. Verify report is generated

**Expected Results:**
- Task is decomposed into logical sub-tasks
- Sub-tasks are assigned correctly
- Execution proceeds without manual intervention
- Intermediate results are coherent
- Final result is complete and accurate
- Quality checks pass
- Report is generated in correct format

**Success Criteria:**
- Full autonomy works end-to-end
- Task decomposition is intelligent
- Multi-organ coordination is seamless
- Result quality is acceptable
- No manual intervention required

**Related Components:** All core organs, organ_01_brain.py, organ_38_task_orchestrator.py

---

### Test H002: Multi-Agent Collaboration
**Test ID:** H002  
**Difficulty:** Hard  
**Component:** organ_10_agents.py + Task Orchestrator  

**Description:** Test collaboration between multiple agents on a shared task.

**Pre-conditions:**
- At least 3 agents are available
- Task orchestrator is running
- Shared task requires multiple skills

**Test Steps:**
1. Define a task requiring multiple agent types (e.g., research + analysis + reporting)
2. Submit task to orchestrator
3. Verify agents are assigned appropriate sub-tasks
4. Monitor inter-agent communication
5. Verify agents share data correctly
6. Verify conflicts are resolved
7. Verify final result integrates all agent contributions

**Expected Results:**
- Agents are assigned based on capabilities
- Inter-agent communication is efficient
- Data sharing is secure and accurate
- Conflicts are resolved automatically
- Final result is coherent

**Success Criteria:**
- Multi-agent collaboration works
- Communication is efficient
- Conflict resolution is effective
- Result quality is high

**Related Components:** organ_10_agents.py, organ_38_task_orchestrator.py, organ_01_crewai_engine.py

---

### Test H003: Vision-to-Action Pipeline
**Test ID:** H003  
**Difficulty:** Hard  
**Component:** Visual Perception + Controllers + Automation  

**Description:** Test complete pipeline from visual input to automated action.

**Pre-conditions:**
- Visual perception is running
- Controllers are available
- Automation system is active
- Test environment is prepared

**Test Steps:**
1. Capture visual input of a UI element (e.g., button)
2. Process image to identify element and location
3. Determine appropriate action (click)
4. Execute action through controller
5. Verify action was performed correctly
6. Verify system state changed as expected

**Expected Results:**
- Visual input is captured clearly
- Element is identified with high confidence (>90%)
- Action is determined correctly
- Action execution is precise
- System state change matches expectation

**Success Criteria:**
- Vision-to-action pipeline works end-to-end
- Accuracy is high enough for practical use
- Action execution is reliable
- System adapts to visual changes

**Related Components:** organ_31_visual_perception.py, organ_05_controllers.py, organ_06_automation.py, intelligent_mouse.py

---

### Test H004: Complex Web Scraping and Analysis
**Test ID:** H004  
**Difficulty:** Hard  
**Component:** Chrome CDP + ScrapeGraphAI + Analysis  

**Description:** Test complex web scraping workflow with data analysis.

**Pre-conditions:**
- Chrome CDP is running
- ScrapeGraphAI organ is available
- Analysis capabilities are ready
- Target website is accessible

**Test Steps:**
1. Navigate to target website
2. Identify data extraction points
3. Extract structured data from multiple pages
4. Clean and normalize extracted data
5. Perform analysis on extracted data
6. Generate insights report

**Expected Results:**
- Navigation completes successfully
- Data extraction points are identified accurately
- Data is extracted from all target pages
- Data cleaning produces consistent format
- Analysis reveals meaningful patterns
- Report is comprehensive and accurate

**Success Criteria:**
- Multi-page scraping works reliably
- Data quality is high
- Analysis is meaningful
- Report generation is automated

**Related Components:** organ_19_chrome_cdp_runtime.py, organ_13_scrapegraphai.py, organ_04_knowledge.py, lead_extractor.py

---

### Test H005: Concurrent Task Execution
**Test ID:** H005  
**Difficulty:** Hard  
**Component:** Task Orchestrator + Multiple Organs  

**Description:** Test system performance under concurrent task load.

**Pre-conditions:**
- System is fully operational
- Multiple organs are available
- System resources are monitored

**Test Steps:**
1. Submit 5 independent tasks simultaneously
2. Monitor resource usage (CPU, memory)
3. Verify all tasks start execution
4. Monitor task progress
5. Verify all tasks complete successfully
6. Verify no deadlocks or race conditions
7. Verify resource usage returns to baseline

**Expected Results:**
- All 5 tasks start within 2 seconds
- Resource usage stays within acceptable limits
- Tasks complete without interference
- No deadlocks occur
- System remains stable throughout
- Resources are freed after completion

**Success Criteria:**
- Concurrent execution works reliably
- Resource management is effective
- No race conditions or deadlocks
- System stability is maintained

**Related Components:** organ_38_task_orchestrator.py, organ_02_cns_single_file.py, all active organs

---

### Test H006: Adaptive Learning from Errors
**Test ID:** H006  
**Difficulty:** Hard  
**Component:** Learning System + Error Catalog  

**Description:** Test system's ability to learn from and adapt to errors.

**Pre-conditions:**
- Learning system is active
- Error catalog is populated
- System has error-prone scenario available

**Test Steps:**
1. Execute a task known to fail
2. Verify error is caught and logged
3. Verify error is analyzed by learning system
4. Verify learning system suggests improvement
5. Apply suggested improvement
6. Re-execute task
7. Verify task now succeeds

**Expected Results:**
- Error is caught with proper categorization
- Error analysis identifies root cause
- Learning system generates actionable improvement
- Improvement is applicable
- Task succeeds after improvement

**Success Criteria:**
- Error learning pipeline works
- Improvements are practical
- System adapts behavior based on learning
- Success rate improves over time

**Related Components:** organ_08_learning.py, organ_25_error_catalog.py, organ_22_decision_engine.py

---

### Test H007: Cross-Modal Reasoning
**Test ID:** H007  
**Difficulty:** Hard  
**Component:** Vision + Language + Knowledge  

**Description:** Test reasoning that combines visual, textual, and knowledge data.

**Pre-conditions:**
- All modal organs are active
- Knowledge base is populated
- Test case requires multi-modal reasoning

**Test Steps:**
1. Provide visual input (image with objects)
2. Provide textual query about the image
3. System should combine visual recognition with knowledge
4. Verify reasoning process uses both modalities
5. Verify answer requires cross-modal synthesis
6. Verify answer is accurate and comprehensive

**Expected Results:**
- Visual input is processed correctly
- Textual query is understood
- Knowledge base is queried for relevant context
- Reasoning combines all modalities
- Answer demonstrates synthesis of information

**Success Criteria:**
- Cross-modal reasoning works
- Information from different sources is integrated
- Reasoning quality is high
- Answers are comprehensive

**Related Components:** organ_31_visual_perception.py, organ_14_llm_runtime_single_file.py, organ_04_knowledge.py

---

### Test H008: Complex Workflow with Branching
**Test ID:** H008  
**Difficulty:** Hard  
**Component:** Workflow Compiler + Decision Engine  

**Description:** Test execution of complex workflow with conditional branching.

**Pre-conditions:**
- Workflow compiler is available
- Decision engine is active
- Complex workflow with branches is defined

**Test Steps:**
1. Define workflow with multiple branches based on conditions
2. Submit workflow for execution
3. Trigger condition that takes Path A
4. Verify execution follows Path A
5. Reset and trigger condition for Path B
6. Verify execution follows Path B
7. Verify both paths produce valid but different results

**Expected Results:**
- Workflow is compiled correctly
- Conditions are evaluated accurately
- Path A executes correctly when condition A is met
- Path B executes correctly when condition B is met
- Results are appropriate for each path

**Success Criteria:**
- Branching logic works correctly
- Conditions are evaluated properly
- Different paths produce expected different outcomes
- Workflow remains stable under different conditions

**Related Components:** organ_36_workflow_compiler.py, organ_22_decision_engine.py, organ_38_task_orchestrator.py

---

### Test H009: System State Recovery
**Test ID:** H009  
**Difficulty:** Hard  
**Component:** Recovery Coordinator + Backup Manager  

**Description:** Test system recovery from a critical failure state.

**Pre-conditions:**
- System is running normally
- Backup manager is active
- Recovery coordinator is monitoring
- System state is backed up

**Test Steps:**
1. Create a critical failure (e.g., crash Brain organ)
2. Verify failure is detected
3. Verify recovery coordinator initiates recovery
4. Verify backup is restored
5. Verify system restarts failed organ
6. Verify system state matches pre-failure state
7. Verify ongoing operations can resume

**Expected Results:**
- Failure is detected within 5 seconds
- Recovery process starts automatically
- Backup restoration is successful
- Organ restart succeeds
- System state is consistent
- Operations can resume

**Success Criteria:**
- Critical failure recovery works
- Data loss is minimized
- System returns to consistent state
- Recovery time is acceptable (< 30 seconds)

**Related Components:** centralized_recovery_coordinator.py, organ_17_backup_manager.py, organ_01_brain.py

---

### Test H010: Long-Running Task Persistence
**Test ID:** H010  
**Difficulty:** Hard  
**Component:** Task Orchestrator + Memory + State Catalog  

**Description:** Test persistence and resumption of long-running tasks.

**Pre-conditions:**
- Task orchestrator is running
- Memory and state catalog are active
- Long-running task is defined

**Test Steps:**
1. Start a long-running task (e.g., 10-step analysis)
2. Let task complete 3 steps
3. Interrupt task (simulate system restart)
4. Restart system
5. Verify task state is persisted
6. Resume task from step 4
7. Verify task completes successfully
8. Verify final result is correct

**Expected Results:**
- Task starts and progresses normally
- Task state is saved after each step
- State persists across restart
- Task resumes from correct point
- No steps are repeated or skipped
- Final result is complete

**Success Criteria:**
- Task persistence works reliably
- State restoration is accurate
- No data corruption occurs
- Task can be resumed seamlessly

**Related Components:** organ_38_task_orchestrator.py, organ_03_memory.py, organ_32_state_catalog.py

---

## Level 4: Expert Tests (Edge Cases & Stress)

### Test X001: Maximum Concurrent Load
**Test ID:** X001  
**Difficulty:** Expert  
**Component:** Full System  

**Description:** Stress test system under maximum concurrent load.

**Pre-conditions:**
- System is fully operational
- Monitoring tools are active
- Resource limits are known

**Test Steps:**
1. Gradually increase concurrent task load from 10 to 100 tasks
2. Monitor system response time at each level
3. Monitor resource utilization
4. Identify breaking point
5. Record performance metrics
6. Reduce load and verify system recovers

**Expected Results:**
- System handles increasing load up to a point
- Response time degrades gracefully
- Resource utilization scales appropriately
- Breaking point is identified
- System recovers when load is reduced

**Success Criteria:**
- System handles at least 50 concurrent tasks
- No catastrophic failures occur
- Performance degradation is predictable
- Recovery from overload is possible

**Related Components:** All organs, monitoring systems

---

### Test X002: Network Partition Resilience
**Test ID:** X002  
**Difficulty:** Expert  
**Component:** CNS + Network Layer  

**Description:** Test system behavior during network partitions between organs.

**Pre-conditions:**
- System is distributed across multiple processes
- Network can be artificially partitioned
- Monitoring is active

**Test Steps:**
1. Identify critical communication paths
2. Partition network between Brain and Memory
3. Verify system detects partition
4. Verify appropriate fallback behavior
5. Verify no data corruption
6. Restore network
7. Verify system resynchronizes

**Expected Results:**
- Partition is detected within timeout period
- System enters degraded mode gracefully
- Fallback behavior prevents data loss
- Reconnection triggers resynchronization
- System returns to normal operation

**Success Criteria:**
- Network partitions are handled gracefully
- Data consistency is maintained
- System can recover from partitions
- No split-brain scenarios occur

**Related Components:** organ_02_cns_single_file.py, organ_03_memory.py, network layer

---

### Test X003: Malicious Input Handling
**Test ID:** X003  
**Difficulty:** Expert  
**Component:** Security + All Input Points  

**Description:** Test system resilience against malicious inputs.

**Pre-conditions:**
- Security organ is active
- All input points are identified
- Malicious test cases are prepared

**Test Steps:**
1. Submit SQL injection attempts through various inputs
2. Submit command injection attempts
3. Submit malformed data structures
4. Submit oversized payloads
5. Submit specially crafted unicode strings
6. Verify all attempts are blocked or sanitized
7. Verify system remains stable

**Expected Results:**
- All malicious inputs are detected
- No SQL injection succeeds
- No command injection succeeds
- Malformed data is rejected or handled
- Oversized payloads are limited
- System remains stable throughout

**Success Criteria:**
- Security layer blocks all attack vectors
- No privilege escalation occurs
- No data corruption occurs
- System availability is maintained

**Related Components:** organ_07_security.py, Brain_Gatekeeper.py, all input handlers

---

### Test X004: Resource Exhaustion Recovery
**Test ID:** X004  
**Difficulty:** Expert  
**Component:** Full System  

**Description:** Test system recovery from resource exhaustion scenarios.

**Pre-conditions:**
- System monitoring is active
- Resource exhaustion can be simulated
- Recovery mechanisms are in place

**Test Steps:**
1. Simulate memory exhaustion (consume available RAM)
2. Verify system detects memory pressure
3. Verify appropriate cleanup occurs
4. Simulate disk space exhaustion
5. Verify system handles disk full condition
6. Simulate CPU exhaustion
7. Verify system remains responsive
8. Restore resources and verify recovery

**Expected Results:**
- Resource exhaustion is detected
- System initiates cleanup/conservation
- Critical operations continue
- Appropriate errors are returned
- System recovers when resources available

**Success Criteria:**
- System handles resource pressure gracefully
- No data loss occurs
- Recovery is automatic
- System remains stable

**Related Components:** All organs, resource managers

---

### Test X005: Temporal Edge Cases
**Test ID:** X005  
**Difficulty:** Expert  
**Component:** Task Orchestrator + Scheduling  

**Description:** Test system behavior with temporal edge cases (time jumps, deadlines, etc.).

**Pre-conditions:**
- Task scheduling is active
- System time can be manipulated
- Deadline handling is implemented

**Test Steps:**
1. Schedule tasks with strict deadlines
2. Jump system time forward past deadlines
3. Verify missed deadline handling
4. Jump system time backward
5. Verify temporal consistency
6. Schedule tasks with zero-duration windows
7. Verify handling of impossible schedules

**Expected Results:**
- Deadlines are detected when missed
- Appropriate actions are taken for missed deadlines
- Time jumps don't corrupt state
- Impossible schedules are rejected or handled
- Temporal logic remains consistent

**Success Criteria:**
- Temporal edge cases are handled correctly
- No state corruption from time anomalies
- Deadline handling is robust
- System remains consistent

**Related Components:** organ_38_task_orchestrator.py, scheduling systems

---

### Test X006: Data Corruption Scenarios
**Test ID:** X006  
**Difficulty:** Expert  
**Component:** Memory + Database + Backup  

**Description:** Test system resilience to data corruption scenarios.

**Pre-conditions:**
- Backup system is active
- Data corruption can be simulated
- Integrity checks are in place

**Test Steps:**
1. Corrupt memory data structure
2. Verify integrity check detects corruption
3. Verify backup is restored
4. Corrupt database records
5. Verify database recovery mechanisms
6. Corrupt configuration files
7. Verify fallback to default configuration
8. Verify system remains operational

**Expected Results:**
- Corruption is detected by integrity checks
- Appropriate recovery is initiated
- Backups are successfully restored
- Fallback mechanisms work
- System continues with degraded or full functionality

**Success Criteria:**
- Data corruption is detected reliably
- Recovery mechanisms work
- System can continue operating
- Data loss is minimized

**Related Components:** organ_03_memory.py, database_manager.py, organ_17_backup_manager.py

---

### Test X007: Concurrent Write Conflicts
**Test ID:** X007  
**Difficulty:** Expert  
**Component:** Memory + CNS + Multi-Agent  

**Description:** Test handling of concurrent write conflicts to shared resources.

**Pre-conditions:**
- Shared memory resources exist
- Multiple agents can write simultaneously
- Conflict resolution is implemented

**Test Steps:**
1. Have 5 agents simultaneously write to same memory location
2. Verify conflict detection
3. Verify conflict resolution strategy
4. Verify final state is consistent
5. Test with different conflict resolution strategies
6. Verify no data loss occurs
7. Verify system performance under conflict load

**Expected Results:**
- Conflicts are detected reliably
- Resolution strategy is applied consistently
- Final state is valid and consistent
- No data is lost
- System remains responsive

**Success Criteria:**
- Concurrent writes are handled correctly
- Conflict resolution is effective
- Data integrity is maintained
- Performance remains acceptable

**Related Components:** organ_03_memory.py, organ_02_cns_single_file.py, organ_10_agents.py

---

### Test X008: Legacy Code Integration
**Test ID:** X008  
**Difficulty:** Expert  
**Component:** Integration Layer + Legacy Components  

**Description:** Test integration with legacy code components.

**Pre-conditions:**
- Legacy code components exist
- Integration layer is implemented
- Compatibility shims are available

**Test Steps:**
1. Identify legacy components requiring integration
2. Test integration layer with each legacy component
3. Verify data format translation
4. Verify protocol compatibility
5. Test error handling for legacy failures
6. Verify performance impact is acceptable
7. Verify legacy components don't destabilize system

**Expected Results:**
- Legacy components integrate successfully
- Data translation is accurate
- Protocol compatibility is maintained
- Legacy failures are isolated
- System remains stable

**Success Criteria:**
- Legacy integration works reliably
- No system destabilization
- Performance impact is minimal
- Errors are handled gracefully

**Related Components:** organ_12_integration.py, organ_13_interface_layer.py, legacy components

---

### Test X009: Cascade Failure Prevention
**Test ID:** X009  
**Difficulty:** Expert  
**Component:** Full System + Circuit Breakers  

**Description:** Test prevention of cascade failures across organs.

**Pre-conditions:**
- Circuit breakers are implemented
- Failure propagation paths are known
- Monitoring is active

**Test Steps:**
1. Trigger failure in critical organ (e.g., Brain)
2. Verify circuit breaker prevents propagation
3. Verify dependent organs fail gracefully
4. Verify system maintains partial functionality
5. Test different failure scenarios
6. Verify no cascade occurs
7. Verify recovery is possible

**Expected Results:**
- Circuit breakers trigger appropriately
- Failure is contained
- System maintains degraded functionality
- No cascade failure occurs
- Recovery is organized and controlled

**Success Criteria:**
- Cascade failures are prevented
- System maintains partial functionality
- Recovery is possible
- No systemic collapse

**Related Components:** All organs, circuit breakers, centralized_recovery_coordinator.py

---

### Test X010: Zero-Knowledge State Restoration
**Test ID:** X010  
**Difficulty:** Expert  
**Component:** Backup + Recovery + State Catalog  

**Description:** Test complete system restoration from backup with no prior state knowledge.

**Pre-conditions:**
- Complete system backup exists
- System can be completely reset
- Restoration procedure is documented

**Test Steps:**
1. Completely shut down system
2. Clear all local state and memory
3. Start system from cold boot
4. Initiate restoration from backup
5. Verify all organs are restored
6. Verify system state matches backup snapshot
7. Verify operations can resume immediately
8. Verify no data loss occurred

**Expected Results:**
- Cold boot succeeds
- Restoration process completes
- All organs are in correct state
- System state is consistent with backup
- Operations resume normally
- No data is lost or corrupted

**Success Criteria:**
- Complete restoration is possible
- State consistency is maintained
- No manual intervention required
- Restoration time is acceptable

**Related Components:** organ_17_backup_manager.py, organ_32_state_catalog.py, centralized_recovery_coordinator.py

---

## Test Execution Guidelines

### General Principles
1. **Progressive Testing**: Execute tests in order (E001 -> E010, M001 -> M010, etc.)
2. **Environment Consistency**: Maintain consistent test environment across runs
3. **Result Logging**: Log all test results with timestamps and system state
4. **Failure Analysis**: Analyze failures thoroughly before proceeding
5. **Regression Prevention**: Re-run previously passed tests after modifications

### Success Metrics
- **Easy Level**: 90% pass rate required
- **Medium Level**: 80% pass rate required
- **Hard Level**: 70% pass rate required
- **Expert Level**: 60% pass rate required

### Test Automation
Where possible, automate test execution using:
- Python test frameworks (pytest, unittest)
- Continuous integration pipelines
- Automated result reporting
- Performance benchmarking

### Continuous Improvement
- Review and update test cases regularly
- Add new test cases for discovered edge cases
- Refine success criteria based on real-world usage
- Maintain test documentation alongside code changes

---

## Appendix A: Organ Dependencies

### Core Organs
- **organ_01_brain.py**: Central decision-making, depends on all other organs
- **organ_02_cns_single_file.py**: Event bus, critical for all communication
- **organ_03_memory.py**: Storage, depended upon by most organs
- **organ_04_knowledge.py**: Information retrieval, used by Brain and Learning

### Runtime Organs
- **organ_05_controllers.py**: Action execution, depends on Brain and CNS
- **organ_06_automation.py**: Automation workflows, depends on Controllers and Task Orchestrator
- **organ_07_security.py**: Security validation, called by all organs before sensitive operations

### Advanced Organs
- **organ_08_learning.py**: Machine learning, depends on Memory and Knowledge
- **organ_10_agents.py**: Agent management, depends on Task Orchestrator and CNS
- **organ_19_chrome_cdp_runtime.py**: Browser automation, depends on Controllers
- **organ_38_task_orchestrator.py**: Task management, central coordinator for workflows

---

## Appendix B: Common Test Scenarios

### Scenario 1: Cold Start
- Start all organs from stopped state
- Verify each organ initializes correctly
- Verify system reaches operational state

### Scenario 2: Graceful Shutdown
- Initiate shutdown sequence
- Verify all organs save state
- Verify clean termination

### Scenario 3: Hot Reload
- Update organ code while system running
- Verify organ reloads without system restart
- Verify continued operation

### Scenario 4: Resource Scaling
- Monitor resource usage during normal operation
- Add load and verify scaling behavior
- Remove load and verify resource release

---

## Conclusion

This training dataset provides a comprehensive progression from basic functionality tests to expert-level stress and edge case scenarios. Each test is designed to validate specific aspects of the Hojaiga system while building confidence in system reliability and robustness.

**Key Benefits:**
- Progressive difficulty allows for incremental validation
- Coverage spans individual organs to full system integration
- Edge cases and stress tests ensure production readiness
- Clear success criteria enable automated validation

**Maintenance Notes:**
- Review and update test cases quarterly
- Add new tests for system enhancements
- Retire tests for deprecated functionality
- Maintain test documentation alongside system evolution

---

**Document Version:** 1.0  
**Last Updated:** 2026-09-29  
**Maintained By:** Hojaiga Development Team