"""
Organ 39 — Target-Scoped Pause/Resume Controller (the Scheduler's pause plane).

This is the missing piece that makes organ_29's pause/resume *real*: it binds to
organ_29's `workflow_pause` / `workflow_resume` in-process sockets (so the
"Pause signal failed: no handler bound" warning goes away) and tracks a per-target
paused set. The task loop consults `gate(target_id)` so that when the Error Handler
halts one app, ONLY that target is frozen — every other target keeps running.

It also supports `register_target()` so a concrete stop/resume action (e.g. pausing a
Chrome tab or cancelling a pending step) can be attached per target.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger("hojaiga.scheduler")


class TargetPauseController:
    def __init__(self, organ29) -> None:
        self._organ29 = organ29
        self._paused: set = set()
        self._hooks: dict = {}  # target_id -> (pause_fn, resume_fn)
        try:
            organ29.sockets.workflow_pause.subscribe(self._on_pause)
            organ29.sockets.workflow_resume.subscribe(self._on_resume)
            logger.info("TargetPauseController bound to organ_29 workflow_pause/workflow_resume sockets")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not bind pause sockets: %s", exc)

    def register_target(
        self,
        target_id: str,
        pause_fn: Optional[Callable[[], None]] = None,
        resume_fn: Optional[Callable[[], None]] = None,
    ) -> None:
        """Attach a concrete stop/resume action for a target (optional)."""
        self._hooks[target_id] = (pause_fn, resume_fn)

    @staticmethod
    def _key(message) -> str:
        payload = message.payload or {}
        return payload.get("target_id") or f"handle:{payload.get('handle')}"

    async def _on_pause(self, message) -> None:
        target_id = self._key(message)
        self._paused.add(target_id)
        fn = self._hooks.get(target_id, (None, None))[0]
        if fn:
            try:
                fn()
            except Exception:  # noqa: BLE001
                logger.debug("pause hook failed", exc_info=True)
        logger.info("PAUSE target=%s (paused now: %s)", target_id, sorted(self._paused))

    async def _on_resume(self, message) -> None:
        target_id = self._key(message)
        self._paused.discard(target_id)
        fn = self._hooks.get(target_id, (None, None))[1]
        if fn:
            try:
                fn()
            except Exception:  # noqa: BLE001
                logger.debug("resume hook failed", exc_info=True)
        logger.info("RESUME target=%s (paused now: %s)", target_id, sorted(self._paused))

    def is_paused(self, target_id: str) -> bool:
        return target_id in self._paused

    async def gate(self, target_id: str) -> None:
        """Block the caller's task loop until `target_id` is resumed.

        A no-op when the target is not paused, so normal execution is unaffected.
        """
        while target_id in self._paused:
            logger.debug("gate: target=%s paused, waiting for resume...", target_id)
            await asyncio.sleep(0.25)
