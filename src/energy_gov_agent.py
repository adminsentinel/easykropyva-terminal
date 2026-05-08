from .base_agent import AgentMessage, AgentState, BaseAgent, MessageType, Skill


class EnergyGovAgent(BaseAgent):
    """Power-state governor with compatibility methods used by coordinator/tests."""

    _STATE_CONSUMPTION_UA = {
        "HIBERNATE": 10,
        "SLEEP": 50,
        "DSP_VERIFY": 15_000,
        "FULL_ALERT": 80_000,
    }

    def __init__(self, agent_id: str = "energy_gov", name: str = "Energy-Hero"):
        skills = [Skill("manage", self.manage, priority=95)]
        super().__init__(agent_id, name, skills)

        self.current_state = "SLEEP"
        self.consumption_ua = self._STATE_CONSUMPTION_UA[self.current_state]
        self.temperature = 25
        self.last_energy = 0
        self.relay_advised = False
        self.weather_sleep_advised = False

    async def state_transition(self, trigger) -> bool:
        """
        Compatibility API:
        - string input: explicit state set
        - numeric input: infer state from signal energy
        """
        target = None

        if isinstance(trigger, str):
            candidate = trigger.strip().upper()
            if candidate in self._STATE_CONSUMPTION_UA:
                target = candidate
        else:
            energy = int(trigger or 0)
            if energy >= 70_000:
                target = "FULL_ALERT"
            elif energy >= 30_000:
                target = "DSP_VERIFY"
            elif energy >= 5_000:
                target = "SLEEP"
            else:
                target = "HIBERNATE"

        if not target:
            return False

        self.current_state = target
        self.consumption_ua = self._STATE_CONSUMPTION_UA[target]
        return True

    async def update_temperature(self, energy: int) -> int:
        """Small thermal model for status display/tests."""
        e = int(energy or 0)

        if e >= 70_000:
            self.temperature += 2
        elif e >= 30_000:
            self.temperature += 1
        else:
            self.temperature -= 1

        self.temperature = max(0, min(127, self.temperature))
        return self.temperature

    async def advise_relay_mode(self, battery_pct: float, threshold: float = 0.05) -> bool:
        pct = max(0.0, min(1.0, float(battery_pct)))
        self.relay_advised = pct <= max(0.01, min(0.5, float(threshold)))
        return self.relay_advised

    async def advise_weather_sleep(self, noise_index: float, threshold: float = 0.78) -> bool:
        idx = max(0.0, min(1.0, float(noise_index)))
        self.weather_sleep_advised = idx >= max(0.1, min(1.0, float(threshold)))
        return self.weather_sleep_advised

    async def manage(self, energy: int):
        self.last_energy = int(energy or 0)
        await self.state_transition(self.last_energy)
        await self.update_temperature(self.last_energy)
        return {
            "current_state": self.current_state,
            "consumption_ua": self.consumption_ua,
            "temperature": self.temperature,
            "relay_advised": self.relay_advised,
            "weather_sleep_advised": self.weather_sleep_advised,
        }

    async def process_message(self, msg: AgentMessage):
        if msg.msg_type == MessageType.DATA:
            await self.manage(msg.payload.get("energy", 0))
            if "battery_pct" in msg.payload:
                await self.advise_relay_mode(
                    battery_pct=float(msg.payload.get("battery_pct", 1.0)),
                    threshold=float(msg.payload.get("relay_threshold", 0.05)),
                )
            if "noise_index" in msg.payload:
                await self.advise_weather_sleep(
                    noise_index=float(msg.payload.get("noise_index", 0.0)),
                    threshold=float(msg.payload.get("weather_threshold", 0.78)),
                )
            return AgentMessage(
                sender=self.agent_id,
                receiver="coordinator",
                msg_type=MessageType.RESULT,
                payload={
                    "pwr_mode": self.current_state,
                    "consumption_ua": self.consumption_ua,
                    "temperature": self.temperature,
                    "relay_advised": self.relay_advised,
                    "weather_sleep_advised": self.weather_sleep_advised,
                },
            )
        return None

    async def initialize(self) -> None:
        self.state = AgentState.IDLE
        print(f"[{self.name}] Ініціалізовано | Навички: {list(self.skills.keys())}")
