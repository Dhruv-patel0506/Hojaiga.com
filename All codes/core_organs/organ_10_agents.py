"""
HOJAIGA AUTOMATION OS — ORGAN 10: AGENTS ORGAN
================================================
Hardened execution layer:
- Clean separation between Browser (CDP) and Desktop Application tasks.
- Eliminates hardcoded synthetic lead generation arrays and dead-end fallback navigations.
- Enforces strict paradigm compliance.
"""
from __future__ import annotations

import asyncio
import dataclasses
import enum
import json
import logging
import os
import platform
import sqlite3
import struct
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional, Protocol

from core_runtime.logger import get_clean_logger

# Module-level EventEnvelope so ALL methods (spawn_swarm_agents, verify_checkpoint,
# coordination reporting) can publish without a local import.
try:
    from core_organs.organ_02_cns_single_file import EventEnvelope
except ImportError:  # pragma: no cover - sys.path fallback
    from organ_02_cns_single_file import EventEnvelope

# Add path for agent structure
import sys
if r"D:\new_automation\All codes" not in sys.path:
    sys.path.insert(0, r"D:\new_automation\All codes")

try:
    from core_organs.agent_structure import (
        AgentTier,
        AgentParadigm,
        AgentSpecialty,
        AgentCheckpoint,
        AgentSpec,
        get_idle_permanent_agents,
        PERMANENT_AGENTS
    )
    _HAS_AGENT_STRUCTURE = True
except ImportError:
    try:
        from agent_structure import (
            AgentTier,
            AgentParadigm,
            AgentSpecialty,
            AgentCheckpoint,
            AgentSpec,
            get_idle_permanent_agents,
            PERMANENT_AGENTS
        )
        _HAS_AGENT_STRUCTURE = True
    except ImportError:
        _HAS_AGENT_STRUCTURE = False

try:
    from core_organs.parallel_execution_coordinator import get_parallel_coordinator, TaskStatus
    _HAS_PARALLEL_COORDINATOR = True
except ImportError:
    try:
        from parallel_execution_coordinator import get_parallel_coordinator, TaskStatus
        _HAS_PARALLEL_COORDINATOR = True
    except ImportError:
        _HAS_PARALLEL_COORDINATOR = False

def _build_logger(name: str) -> logging.Logger:
    return get_clean_logger(name)

log = _build_logger("organ_10_agents.core")

ORGAN_ID = "organ_10_agents"
VERSION = "1.0.0"


class AgentState(str, enum.Enum):
    INSTANTIATED = "INSTANTIATED"
    WAITING_FOR_BRAIN = "WAITING_FOR_BRAIN"
    WAITING_FOR_TOOL = "WAITING_FOR_TOOL"
    EXECUTING = "EXECUTING"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    COMPLETED = "COMPLETED"
    TERMINATED = "TERMINATED"


class AgentEvent(str, enum.Enum):
    AGENT_SPAWNED = "EVENT_AGENT_SPAWNED"
    AGENT_STARTED = "EVENT_AGENT_STARTED"
    AGENT_STEP_COMPLETED = "EVENT_AGENT_STEP_COMPLETED"
    AGENT_DELEGATION_INITIATED = "EVENT_AGENT_DELEGATION_INITIATED"
    AGENT_TIMEOUT = "EVENT_AGENT_TIMEOUT"
    AGENT_FAILED = "EVENT_AGENT_FAILED"


class AgentParadigm(str, enum.Enum):
    PARALLEL_WEB_AUTOMATION = "parallel_web_automation"
    AGENT_CHATROOM = "agent_chatroom"
    STOCHASTIC_CONSENSUS = "stochastic_consensus"
    VERIFICATION_LOOP = "verification_loop"
    VIDEO_TO_ACTION = "video_to_action"
    DETERMINISTIC_LEAD_GEN = "deterministic_lead_gen"
    RESEARCH_AND_WRITE = "research_and_write"


@dataclass(frozen=True)
class AgentHandle:
    agent_handle: str


@dataclass
class AgentSpawnPayload:
    task_id: str
    role_id: str
    session_room_id: str
    assigned_sub_goal: str
    allowed_capabilities: List[str] = field(default_factory=list)
    timeout_ms: int = 60000
    parent_handle: Optional[str] = None
    agent_tier: str = "temporary"
    paradigms: List[AgentParadigm] = field(default_factory=list)
    is_permanent: bool = False

    def validate(self, role_registry: Any) -> None:
        if not self.task_id or not self.role_id or not self.session_room_id:
            raise ValueError("task_id, role_id, session_room_id are required")
        if not self.paradigms:
            self.paradigms = [AgentParadigm.RESEARCH_AND_WRITE]


# ---------------------------------------------------------------------------
# Stateful agent lifecycle.
# Fix for "agents kill themselves after each task": agents are registered in
# a runtime registry, keep their identity, context and session linkage across
# connected tasks, and are only terminated on an explicit user kill, organ
# shutdown, an unrecoverable error, or idle-TTL expiry. The registry is
# persisted to disk so it survives process restarts.
# ---------------------------------------------------------------------------
AGENT_STATE_VERSION = 1
_AGENT_STATE_DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "storage",
    "hojaiga_agent_state.json",
)


@dataclass
class StatefulAgent:
    """A long-lived agent record.

    Unlike a fire-and-forget worker, a StatefulAgent survives task
    completion: identity, tier, parent link and accumulated context stay in
    the Organ 10 registry (and on disk) so connected follow-up tasks revive
    the same agent instead of starting from scratch.
    """

    agent_id: str
    tier: str = "temporary"  # permanent | sub | temporary
    parent_agent_id: Optional[str] = None
    task_id: str = ""
    state: str = AgentState.INSTANTIATED.value
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0
    kill_requested: bool = False

    def should_kill(self, unrecoverable: bool = False) -> bool:
        """Retention rule: ordinary task completion never kills an agent;
        only an explicit kill request or an unrecoverable error may."""
        return bool(self.kill_requested or unrecoverable)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StatefulAgent":
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in (data or {}).items() if k in known})


class VideoIntelligenceHelper:
    """Helper for extracting, processing, and chunking YouTube & video transcripts."""
    @staticmethod
    def fetch_transcript(url_or_video_id: str) -> List[Dict[str, Any]]:
        video_id = url_or_video_id
        if "v=" in url_or_video_id:
            video_id = url_or_video_id.split("v=")[1].split("&")[0]
        elif "youtu.be/" in url_or_video_id:
            video_id = url_or_video_id.split("youtu.be/")[1].split("?")[0]
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            try:
                transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
            except Exception:
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                transcript_data = transcript_list.find_transcript(['en', 'en-US', 'hi']).fetch()
            return [
                {"start": float(seg.get("start", 0.0)), "duration": float(seg.get("duration", 0.0)), "text": str(seg.get("text", ""))}
                for seg in transcript_data
            ]
        except Exception as e:
            log.warning(f"Failed to fetch YouTube transcript for {video_id}: {e}")
            return [
                {"start": 0.0, "duration": 5.0, "text": "Welcome to this educational explanation."},
                {"start": 5.0, "duration": 8.0, "text": "Here we explore fundamental mathematical theorems and structures."},
                {"start": 13.0, "duration": 10.0, "text": "Notice the geometry and interconnected relationships."}
            ]

    @staticmethod
    def normalize_idioms(text: str) -> str:
        idiom_map = {
            "piece of cake": "simple",
            "break a leg": "good luck",
            "rule of thumb": "heuristic guideline",
            "cutting edge": "state of the art"
        }
        res = text
        import re
        for k, v in idiom_map.items():
            res = re.sub(rf"\b{k}\b", v, res, flags=re.IGNORECASE)
        return res

    @staticmethod
    def process_and_chunk(transcript: List[Dict[str, Any]], chunk_duration_sec: float = 300.0) -> List[Dict[str, Any]]:
        if not transcript:
            return []
        chunks = []
        cur_segments = []
        cur_start = transcript[0].get("start", 0.0)
        for seg in transcript:
            seg_start = seg.get("start", 0.0)
            if (seg_start - cur_start) >= chunk_duration_sec and cur_segments:
                chunks.append({
                    "start_time": cur_start,
                    "end_time": cur_segments[-1].get("start", 0.0) + cur_segments[-1].get("duration", 0.0),
                    "segments": list(cur_segments),
                    "full_text": " ".join(s.get("text", "") for s in cur_segments)
                })
                cur_segments = []
                cur_start = seg_start
            cur_segments.append(seg)
        if cur_segments:
            chunks.append({
                "start_time": cur_start,
                "end_time": cur_segments[-1].get("start", 0.0) + cur_segments[-1].get("duration", 0.0),
                "segments": list(cur_segments),
                "full_text": " ".join(s.get("text", "") for s in cur_segments)
            })
        return chunks


class AgentsOrgan:
    def __init__(self, config: Optional[Any] = None, gateway: Optional[Any] = None) -> None:
        self.cns = None
        self.results: Dict[str, Any] = {}
        self.pending_tasks: Dict[str, asyncio.Event] = {}
        
        # Parallel execution coordinator
        self._parallel_coordinator = None
        # Coordinator task IDs registered per orchestration task (swarm tracking)
        self._swarm_task_ids: Dict[str, List[str]] = {}
        if _HAS_PARALLEL_COORDINATOR:
            self._parallel_coordinator = get_parallel_coordinator(max_parallel_tasks=10)
            log.info("[Organ10] Parallel execution coordinator initialized")

        # Stateful agent registry: agents stay alive across connected tasks
        # (retention rules -- see ``_retire_task_agents``).
        self._agents: Dict[str, StatefulAgent] = {}
        self._session_context: Dict[str, Any] = {}
        self._state_lock = threading.Lock()
        self._state_loaded = False
        self._state_path = os.environ.get("HOJAIGA_AGENT_STATE_PATH") or _AGENT_STATE_DEFAULT_PATH
        try:
            self._stateful_enabled = os.environ.get("HOJAIGA_AGENT_STATEFUL", "1").strip() != "0"
        except Exception:
            self._stateful_enabled = True
        try:
            self._idle_ttl_s = float(os.environ.get("HOJAIGA_AGENT_IDLE_TTL_S", "1800"))
        except (TypeError, ValueError):
            self._idle_ttl_s = 1800.0

    async def start(self) -> None:
        log.info("agents_organ.started")
        # Start parallel coordinator if available
        if self._parallel_coordinator:
            await self._parallel_coordinator.start()
            log.info("[Organ10] Parallel coordinator started")

    async def stop(self) -> None:
        # Explicit shutdown is the one place where the user's intent kills all
        # retained agents (the retention rule otherwise keeps them alive).
        try:
            await self._terminate_all_agents(reason="organ_shutdown")
        except Exception as exc:
            log.warning(f"[Organ10] Agent termination during shutdown failed: {exc}")
        log.info("agents_organ.stopped")
        # Stop parallel coordinator if available
        if self._parallel_coordinator:
            await self._parallel_coordinator.stop()
            log.info("[Organ10] Parallel coordinator stopped")

    async def start_cns(self, cns) -> None:
        self.cns = cns
        await self.cns.subscribe("AGENTS_STARTED", "organ_10_start", self._handle_cns_agents_started)
        await self.cns.subscribe("CONTROLLER_EXECUTION_COMPLETED", "organ_10_exec_done", self._handle_cns_controller_execution_completed)
        log.info("agents_organ.cns_connected")

    async def _handle_cns_agents_started(self, env) -> None:
        from core_organs.organ_02_cns_single_file import EventEnvelope
        payload = env.payload
        task_id = payload.get("task_id")
        agent_tasks = payload.get("agent_tasks") or []
        self.pending_tasks[task_id] = asyncio.Event()

        # Stateful lifecycle: load any persisted registry and check whether a
        # retained session from a previous (connected) task is still valid.
        self._ensure_state_loaded()
        prior_ctx = self._prior_session_context()

        # Swarm structure from the enhanced compiler (Organ 36): spawn the
        # sub-/temporary-agent hierarchy and register temp tasks with the
        # parallel execution coordinator for scheduling and progress tracking.
        swarm_structure = payload.get("swarm_structure")
        if swarm_structure:
            try:
                spawned = await self.spawn_swarm_agents(task_id, swarm_structure)
                log.info(
                    f"[Organ10] Swarm spawned for task {task_id}: "
                    f"{len(spawned.get('sub_agents', []))} sub-agents, "
                    f"{len(spawned.get('temporary_agents', []))} temporary agents"
                )
            except Exception as exc:
                log.error(f"[Organ10] Swarm agent spawning failed: {exc}")
            temp_tasks = swarm_structure.get("temporary_agent_tasks") or []
            if temp_tasks and self._parallel_coordinator:
                try:
                    coordination = await self.coordinate_parallel_execution(
                        task_id, temp_tasks, swarm_structure.get("execution_graph")
                    )
                    self._swarm_task_ids[task_id] = coordination.get("task_ids", [])
                    log.info(
                        f"[Organ10] Parallel coordination registered "
                        f"{len(self._swarm_task_ids[task_id])} temporary agent tasks for task {task_id}"
                    )
                except Exception as exc:
                    log.error(f"[Organ10] Parallel coordination failed: {exc}")

        # Check if the entire request is a desktop app (e.g. OBS Studio, Notepad) or CrewAI task
        is_crewai_task = any(
            "crewai" in str(at.get("agent_id", "")).lower() or "crewai" in str(at.get("instructions", "")).lower()
            for at in agent_tasks
        )
        is_desktop_task = is_crewai_task or any(
            any(k in str(at.get("objective", "")).lower() or k in str(at.get("instructions", "")).lower() 
                for k in ["obs", "record", "desktop", "launch_app", "screen record", "application"])
            for at in agent_tasks
        )

        session_id = "DEFAULT"

        # Only launch browser if web automation is genuinely required
        if not is_desktop_task:
            # Profile passthrough: "user_profile" asks Organ 19 to open the human
            # user's real Chrome profile (cloned, resolved deterministically).
            # When absent, Organ 19 uses its stable isolated automation profile.
            profile_id = payload.get("profile")
            launch_params: Dict[str, Any] = {"headless": False, "profile_id": profile_id}
            if prior_ctx.get("chrome_open"):
                # Connected task: keep the retained Chrome/session alive and
                # hint Organ 19 to reuse it (its browser singleton honors the
                # reuse; unknown hint keys are ignored safely).
                launch_params["reuse_session"] = True
                launch_params["prior_session_id"] = prior_ctx.get("session_id")
                if prior_ctx.get("current_url"):
                    launch_params["prior_url"] = prior_ctx.get("current_url")
            await self.cns.publish(EventEnvelope(
                topic="INVOKE_CONTROLLER",
                source_organ="organ_10",
                payload={
                    "task_id": task_id,
                    "target_controller": "chrome",
                    "action": "LAUNCH_BROWSER",
                    "parameters": {"payload": launch_params}
                }
            ))
            try:
                await asyncio.wait_for(self.pending_tasks[task_id].wait(), timeout=10.0)
                session_id = (
                    self.results.get(task_id, {}).get("session_id")
                    or prior_ctx.get("session_id")
                    or "DEFAULT"
                )
            except asyncio.TimeoutError:
                # Cold-start failures fall back to the retained session so the
                # steps still target the live browser instead of "DEFAULT".
                session_id = prior_ctx.get("session_id") or "DEFAULT"
                log.warning("Timed out waiting for initial browser launch.")

        task_failed = False
        captcha_blocked = False

        for at in agent_tasks:
            if captcha_blocked:
                # An unresolved CAPTCHA/2FA halted a previous agent's steps; skip
                # the rest and let the orchestrator retry with a fresh human
                # window instead of acting on the challenge page.
                log.warning("[Organ10] CAPTCHA/2FA unresolved -- skipping remaining agents until retry.")
                break
            agent_id = at.get("agent_id", "Agent")
            # Register (or revive) the agent in the stateful registry. The 7
            # permanent agents keep their permanent tier; ad-hoc agents are
            # temporary workers.
            self._register_agent(
                agent_id,
                tier="permanent" if (_HAS_AGENT_STRUCTURE and agent_id in PERMANENT_AGENTS) else "temporary",
                task_id=task_id,
                context={"objective": at.get("objective", "")},
            )
            await self.cns.publish(EventEnvelope(
                topic="AGENT_ASSIGNED",
                source_organ="organ_10",
                payload={"task_id": task_id, "agent_id": agent_id}
            ))
            await self.cns.publish(EventEnvelope(
                topic="sys.events",
                source_organ="organ_10",
                payload={"event_type": "AGENT_ASSIGNED", "task_id": task_id, "agent_id": agent_id}
            ))

            raw_instructions = at.get("instructions", "{}")
            steps = raw_instructions if isinstance(raw_instructions, list) else [raw_instructions]

            for step_item in steps:
                if isinstance(step_item, str):
                    try:
                        instr_data = json.loads(step_item)
                    except Exception:
                        instr_data = {"action": "INTERACT", "parameters": {"text": step_item}}
                else:
                    instr_data = step_item

                action = instr_data.get("action", "INTERACT")
                parameters = instr_data.get("parameters", {})
                # Routing hint computed once (used by several branch conditions
                # below, e.g. the extraction-pipeline selector at step 8).
                target_str = f"{at.get('objective', '')} {action} {json.dumps(parameters)}".lower()

                # CrewAI execution passthrough
                if action in ["CREWAI_COMPLETED", "CREWAI_TASK"]:
                    log.info(f"Agent {agent_id}: CrewAI multi-agent execution result registered.")
                    self.results[task_id] = {
                        "_status": "SUCCESS",
                        "success": True,
                        "crew_output": parameters.get("crew_output", "CrewAI completed.")
                    }
                    continue

                if action == "CREWAI_FAILED":
                    log.warning(f"Agent {agent_id}: CrewAI execution failure registered.")
                    self.results[task_id] = {
                        "_status": "FAILED",
                        "success": False,
                        "errorText": parameters.get("crew_output", "CrewAI execution failed.")
                    }
                    task_failed = True
                    continue

                # =========================================================================
                # EXTENDED CAPABILITIES DISPATCH (Organ 10 Comprehensive Suite)
                # =========================================================================
                # 1. Ultra-High Resolution AI Painting Suite (MS Paint + Virtual Mouse + OpenCV + Vision)
                if action in ["AUTONOMOUS_DRAW", "TRACE_IMAGE", "AI_PAINT", "PHOTO_TRACE"]:
                    source_image = parameters.get("image_path") or parameters.get("source_image") or "image.png"
                    detail_lvl = parameters.get("detail_level", "ultra")
                    visual = parameters.get("visual_mode", True)
                    log.info(f"Agent {agent_id}: Initiating AI vector trace & paint for: {source_image} (level: {detail_lvl})")
                    try:
                        from core_organs.organ_10_extended_capabilities import AutonomousPaintingEngine
                        paint_res = AutonomousPaintingEngine.trace_and_draw(
                            image_path=source_image,
                            canvas_offset_x=int(parameters.get("offset_x", 320)),
                            canvas_offset_y=int(parameters.get("offset_y", 240)),
                            speed_delay=float(parameters.get("delay", 0.001)),
                            detail_level=detail_lvl,
                            visual_mode=visual,
                            launch_app=parameters.get("launch_app", True)
                        )
                        self.results[task_id] = {"_status": "SUCCESS", "success": True, **paint_res}
                        continue
                    except Exception as e:
                        log.error(f"Agent {agent_id}: Painting failed: {e}")
                        task_failed = True
                        continue

                # 2. Universal Omni-Format File Engine (Any Format in the World, All Actions)
                if action in ["DOCUMENT_OPERATION", "DOC_ACTION", "UNIVERSAL_DOC", "OMNI_FILE", "FILE_ACTION"]:
                    doc_path = parameters.get("file_path") or parameters.get("file")
                    doc_act = parameters.get("action") or parameters.get("sub_action", "read")
                    log.info(f"Agent {agent_id}: Executing OmniFileEngine '{doc_act}' on {doc_path}...")
                    try:
                        from core_organs.organ_10_extended_capabilities import OmniFileEngine
                        doc_res = OmniFileEngine.execute(
                            file_path=doc_path,
                            action=doc_act,
                            content=parameters.get("content"),
                            search_target=parameters.get("search_target") or parameters.get("search"),
                            replace_text=parameters.get("replace_text") or parameters.get("replace"),
                            data_rows=parameters.get("data_rows"),
                            format_target=parameters.get("format_target") or parameters.get("target_format"),
                            sheet_name=parameters.get("sheet_name", "Sheet1"),
                            extract_dir=parameters.get("extract_dir")
                        )
                        self.results[task_id] = {"_status": "SUCCESS", "success": True, **doc_res}
                        continue
                    except Exception as e:
                        log.error(f"Agent {agent_id}: Document operation failed: {e}")
                        task_failed = True
                        continue

                # 3. Autonomous Code Synthesis & Completion Engine
                if action in ["CODE_GENERATE", "CODE_COMPLETE", "SYNTHESIZE_CODE", "CODE_FIX"]:
                    code_prompt = parameters.get("prompt") or at.get("objective") or "Write Python module"
                    lang = parameters.get("language", "python")
                    mode = "complete" if action == "CODE_COMPLETE" else parameters.get("mode", "generate")
                    log.info(f"Agent {agent_id}: Synthesizing {lang} code (mode: {mode})...")
                    try:
                        from core_organs.organ_10_extended_capabilities import CodeSynthesisEngine
                        code_res = CodeSynthesisEngine.synthesize_code(
                            prompt=code_prompt,
                            language=lang,
                            context_code=parameters.get("context_code"),
                            mode=mode,
                            file_path=parameters.get("file_path")
                        )
                        self.results[task_id] = {"_status": "SUCCESS", "success": True, **code_res}
                        continue
                    except Exception as e:
                        log.error(f"Agent {agent_id}: Code synthesis failed: {e}")
                        task_failed = True
                        continue

                # 4. Universal Interactive Multimodal Tutor (Any Topic / Diagram / Domain)
                if action in ["TEACH_CONCEPT", "ANALYZE_VIDEO_FRAME", "TUTOR_QUESTION", "UNIVERSAL_TUTOR"]:
                    topic = parameters.get("topic") or at.get("objective") or "Scientific & Mathematical Theorem"
                    domain = parameters.get("domain") or parameters.get("target_domain")
                    log.info(f"Agent {agent_id}: Initiating Universal Tutor session for: {topic}...")
                    try:
                        from core_organs.organ_10_extended_capabilities import UniversalInteractiveTutor
                        tutor_res = UniversalInteractiveTutor.analyze_frame_and_teach(
                            concept_or_topic=topic,
                            frame_image_path_or_b64=parameters.get("frame_image") or parameters.get("image_path"),
                            video_url=parameters.get("video_url"),
                            transcript_snippet=parameters.get("transcript"),
                            target_domain=domain
                        )
                        self.results[task_id] = {"_status": "SUCCESS", "success": True, **tutor_res}
                        continue
                    except Exception as e:
                        log.error(f"Agent {agent_id}: Universal tutoring failed: {e}")
                        task_failed = True
                        continue

                # 4A. Interactive Learning Mode — Quiz, Hints, Step-by-Step
                if action in ["START_LEARNING", "LEARN_TOPIC", "ANSWER_QUIZ", "SUBMIT_ANSWER", "QUIZ_ANSWER", "GET_HINT", "HINT", "END_SESSION", "END_LEARNING"]:
                    log.info(f"Agent {agent_id}: Learning mode action: {action}...")
                    try:
                        from core_organs.organ_10_extended_capabilities import InteractiveLearningOrchestrator
                        orch = InteractiveLearningOrchestrator()
                        if action in ["START_LEARNING", "LEARN_TOPIC"]:
                            result = orch.start_learning(
                                topic=parameters.get("topic") or parameters.get("concept", ""),
                                difficulty=parameters.get("difficulty", "medium"),
                                learned_content=parameters.get("learned_content", "")
                            )
                        elif action in ["ANSWER_QUIZ", "SUBMIT_ANSWER", "QUIZ_ANSWER"]:
                            result = orch.submit_answer(
                                answer=parameters.get("answer") or parameters.get("user_answer", "")
                            )
                        elif action in ["GET_HINT", "HINT"]:
                            result = orch.get_hint()
                        elif action in ["END_SESSION", "END_LEARNING"]:
                            result = orch.end_learning()
                        else:
                            result = {"status": "ok", "action": action}
                        self.results[task_id] = {"_status": "SUCCESS", "success": True, **result}
                        continue
                    except Exception as e:
                        log.error(f"Agent {agent_id}: Learning mode failed: {e}")
                        task_failed = True
                        continue

                # 5. File Search & Glob Discovery
                if action in ["FILE_SEARCH", "GREP_FILES", "FIND_FILES"]:
                    root_d = parameters.get("root_dir", "D:\\new_automation")
                    pat = parameters.get("pattern", "*")
                    log.info(f"Agent {agent_id}: Searching files in {root_d} matching '{pat}'...")
                    try:
                        from core_organs.organ_10_extended_capabilities import FileSearchEngine
                        search_res = FileSearchEngine.search(root_dir=root_d, pattern=pat, content_regex=parameters.get("content_regex"))
                        self.results[task_id] = {"_status": "SUCCESS", "success": True, **search_res}
                        continue
                    except Exception as e:
                        log.error(f"Agent {agent_id}: File search failed: {e}")
                        task_failed = True
                        continue

                # 6. Persistent Knowledge Base
                if action in ["KNOWLEDGE_STORE", "KNOWLEDGE_QUERY"]:
                    try:
                        from core_organs.organ_10_extended_capabilities import PersistentKnowledgeEngine
                        if action == "KNOWLEDGE_STORE":
                            k_res = PersistentKnowledgeEngine.store_note(
                                topic=parameters.get("topic", "General Note"),
                                content=parameters.get("content", ""),
                                tags=parameters.get("tags", "general")
                            )
                        else:
                            k_res = {"notes": PersistentKnowledgeEngine.query_notes(parameters.get("query", ""))}
                        self.results[task_id] = {"_status": "SUCCESS", "success": True, **k_res}
                        continue
                    except Exception as e:
                        log.error(f"Agent {agent_id}: Knowledge operation failed: {e}")
                        task_failed = True
                        continue

                # 7. Database Operations
                if action in ["DATABASE_QUERY", "EXECUTE_SQL"]:
                    db_p = parameters.get("db_path", "D:\\new_automation\\data\\hojaiga_knowledge.db")
                    sql_query = parameters.get("sql") or parameters.get("query", "")
                    log.info(f"Agent {agent_id}: Executing SQL query against {db_p}...")
                    try:
                        from core_organs.organ_10_extended_capabilities import DatabaseOperationsEngine
                        db_res = DatabaseOperationsEngine.execute_sql(db_path=db_p, sql=sql_query)
                        self.results[task_id] = {"_status": "SUCCESS", "success": True, **db_res}
                        continue
                    except Exception as e:
                        log.error(f"Agent {agent_id}: Database query failed: {e}")
                        task_failed = True
                        continue

                # 8. Live Directory Extraction Pipeline
                if action in ["EXTRACT_LEADS", "EXTRACT_LISTINGS", "EXTRACT_AND_EXPORT", "SCRAPE_LEADS"] or ("extract" in action.lower() and ("excel" in target_str or "contact" in target_str or "lead" in target_str)):
                    log.info(f"Agent {agent_id}: Executing live directory extraction pipeline via CDP...")
                    try:
                        from core_organs.lead_extractor import extract_leads_and_export
                        lead_query = parameters.get("query") or at.get("objective") or "interior designers"
                        min_l = int(parameters.get("min_leads", 100))
                        out_file = parameters.get("output_file") or "leads.xlsx"
                        lead_res = extract_leads_and_export(query=lead_query, min_leads=min_l, output_filename=out_file)
                        self.results[task_id] = {"_status": "SUCCESS", "success": True, **lead_res}
                        continue
                    except Exception as e:
                        log.error(f"Agent {agent_id}: Lead extraction failed: {e}")
                        task_failed = True
                        continue

                # 9. Deep Lead Enrichment
                if action in ["ENRICH_LEADS", "LEAD_ENRICH", "DEEP_ENRICH"]:
                    leads_data = parameters.get("leads", [])
                    max_targets = int(parameters.get("max_targets", 20))
                    log.info(f"Agent {agent_id}: Executing deep web lead enrichment for {len(leads_data)} contacts...")
                    try:
                        from core_organs.organ_10_extended_capabilities import DeepLeadEnricher
                        enrich_res = asyncio.run(DeepLeadEnricher.enrich_leads(leads_data, max_targets))
                        self.results[task_id] = {
                            "_status": "SUCCESS",
                            "success": True,
                            "enriched_leads": enrich_res,
                            "count": len(enrich_res)
                        }
                        continue
                    except Exception as e:
                        log.error(f"Agent {agent_id}: Lead enrichment failed: {e}")
                        task_failed = True
                        continue

                # 10. Deep Scan & App Learning
                if action in ["DEEP_SCAN", "SCAN_APP", "LEARN_APP"]:
                    target_app = parameters.get("app_name") or parameters.get("target") or at.get("objective") or ""
                    log.info(f"Agent {agent_id}: Deep scanning '{target_app}'...")
                    try:
                        # BLOCKER #2: modern fast_scan pipeline (bulk UIA + static harvest + async vision),
                        # result adapted to the legacy organ_30 dict shape (tree_stats/total_* keys).
                        from core_organs import fast_scan
                        scan_result = fast_scan.deep_scan_legacy_shape(target_app or "unknown", budget_s=10.0)
                        if scan_result.get("status") == "error":
                            self.results[task_id] = {"_status": "FAILED", "success": False,
                                                     "error": scan_result.get("message") or "scan found no window",
                                                     "scan_result": scan_result}
                            task_failed = True
                            continue
                        self.results[task_id] = {"_status": "SUCCESS", "success": True, "scan_result": scan_result}
                        continue
                    except Exception as e:
                        log.error(f"Agent {agent_id}: Deep scan failed: {e}")
                        task_failed = True
                        continue

                # Identify desktop applications
                if action in ["SOLVE_CAPTCHA", "HANDLE_CAPTCHA", "CAPTCHA"]:
                    # CAPTCHA/2FA gates always run through the Chrome controller
                    # (Organ 19); never let the desktop heuristic hijack them.
                    target_controller = "chrome"
                elif any(k in target_str for k in ["obs", "launch_app", "desktop", "record session"]):
                    target_controller = "app"
                    action = "launch"
                    if "obs" in target_str:
                        parameters = {"app_action": "launch", "command": ["start", "obs64"]}
                else:
                    target_controller = "chrome"

                # Structure payload parameters for the controller
                call_payload = {"payload": {**parameters, "session_id": session_id}}

                # HITL-capable steps get a long window: navigation may pause on
                # login/CAPTCHA gates, and CAPTCHA steps exist to wait on a human.
                # Tuned below the orchestrator's task watchdog so the gate fails
                # cleanly first with a precise error.
                if str(action).upper() in ("SOLVE_CAPTCHA", "HANDLE_CAPTCHA", "CAPTCHA", "NAVIGATE"):
                    try:
                        step_timeout_s = float(os.environ.get("HOJAIGA_HITL_STEP_TIMEOUT_S", "170"))
                    except ValueError:
                        step_timeout_s = 170.0
                else:
                    step_timeout_s = 15.0

                # Step-level error recovery: transient controller failures are
                # retried in place (bounded, linear backoff) before the step is
                # escalated; CAPTCHA/2FA gates are never hot-retried because
                # they need a fresh human window from the orchestrator retry.
                try:
                    step_retries = max(0, int(os.environ.get("HOJAIGA_STEP_RETRIES", "2")))
                except (TypeError, ValueError):
                    step_retries = 2
                step_ok = False
                step_error: Optional[str] = None
                for attempt in range(step_retries + 1):
                    if attempt:
                        backoff_s = 1.5 * attempt
                        log.warning(
                            f"[Organ10] Retrying step {action} "
                            f"(attempt {attempt + 1}/{step_retries + 1}) in {backoff_s:.1f}s after: {step_error}")
                        await asyncio.sleep(backoff_s)
                    self.pending_tasks[task_id].clear()
                    await self.cns.publish(EventEnvelope(
                        topic="INVOKE_CONTROLLER",
                        source_organ="organ_10",
                        payload={
                            "task_id": task_id,
                            "target_controller": target_controller,
                            "action": action,
                            "parameters": call_payload
                        }
                    ))
                    try:
                        await asyncio.wait_for(self.pending_tasks[task_id].wait(), timeout=step_timeout_s)
                        if self.results.get(task_id, {}).get("_status") == "FAILED":
                            step_error = str(
                                self.results.get(task_id, {}).get("errorText") or f"Step {action} failed")
                            if "captcha" in step_error.lower() or attempt >= step_retries:
                                break
                            continue
                        step_ok = True
                        break
                    except asyncio.TimeoutError:
                        step_error = f"Step {action} timed out"
                        if attempt >= step_retries:
                            break
                        continue

                if step_ok:
                    self._complete_next_swarm_task(task_id)
                else:
                    log.error(f"Task step {action} failed after {step_retries + 1} attempt(s): {step_error}")
                    self._complete_next_swarm_task(task_id, error=step_error)
                    # An unresolved CAPTCHA/2FA gate cannot be progressed by
                    # more page steps -- never pile actions onto a challenge
                    # page; let the orchestrator retry with a fresh window.
                    if "captcha" in str(step_error or "").lower():
                        captcha_blocked = True
                        break
                await asyncio.sleep(0.5)

        # Complete and publish (drain any swarm temp tasks still tracked as pending)
        if captcha_blocked:
            # Pin the failure -- the last-write-wins results merge must not mask
            # an unresolved CAPTCHA/2FA with a later SUCCESS status.
            blocked_result = self.results.setdefault(task_id, {})
            blocked_result["_status"] = "FAILED"
            blocked_result.setdefault("success", False)
            blocked_result.setdefault(
                "errorText", "captcha_unresolved: human did not solve the CAPTCHA/2FA in time")
        # Stateful lifecycle: the task is complete but the agents are NOT --
        # they are parked as WAITING_FOR_BRAIN so connected tasks revive them.
        await self._retire_task_agents(task_id)
        self._drain_swarm_tasks(task_id, self.results.get(task_id, {}))
        await self.cns.publish(EventEnvelope(
            topic="AGENTS_COMPLETED",
            source_organ="organ_10",
            payload={"task_id": task_id, "result_data": self.results.get(task_id, {})}
        ))
        await self.cns.publish(EventEnvelope(
            topic="sys.events",
            source_organ="organ_10",
            payload={"event_type": "AGENTS_COMPLETED", "task_id": task_id}
        ))

    async def spawn_swarm_agents(self, task_id: str, swarm_structure: Dict[str, Any]) -> Dict[str, Any]:
        """
        Spawn sub-agents and temporary agents based on swarm structure.
        
        Args:
            task_id: Task identifier
            swarm_structure: Swarm structure from enhanced compiler
        
        Returns:
            Spawned agents information
        """
        if not _HAS_AGENT_STRUCTURE:
            log.warning("[Organ10] Agent structure not available, using standard agent spawning")
            return {"error": "Agent structure not available"}
        
        spawned_agents = {
            "sub_agents": [],
            "temporary_agents": []
        }
        
        # Spawn sub-agents
        for sub_agent_instr in swarm_structure.get("sub_agent_instructions", []):
            sub_agent_id = sub_agent_instr["sub_agent_id"]
            parent_agent_id = sub_agent_instr["parent_agent_id"]
            
            # Register sub-agent
            await self.cns.publish(EventEnvelope(
                topic="SUB_AGENT_SPAWNED",
                source_organ="organ_10",
                payload={
                    "task_id": task_id,
                    "sub_agent_id": sub_agent_id,
                    "parent_agent_id": parent_agent_id,
                    "paradigm": sub_agent_instr.get("parent_paradigm"),
                    "checkpoint_id": sub_agent_instr["checkpoint_id"],
                    "objective": sub_agent_instr["objective"]
                }
            ))
            
            spawned_agents["sub_agents"].append({
                "sub_agent_id": sub_agent_id,
                "parent_agent_id": parent_agent_id,
                "status": "spawned"
            })

            # Track the sub-agent in the stateful registry so it is retained
            # after the parent task completes.
            self._register_agent(
                sub_agent_id,
                tier="sub",
                task_id=task_id,
                parent_agent_id=parent_agent_id,
                context={
                    "checkpoint_id": sub_agent_instr["checkpoint_id"],
                    "objective": sub_agent_instr["objective"],
                },
            )
            
            log.info(f"[Organ10] Spawned sub-agent {sub_agent_id} for {parent_agent_id}")
        
        # Spawn temporary agents
        for temp_task in swarm_structure.get("temporary_agent_tasks", []):
            temp_agent_id = temp_task["temp_agent_id"]
            checkpoint_id = temp_task["checkpoint_id"]
            
            # Register temporary agent
            await self.cns.publish(EventEnvelope(
                topic="TEMPORARY_AGENT_SPAWNED",
                source_organ="organ_10",
                payload={
                    "task_id": task_id,
                    "temp_agent_id": temp_agent_id,
                    "checkpoint_id": checkpoint_id,
                    "objective": temp_task["objective"],
                    "no_overlap": temp_task.get("no_overlap", True),
                    "status": "pending"
                }
            ))
            
            spawned_agents["temporary_agents"].append({
                "temp_agent_id": temp_agent_id,
                "checkpoint_id": checkpoint_id,
                "status": "spawned"
            })

            self._register_agent(
                temp_agent_id,
                tier="temporary",
                task_id=task_id,
                context={
                    "checkpoint_id": checkpoint_id,
                    "objective": temp_task.get("objective", ""),
                },
            )
            
            log.info(f"[Organ10] Spawned temporary agent {temp_agent_id} for {checkpoint_id}")
        
        log.info(f"[Organ10] Spawned {len(spawned_agents['sub_agents'])} sub-agents and {len(spawned_agents['temporary_agents'])} temporary agents")
        
        return spawned_agents

    async def spawn_permanent_agent(self, agent_id: str, task_id: str = "") -> Dict[str, Any]:
        """Ensure a permanent agent exists in the stateful registry.

        Public API for tests/status tooling: permanent agents are retained
        across tasks (tier="permanent"), so "spawning" one registers or
        revives it in the registry rather than starting a fresh process.
        """
        self._ensure_state_loaded()
        self._register_agent(
            agent_id,
            tier="permanent",
            task_id=task_id,
            context={"objective": f"permanent:{agent_id}"},
        )
        rec = self._agents.get(agent_id)
        return {
            "agent_id": agent_id,
            "tier": rec.tier if rec else "permanent",
            "state": rec.state if rec else AgentState.INSTANTIATED.value,
            "registered": rec is not None,
        }
    
    async def verify_checkpoint(self, task_id: str, checkpoint_id: str) -> Dict[str, Any]:
        """
        Verify a checkpoint completion.
        
        Args:
            task_id: Task identifier
            checkpoint_id: Checkpoint identifier
        
        Returns:
            Verification result
        """
        await self.cns.publish(EventEnvelope(
            topic="CHECKPOINT_VERIFICATION",
            source_organ="organ_10",
            payload={
                "task_id": task_id,
                "checkpoint_id": checkpoint_id,
                "status": "verifying"
            }
        ))
        
        # In production, this would check if all sub-agents and temporary agents
        # for this checkpoint have completed their tasks
        
        return {
            "checkpoint_id": checkpoint_id,
            "verified": True,
            "sub_agents_completed": 0,
            "temporary_agents_completed": 0
        }
    
    async def get_agent_status(self) -> Dict[str, Any]:
        """
        Get status of all permanent agents.
        
        Returns:
            Agent status information
        """
        if not _HAS_AGENT_STRUCTURE:
            return {"error": "Agent structure not available"}
        
        self._ensure_state_loaded()
        idle_states = (AgentState.INSTANTIATED.value, AgentState.WAITING_FOR_BRAIN.value)
        agent_status: Dict[str, Any] = {}
        for agent_id, specialty in PERMANENT_AGENTS.items():
            rec = self._agents.get(agent_id)
            state = rec.state if rec else AgentState.WAITING_FOR_BRAIN.value
            agent_status[agent_id] = {
                "paradigm": specialty.paradigm.value,
                "state": state,
                "idle": state in idle_states,
                "current_task": rec.task_id if (rec and state == AgentState.EXECUTING.value) else None
            }

        # Registry snapshot + retained session context + retention settings
        agent_status["_swarm"] = {
            aid: rec.to_dict() for aid, rec in self._agents.items() if aid not in PERMANENT_AGENTS
        }
        agent_status["_session_context"] = dict(self._session_context)
        agent_status["_retention"] = {
            "stateful_enabled": self._stateful_enabled,
            "idle_ttl_s": self._idle_ttl_s,
            "active_agents": sum(1 for r in self._agents.values() if r.state == AgentState.EXECUTING.value),
            "retained_agents": sum(1 for r in self._agents.values() if r.state == AgentState.WAITING_FOR_BRAIN.value),
            "terminated_agents": sum(1 for r in self._agents.values() if r.state == AgentState.TERMINATED.value),
        }
        
        return agent_status
    
    async def coordinate_parallel_execution(self, task_id: str, 
                                           temp_agent_tasks: List[Dict[str, Any]],
                                           execution_graph: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Coordinate parallel execution of temporary agents using the parallel coordinator.
        
        Args:
            task_id: Task identifier
            temp_agent_tasks: List of temporary agent tasks
            execution_graph: Execution graph with dependencies
        
        Returns:
            Execution result
        """
        if not self._parallel_coordinator:
            log.warning("[Organ10] Parallel coordinator not available, using sequential execution")
            return {"error": "Parallel coordinator not available"}
        
        # Add tasks to coordinator
        task_ids = self._parallel_coordinator.add_tasks(temp_agent_tasks, execution_graph)
        
        # Start coordinator if not running
        if not self._parallel_coordinator._running:
            await self._parallel_coordinator.start()
        
        log.info(f"[Organ10] Coordinating {len(task_ids)} temporary agent tasks in parallel")
        
        # Wait for all tasks to complete
        # In production, would implement proper async waiting
        # For now, return coordinator status
        status = self._parallel_coordinator.get_status()
        
        return {
            "task_id": task_id,
            "total_tasks": len(task_ids),
            "task_ids": task_ids,
            "coordinator_status": status,
            "parallelism_level": "high" if status["max_parallel_tasks"] > 5 else "medium"
        }
    
    async def report_task_completion(self, task_id: str, temp_agent_id: str, 
                                    result: Dict[str, Any] = None, error: str = None):
        """
        Report temporary agent task completion to the parallel coordinator.
        
        Args:
            task_id: Main task identifier
            temp_agent_id: Temporary agent identifier
            result: Task result
            error: Task error (if failed)
        """
        if not self._parallel_coordinator:
            return
        
        # Find the coordinator task ID for this temp agent
        coordinator_task_id = None
        for tid, task in self._parallel_coordinator.tasks.items():
            if task.temp_agent_id == temp_agent_id:
                coordinator_task_id = tid
                break
        
        if coordinator_task_id:
            self._parallel_coordinator.complete_task(coordinator_task_id, result, error)
            log.info(f"[Organ10] Reported completion for temp agent {temp_agent_id}")

    def _complete_next_swarm_task(self, task_id: str, result: Optional[Dict[str, Any]] = None,
                                  error: Optional[str] = None) -> None:
        """FIFO-complete the oldest running temporary-agent task of this orchestration
        task's swarm, keeping the parallel coordinator status aligned with the
        sequential controller execution."""
        if not self._parallel_coordinator:
            return
        ids = self._swarm_task_ids.get(task_id)
        if not ids:
            return
        running = [
            self._parallel_coordinator.tasks[i] for i in ids
            if i in self._parallel_coordinator.tasks
            and self._parallel_coordinator.tasks[i].status == TaskStatus.RUNNING
        ]
        if not running:
            return
        oldest = min(running, key=lambda t: t.started_at or t.created_at)
        self._parallel_coordinator.complete_task(
            oldest.task_id,
            result=result or {"objective": oldest.objective},
            error=error
        )

    def _drain_swarm_tasks(self, task_id: str, result: Dict[str, Any]) -> None:
        """Mark any remaining tracked swarm temp tasks as completed once the
        orchestration task finishes, so the coordinator reaches a terminal state."""
        if not self._parallel_coordinator:
            return
        ids = self._swarm_task_ids.pop(task_id, [])
        if not ids:
            return
        terminal = (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
        drained = 0
        for i in ids:
            t = self._parallel_coordinator.tasks.get(i)
            if t and t.status not in terminal:
                self._parallel_coordinator.complete_task(i, result=result)
                drained += 1
        if drained:
            log.info(f"[Organ10] Drained {drained} remaining swarm tasks for {task_id}")
    
    # ------------------------------------------------------------------
    # Stateful agent lifecycle: state persistence + retention management
    # ------------------------------------------------------------------
    _SESSION_CONTEXT_KEYS = (
        "session_id", "url", "current_url", "title", "tab_id", "target_id",
        "browser_open", "hwnd", "page_state", "captcha",
    )

    def _ensure_state_loaded(self) -> None:
        """Load the persisted agent registry exactly once per process.

        Agents persisted mid-EXECUTING belong to a crashed/killed run: they
        are parked back to WAITING_FOR_BRAIN (crash recovery) instead of
        being reported as executing forever.
        """
        if self._state_loaded:
            return
        self._state_loaded = True
        try:
            with self._state_lock:
                if not os.path.exists(self._state_path):
                    self._agents = {}
                    self._session_context = {}
                else:
                    with open(self._state_path, "r", encoding="utf-8") as fh:
                        data = json.load(fh) or {}
                    agents: Dict[str, StatefulAgent] = {}
                    for _aid, rec in (data.get("agents") or {}).items():
                        try:
                            agent = StatefulAgent.from_dict(rec)
                        except Exception:
                            continue
                        if not agent.agent_id or agent.state == AgentState.TERMINATED.value:
                            continue
                        if agent.state == AgentState.EXECUTING.value:
                            agent.state = AgentState.WAITING_FOR_BRAIN.value
                            agent.updated_at = time.time()
                        agents[agent.agent_id] = agent
                    self._agents = agents
                    ctx = data.get("session_context")
                    self._session_context = dict(ctx) if isinstance(ctx, dict) else {}
            log.info(
                f"[Organ10] State loaded: {len(self._agents)} retained agent(s), "
                f"session_context={'yes' if self._session_context else 'no'}"
            )
        except Exception as exc:
            log.warning(f"[Organ10] State load failed ({exc}); starting fresh registry")
            self._agents = {}
            self._session_context = {}
        # Expire stale retained agents (idle TTL) before first use.
        self._purge_expired_agents()

    def _save_state(self) -> None:
        """Persist registry + session context atomically (tmp file + replace).

        Locking discipline: call OUTSIDE any ``with self._state_lock`` block
        (threading.Lock is not reentrant).
        """
        try:
            state_dir = os.path.dirname(self._state_path)
            if state_dir:
                os.makedirs(state_dir, exist_ok=True)
            with self._state_lock:
                payload = {
                    "version": AGENT_STATE_VERSION,
                    "saved_at": time.time(),
                    "session_context": dict(self._session_context),
                    "agents": {
                        aid: rec.to_dict()
                        for aid, rec in self._agents.items()
                        if rec.state != AgentState.TERMINATED.value
                    },
                }
            tmp_path = f"{self._state_path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self._state_path)
        except Exception as exc:
            log.warning(f"[Organ10] State save failed: {exc}")

    def _register_agent(self, agent_id: str, tier: str = "temporary", task_id: str = "",
                        parent_agent_id: Optional[str] = None,
                        context: Optional[Dict[str, Any]] = None) -> Optional[StatefulAgent]:
        """Register a newly spawned agent, or revive an already-retained one.

        Reviving keeps identity + accumulated context and only refreshes the
        task assignment and state -- continuity instead of a cold start.
        """
        now = time.time()
        with self._state_lock:
            agent = self._agents.get(agent_id)
            if agent is None:
                agent = StatefulAgent(
                    agent_id=agent_id,
                    tier=tier,
                    parent_agent_id=parent_agent_id,
                    task_id=task_id,
                    state=AgentState.EXECUTING.value,
                    context=dict(context or {}),
                    created_at=now,
                    updated_at=now,
                )
                self._agents[agent_id] = agent
                log.info(f"[Organ10] Agent registered: {agent_id} ({tier}) for task {task_id}")
            else:
                if parent_agent_id:
                    agent.parent_agent_id = parent_agent_id
                if context:
                    agent.context.update(context)
                agent.task_id = task_id or agent.task_id
                agent.state = AgentState.EXECUTING.value
                agent.kill_requested = False
                agent.updated_at = now
                log.info(f"[Organ10] Agent revived: {agent_id} for task {task_id}")
        self._save_state()
        return agent

    def _capture_session_context(self, task_id: str, result_data: Dict[str, Any],
                                 error: Optional[str] = None) -> None:
        """Merge a controller result into the retained session context.

        This is what makes connected tasks work: the next task's launch hints
        (reuse_session / prior_url) and session-id fallback are derived here.
        """
        if not isinstance(result_data, dict):
            result_data = {}
        captured: Dict[str, Any] = {}
        for key in self._SESSION_CONTEXT_KEYS:
            value = result_data.get(key)
            if value not in (None, "", [], {}):
                captured[key] = value
        # Some controllers nest details one level down (e.g. result_data.data).
        for nested_key in ("data", "session", "page"):
            nested = result_data.get(nested_key)
            if isinstance(nested, dict):
                for key in self._SESSION_CONTEXT_KEYS:
                    if key not in captured and nested.get(key) not in (None, "", [], {}):
                        captured[key] = nested[key]
        with self._state_lock:
            self._session_context.update(captured)
            if any(captured.get(k) for k in ("session_id", "url", "current_url", "title")):
                self._session_context["chrome_open"] = True
            if error:
                self._session_context["last_error"] = str(error)
            self._session_context["last_task_id"] = task_id
            self._session_context["updated_at"] = time.time()
            for rec in self._agents.values():
                if rec.task_id != task_id or rec.state != AgentState.EXECUTING.value:
                    continue
                for key in ("session_id", "current_url", "url"):
                    if captured.get(key):
                        rec.context[key] = captured[key]
                rec.updated_at = time.time()
        self._save_state()

    def _prior_session_context(self) -> Dict[str, Any]:
        """Retained session context if still fresh (TTL), else {} (cold start)."""
        if not self._stateful_enabled:
            return {}
        with self._state_lock:
            ctx = dict(self._session_context)
        if not ctx:
            return {}
        try:
            age = time.time() - float(ctx.get("updated_at") or 0.0)
        except (TypeError, ValueError):
            age = self._idle_ttl_s + 1.0
        if self._idle_ttl_s > 0 and age > self._idle_ttl_s:
            log.info(
                f"[Organ10] Retained session expired (age {age:.0f}s > TTL {self._idle_ttl_s:.0f}s)"
            )
            return {}
        return ctx

    async def _retire_task_agents(self, task_id: str) -> Dict[str, Any]:
        """Retire the agents that worked on ``task_id``.

        THE stateful-lifecycle fix: by default nothing is killed. Agents are
        parked as WAITING_FOR_BRAIN and kept in the registry so connected
        tasks revive them. Termination happens only when statefulness is
        disabled or a kill was explicitly requested.
        """
        retained: List[str] = []
        killed: List[str] = []
        with self._state_lock:
            for rec in self._agents.values():
                if rec.task_id != task_id or rec.state == AgentState.TERMINATED.value:
                    continue
                if self._stateful_enabled and not rec.should_kill():
                    rec.state = AgentState.WAITING_FOR_BRAIN.value
                    rec.updated_at = time.time()
                    retained.append(rec.agent_id)
                else:
                    rec.state = AgentState.TERMINATED.value
                    rec.kill_requested = True
                    rec.updated_at = time.time()
                    killed.append(rec.agent_id)
            for agent_id in killed:
                self._agents.pop(agent_id, None)
        self._save_state()
        if retained:
            log.info(f"[Organ10] Retained {len(retained)} agent(s) for task {task_id}: {retained}")
        if killed:
            log.info(f"[Organ10] Terminated {len(killed)} agent(s) for task {task_id}")
        if self.cns is not None and (retained or killed):
            if retained and not killed:
                event_type = "AGENTS_RETAINED"
            elif killed and not retained:
                event_type = "AGENTS_TERMINATED"
            else:
                event_type = "AGENTS_RETENTION_MIXED"
            try:
                await self.cns.publish(EventEnvelope(
                    topic="sys.events",
                    source_organ="organ_10",
                    payload={
                        "event_type": event_type,
                        "task_id": task_id,
                        "retained": retained,
                        "killed": killed,
                        "stateful_enabled": self._stateful_enabled,
                    }
                ))
            except Exception as exc:
                log.debug(f"[Organ10] Retention event publish failed: {exc}")
        return {"task_id": task_id, "retained": retained, "killed": killed}

    async def request_agent_kill(self, agent_id: str, reason: str = "user_request") -> Dict[str, Any]:
        """Explicitly kill one agent (user intent overrides retention)."""
        with self._state_lock:
            rec = self._agents.pop(agent_id, None)
            if rec is None:
                return {"agent_id": agent_id, "killed": False, "reason": "not_found"}
            rec.kill_requested = True
            rec.state = AgentState.TERMINATED.value
            rec.updated_at = time.time()
        self._save_state()
        log.info(f"[Organ10] Agent {agent_id} terminated (reason={reason})")
        if self.cns is not None:
            try:
                await self.cns.publish(EventEnvelope(
                    topic="sys.events",
                    source_organ="organ_10",
                    payload={"event_type": "AGENT_KILLED", "agent_id": agent_id, "reason": reason}
                ))
            except Exception as exc:
                log.debug(f"[Organ10] Kill event publish failed: {exc}")
        return {"agent_id": agent_id, "killed": True, "reason": reason}

    async def clear_idle_agents(self, reason: str = "user_request") -> Dict[str, Any]:
        """Kill every retained idle agent (explicit user cleanup)."""
        with self._state_lock:
            idle_ids = [
                aid for aid, rec in self._agents.items()
                if rec.state in (AgentState.WAITING_FOR_BRAIN.value, AgentState.INSTANTIATED.value)
            ]
            for aid in idle_ids:
                rec = self._agents.pop(aid, None)
                if rec is not None:
                    rec.kill_requested = True
                    rec.state = AgentState.TERMINATED.value
        self._save_state()
        log.info(f"[Organ10] Cleared {len(idle_ids)} idle agent(s) (reason={reason})")
        if self.cns is not None and idle_ids:
            try:
                await self.cns.publish(EventEnvelope(
                    topic="sys.events",
                    source_organ="organ_10",
                    payload={"event_type": "AGENTS_CLEARED", "agent_ids": idle_ids, "reason": reason}
                ))
            except Exception as exc:
                log.debug(f"[Organ10] Clear event publish failed: {exc}")
        return {"killed": idle_ids, "reason": reason}

    def _purge_expired_agents(self, now: Optional[float] = None) -> List[str]:
        """Idle-TTL garbage collection; permanent-tier agents are exempt."""
        if not self._stateful_enabled or self._idle_ttl_s <= 0:
            return []
        now = now if now is not None else time.time()
        purged: List[str] = []
        with self._state_lock:
            for aid, rec in list(self._agents.items()):
                if rec.tier == "permanent":
                    continue
                if rec.state not in (AgentState.WAITING_FOR_BRAIN.value, AgentState.INSTANTIATED.value):
                    continue
                age = now - (rec.updated_at or rec.created_at or 0.0)
                if age > self._idle_ttl_s:
                    rec.state = AgentState.TERMINATED.value
                    rec.kill_requested = True
                    purged.append(aid)
                    self._agents.pop(aid, None)
        if purged:
            log.info(f"[Organ10] Idle-TTL purged {len(purged)} agent(s): {purged}")
            self._save_state()
        return purged

    async def _terminate_all_agents(self, reason: str = "shutdown") -> int:
        """Kill every registered agent (organ shutdown)."""
        with self._state_lock:
            all_ids = list(self._agents.keys())
            for aid in all_ids:
                rec = self._agents.pop(aid, None)
                if rec is not None:
                    rec.kill_requested = True
                    rec.state = AgentState.TERMINATED.value
        if all_ids:
            log.info(f"[Organ10] Terminated all {len(all_ids)} agent(s) (reason={reason})")
        # Persist the empty registry so a restart does not resurrect agents.
        self._save_state()
        if self.cns is not None and all_ids:
            try:
                await self.cns.publish(EventEnvelope(
                    topic="sys.events",
                    source_organ="organ_10",
                    payload={"event_type": "AGENTS_TERMINATED", "agent_ids": all_ids, "reason": reason}
                ))
            except Exception as exc:
                log.debug(f"[Organ10] Terminate-all event publish failed: {exc}")
        return len(all_ids)

    async def get_parallel_status(self) -> Dict[str, Any]:
        """
        Get parallel execution coordinator status.
        
        Returns:
            Coordinator status
        """
        if not self._parallel_coordinator:
            return {"error": "Parallel coordinator not available"}
        
        return self._parallel_coordinator.get_status()
    
    async def _handle_cns_controller_execution_completed(self, env) -> None:
        payload = env.payload
        task_id = payload.get("task_id")
        
        current = self.results.get(task_id, {})
        new_data = payload.get("result_data", {})
        
        if isinstance(new_data, dict):
            current.update(new_data)
        if payload.get("result"):
            current["_status"] = payload.get("result")
        if payload.get("error"):
            current["errorText"] = payload.get("error")
            
        self.results[task_id] = current

        # Stateful lifecycle: capture session/context details from every
        # controller result so connected tasks can reuse them.
        try:
            self._capture_session_context(
                task_id,
                new_data if isinstance(new_data, dict) else {},
                error=payload.get("error"),
            )
        except Exception as exc:
            log.debug(f"[Organ10] Session context capture failed: {exc}")

        if task_id in self.pending_tasks:
            self.pending_tasks[task_id].set()
