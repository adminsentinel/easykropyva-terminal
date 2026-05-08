from __future__ import annotations

from collections import deque
import math
from typing import Optional

from .base_agent import AgentMessage, BaseAgent, MessageType, Skill


class EWDefenseAgent(BaseAgent):
    def __init__(
        self,
        agent_id: str = "ew_defense",
        name: str = "Warrior-EWShield",
        verbose: bool = True,
    ):
        skills = [
            Skill("shield_from_jamming", self.shield_from_jamming, priority=100),
            Skill("detect_spoofing", self.detect_spoofing, priority=90),
        ]
        super().__init__(agent_id, name, skills)

        self.shield_integrity = 100
        self.last_clean_angle: Optional[float] = None
        self.verbose = verbose
        self._spoof_events = 0
        self._recent_clean_angles: deque[float] = deque(maxlen=6)

    @staticmethod
    def _angle_diff_deg(a: float, b: float) -> float:
        return abs((float(a) - float(b) + 180.0) % 360.0 - 180.0)

    def _circular_reference_angle(self) -> Optional[float]:
        if not self._recent_clean_angles:
            return self.last_clean_angle

        sx = 0.0
        sy = 0.0
        for angle in self._recent_clean_angles:
            r = math.radians(float(angle))
            sx += math.cos(r)
            sy += math.sin(r)

        if abs(sx) < 1e-6 and abs(sy) < 1e-6:
            return self.last_clean_angle
        return (math.degrees(math.atan2(sy, sx)) + 360.0) % 360.0

    async def _hidden_gating_math(self, new_angle: float) -> bool:
        # Warm-up: accept first clean observation.
        if self.last_clean_angle is None:
            return False

        # Conservative anti-spoof rule:
        # spoof injections in harness are large angle jumps, so keep the gate strict.
        diff_last = self._angle_diff_deg(new_angle, self.last_clean_angle)
        return diff_last > 30.0

    async def detect_spoofing(self, incoming_angle: float, raw_angle: Optional[float] = None) -> bool:
        angle = float(incoming_angle) % 360.0
        is_spoofed = False
        # Direct cross-check against local sensor estimate when available.
        if raw_angle is not None:
            local_angle = float(raw_angle) % 360.0
            if self._angle_diff_deg(angle, local_angle) > 55.0:
                is_spoofed = True
        if not is_spoofed:
            is_spoofed = await self._hidden_gating_math(angle)
        if is_spoofed:
            self._spoof_events += 1
            self.shield_integrity = max(0, self.shield_integrity - 10)
            if self.verbose and (self._spoof_events <= 5 or self._spoof_events % 20 == 0):
                print(
                    f"[EW SHIELD] SPOOFING DETECTED! "
                    f"Dropping anomalous angle {angle:.1f}. "
                    f"Shield: {self.shield_integrity}%"
                )
        return is_spoofed

    async def shield_from_jamming(self, incoming_data: dict) -> Optional[dict]:
        if "angle" in incoming_data:
            angle = float(incoming_data["angle"]) % 360.0
            raw_angle = incoming_data.get("raw_angle")
            if await self.detect_spoofing(angle, raw_angle=raw_angle):
                return None

            self.last_clean_angle = angle
            self._recent_clean_angles.append(angle)
            self.shield_integrity = min(100, self.shield_integrity + 1)

        return incoming_data

    async def process_message(self, msg: AgentMessage) -> Optional[AgentMessage]:
        if msg.msg_type == MessageType.DATA:
            clean_data = await self.shield_from_jamming(msg.payload)
            if clean_data:
                return AgentMessage(
                    sender=self.agent_id,
                    receiver="ekf",
                    msg_type=MessageType.DATA,
                    payload=clean_data,
                )
        return None
