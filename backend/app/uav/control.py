"""Supervisor commands during a flight: pause, resume, return home, land.

The API sets the wanted phase here; the source flying the mission reads it between frames and acts on it (PX4
through MAVSDK, the simulator by changing its own flight), so the commands run in the source's own event loop.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Literal

Action = Literal["pause", "resume", "return", "land"]
# to_landing: after the survey, flying to the landing point chosen for the mission (PX4).
Phase = Literal["surveying", "paused", "returning", "landing", "to_landing"]

STOP_REASONS = {"returning": "Returned home by the supervisor", "landing": "Landed by the supervisor"}


class ControlRejected(Exception):
    """The command does not apply in the current phase. The message says why."""


class FlightControl:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.phase: Phase = "surveying"
        # Flight time spent paused, added by the source. Only PX4's clock runs while paused: the simulator stops.
        self.paused_s = 0.0
        # The survey is complete and the UAV flies home on its own (PX4); no more commands apply.
        self.survey_finished = False
        self._changed = asyncio.Event()
        # Pauses in real (wall-clock) time, for the sensor collection: lanes read before and after a long pause
        # were not read in one go.
        self._clock = clock
        self._paused_since: float | None = None
        self._longest_pause_s = 0.0

    @property
    def longest_pause_s(self) -> float:
        """The longest pause so far, in seconds of real time, the one under way included."""
        current = 0.0 if self._paused_since is None else self._clock() - self._paused_since
        return max(self._longest_pause_s, current)

    def _set(self, phase: Phase) -> None:
        if self._paused_since is not None and phase != "paused":
            self._longest_pause_s = max(self._longest_pause_s, self._clock() - self._paused_since)
            self._paused_since = None
        elif phase == "paused" and self._paused_since is None:
            self._paused_since = self._clock()
        self.phase = phase

    @property
    def scanning(self) -> bool:
        """Sensor readings are only taken on the survey lines: not hovering in one place or on the way down."""
        return self.phase == "surveying"

    @property
    def stop_reason(self) -> str | None:
        """Why the survey ended early, or None while it may still finish (or has finished)."""
        return None if self.survey_finished else STOP_REASONS.get(self.phase)

    def finish_survey(self, to_landing: bool = False) -> None:
        """The last waypoint is reached; the UAV returns home (or flies to the landing point) and lands by itself."""
        self.survey_finished = True
        self._set("to_landing" if to_landing else "returning")
        self._changed.set()

    def request(self, action: Action) -> Phase:
        if self.survey_finished:
            raise ControlRejected("The survey is complete; the UAV is returning home")
        if self.stop_reason is not None:
            raise ControlRejected(f"The UAV is already {self.phase}")
        if action == "pause":
            if self.phase == "paused":
                raise ControlRejected("The survey is already paused")
            self._set("paused")
        elif action == "resume":
            if self.phase != "paused":
                raise ControlRejected("The survey is not paused")
            self._set("surveying")
        elif action == "return":
            self._set("returning")
        elif action == "land":
            self._set("landing")
        else:
            raise ControlRejected(f"Unknown command: {action}")
        self._changed.set()
        return self.phase

    async def wait_while_paused(self) -> None:
        while self.phase == "paused":
            self._changed.clear()
            await self._changed.wait()
