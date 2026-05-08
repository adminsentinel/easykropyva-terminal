"""
TARGET ACQUISITION AGENT (Goertzel DSP)
=======================================
Спеціалізований Воїн. Його єдина мета - миттєво захоплювати ціль за відомими
бойовими частотами без важкої математики FFT. Працює паралельно з оригінальним DSP.
"""

from typing import Optional
from .base_agent import BaseAgent, Skill, AgentMessage, MessageType, AgentState

class TargetAcquisitionAgent(BaseAgent):
    def __init__(self, agent_id: str = "target_acq", name: str = "Warrior-TargetAcq"):
        skills = [
            Skill("rapid_lock_on", self.rapid_lock_on, priority=100),
            Skill("deploy_goertzel_filters", self.deploy_goertzel_filters, priority=90)
        ]
        super().__init__(agent_id, name, skills)
        
        # Зашиті "Золоті" частоти ворогів (з gold_combat_v1.json)
        self.target_frequencies = [187.5, 398.4, 742.2]
        
    async def _hidden_goertzel_math(self, audio_chunk: list, target_freq: float, sample_rate: int) -> float:
        """Схована математика. Воїни не думають про формули під час бою."""
        import math
        N = len(audio_chunk)
        k = int(0.5 + (N * target_freq) / sample_rate)
        omega = (2.0 * math.pi * k) / N
        sine = math.sin(omega)
        cosine = math.cos(omega)
        coeff = 2.0 * cosine
        q1 = 0
        q2 = 0
        for sample in audio_chunk:
            q0 = coeff * q1 - q2 + sample
            q2 = q1
            q1 = q0
        magnitude = math.sqrt(q1*q1 + q2*q2 - q1*q2*coeff)
        return magnitude

    async def deploy_goertzel_filters(self, audio_chunk: list) -> dict:
        """Скіл: Розгортання швидких фільтрів Гертцеля на зашиті частоти."""
        results = {}
        for freq in self.target_frequencies:
            mag = await self._hidden_goertzel_math(audio_chunk, freq, 16000)
            results[freq] = mag
        return results

    async def rapid_lock_on(self, audio_chunk: list) -> Optional[float]:
        """Павер: Миттєве захоплення цілі."""
        mags = await self.deploy_goertzel_filters(audio_chunk)
        
        # Якщо якась з бойових частот перевищує поріг - це ціль.
        for freq, mag in mags.items():
            if mag > 5000:  # Threshold
                return freq
        return None

    async def process_message(self, msg: AgentMessage) -> Optional[AgentMessage]:
        if msg.msg_type == MessageType.DATA and 'audio_chunk' in msg.payload:
            locked_freq = await self.rapid_lock_on(msg.payload['audio_chunk'])
            if locked_freq:
                return AgentMessage(
                    sender=self.agent_id,
                    receiver='threat_intel',
                    msg_type=MessageType.ALERT,
                    payload={'locked_freq': locked_freq}
                )
        return None
