from typing import Optional

from .base_agent import AgentMessage, AgentState, BaseAgent, MessageType, Skill


class EKFTrackerAgent(BaseAgent):
    """Lightweight EKF-like tracker with legacy 1D API compatibility."""

    def __init__(self, agent_id: str = "ekf", name: str = "EKF-Hero"):
        skills = [
            Skill("predict", self.predict, priority=95),
            Skill("update", self.update, priority=90),
            Skill("inertia_hold", self.inertia_hold, priority=80),
        ]
        super().__init__(agent_id, name, skills)

        self.x = 0.0  # angle in degrees [0..360)
        self.v = 0.0  # deg/s (coarse)
        self.P = 1000.0
        self.ghost_mode = False

        # Backward-compatible structure expected by old tests/callers.
        self.tracker_1d = {
            "angle_q16": 0,
            "velocity_q16": 0,
            "uncertainty": int(self.P),
        }

    def _sync_tracker_1d(self) -> None:
        self.tracker_1d["angle_q16"] = int((self.x % 360.0) * 65536 / 360.0)
        self.tracker_1d["velocity_q16"] = int(self.v * 65536 / 360.0)
        self.tracker_1d["uncertainty"] = int(self.P)

    async def predict(self, dt_ms: int):
        dt = max(0.0, float(dt_ms) / 1000.0)
        self.x = (self.x + self.v * dt) % 360.0
        self.P += 5.0
        self._sync_tracker_1d()

    async def update(self, z_deg: float, energy: int):
        # Energy-adaptive measurement noise.
        e = max(0.0, float(energy))
        R = 50.0 / (e / 1000.0 + 1.0)
        K = self.P / (self.P + R)

        diff = (float(z_deg) - self.x + 180.0) % 360.0 - 180.0
        self.x = (self.x + K * diff) % 360.0
        self.v = K * diff
        self.P = (1.0 - K) * self.P
        self.ghost_mode = False
        self._sync_tracker_1d()

    async def inertia_hold(self):
        if self.P > 500.0:
            self.ghost_mode = True
        if self.ghost_mode:
            self.x = (self.x + self.v) % 360.0
        self._sync_tracker_1d()

    async def predict_1d(self, dt_ms: int):
        """Legacy API shim."""
        await self.predict(dt_ms)

    async def update_1d(self, angle_q16: int, energy: int):
        """Legacy API shim (Q16 angle -> degrees)."""
        z_deg = (int(angle_q16) % 65536) * 360.0 / 65536.0
        await self.update(z_deg, energy)

    async def process_message(self, msg: AgentMessage) -> Optional[AgentMessage]:
        if msg.msg_type == MessageType.DATA:
            payload = msg.payload or {}
            z = payload.get("angle", payload.get("angle_deg", 0.0))
            e = payload.get("energy", 100)
            await self.predict(50)
            await self.update(z, e)
            return AgentMessage(
                sender=self.agent_id,
                receiver="coordinator",
                msg_type=MessageType.DATA,
                payload={"x": self.x, "v": self.v, "p": self.P, **self.tracker_1d},
            )
        return None

    async def initialize(self) -> None:
        self.state = AgentState.IDLE
        print(f"[{self.name}] Ініціалізовано | Навички: {list(self.skills.keys())}")
