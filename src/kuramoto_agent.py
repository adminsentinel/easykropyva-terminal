from typing import Optional

from .base_agent import BaseAgent, Skill, AgentMessage, MessageType, AgentState

class KuramotoAgent(BaseAgent):
    def __init__(self, agent_id: str = "kuramoto", name: str = "Kuramoto-Hero"):
        skills = [Skill("sync", self.sync, priority=90)]
        super().__init__(agent_id, name, skills)
        self.phase = 0 # 0..65535
        self.coupling = 3276 # ~0.05 in Q16
        
    async def sync(self, neighbor_phase: int):
        # Direct Integer Math - No floats!
        diff = (neighbor_phase - self.phase + 32768) % 65536 - 32768
        # Gate check: ignore if > 90 deg (16384 in Q16)
        if abs(diff) < 16384:
            self.phase = (self.phase + (diff * self.coupling >> 16)) % 65536

    async def process_message(self, msg: AgentMessage) -> Optional[AgentMessage]:
        if msg.msg_type == MessageType.SYNC:
            await self.sync(msg.payload.get('phase', 0))
            return AgentMessage(self.agent_id, 'mesh', MessageType.DATA, {'phase': self.phase})
        return None
