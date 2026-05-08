"""
THREAT INTELLIGENCE AGENT
=========================
Спеціалізований Воїн. Зберігає досвід (Золоті Сигнатури).
Абстрагує складну математику класифікації у прості рівні загрози.
"""

from typing import Optional
from .base_agent import BaseAgent, Skill, AgentMessage, MessageType, AgentState

class ThreatIntelAgent(BaseAgent):
    def __init__(self, agent_id: str = "threat_intel", name: str = "Warrior-ThreatIntel"):
        skills = [
            Skill("assess_threat", self.assess_threat, priority=100)
        ]
        super().__init__(agent_id, name, skills)
        
        # Досвід Воїна (з gold_combat_v1.json)
        self.known_threats = {
            187.5: "HeavyBabaYaga",
            398.4: "ReconDrone",
            742.2: "LightFPV"
        }

    async def _hidden_classification_math(self, freq: float) -> tuple[str, int]:
        """Схована логіка ймовірностей."""
        # Уявімо тут складну байєсівську логіку або дерева рішень.
        # Для Воїна це просто рефлекс.
        closest_freq = min(self.known_threats.keys(), key=lambda k: abs(k - freq))
        if abs(closest_freq - freq) < 10.0:
            return self.known_threats[closest_freq], 99  # 99% впевненість
        return "Unknown_Anomaly", 50

    async def assess_threat(self, target_freq: float) -> dict:
        """Павер: Миттєва оцінка рівня загрози."""
        threat_class, confidence = await self._hidden_classification_math(target_freq)
        
        threat_level = "CRITICAL" if threat_class in ["HeavyBabaYaga", "LightFPV"] else "ELEVATED"
        
        return {
            "class": threat_class,
            "level": threat_level,
            "confidence": confidence
        }

    async def process_message(self, msg: AgentMessage) -> Optional[AgentMessage]:
        if msg.msg_type == MessageType.ALERT and 'locked_freq' in msg.payload:
            assessment = await self.assess_threat(msg.payload['locked_freq'])
            
            # Передаємо координатору або системі захисту
            return AgentMessage(
                sender=self.agent_id,
                receiver='coordinator',
                msg_type=MessageType.ALERT,
                payload={'threat_assessment': assessment}
            )
        return None
