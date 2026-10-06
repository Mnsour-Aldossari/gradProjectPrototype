"""Supervisor commands during a flight: pause, resume, return home, land.

The API sets the wanted phase here; the source flying the mission reads it between frames and acts on it (PX4
through MAVSDK, the simulator by changing its own flight), so the commands run in the source's own event loop.
"""

from __future__ import annotations

import asyncio
from typing import Literal

Action = Literal["pause", "resume", "return", "land"]
Phase = Literal["surveying", "paused", "returning", "landing"]

STOP_REASONS = {"returning": "Returned home by the supervisor", "landing": "Landed by the supervisor"}


class ControlRejected(Exception):
    """The command does not apply in the current phase. The message says why."""


class FlightControl:
    def __init__(self) -> None:
        self.phase: Phase = "surveying"
        # Flight time spent paused, added by the source. Only PX4's clock runs while paused: the simulator stops.
        self.paused_s = 0.0
        self._changed = asyncio.Event()

    @property
    def scanning(self) -> bool:
        """Sensor readings are only taken on the survey lines: not hovering in one place or on the way down."""
        return self.phase == "surveying"

    @property
    def stop_reason(self) -> str | None:
        """Why the survey ended early, or None while it may still finish."""
        return STOP_REASONS.get(self.phase)

    def request(self, action: Action) -> Phase:
        if self.stop_reason is not None:
            raise ControlRejected(f"The UAV is already {self.phase}")
        if action == "pause":
            if self.phase == "paused":
                raise ControlRejected("The survey is already paused")
            self.phase = "paused"
        elif action == "resume":
            if self.phase != "paused":
                raise ControlRejected("The survey is not paused")
            self.phase = "surveying"
        elif action == "return":
            self.phase = "returning"
        elif action == "land":
            self.phase = "landing"
        else:
            raise ControlRejected(f"Unknown command: {action}")
        self._changed.set()
        return self.phase

    async def wait_while_paused(self) -> None:
        while self.phase == "paused":
            self._changed.clear()
            await self._changed.wait()
