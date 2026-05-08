
from .base_agent import BaseAgent, Skill, AgentMessage, MessageType, AgentState

class MemoryAgent(BaseAgent):
    def __init__(self, agent_id: str = "memory", name: str = "Memory-Hero"):
        skills = [Skill("remember", self.remember, priority=90)]
        super().__init__(agent_id, name, skills)
        self.slots = {} # angle -> energy map (max 8)

    async def remember(self, angle: int, energy: int):
        # Experience: store only significant targets
        if energy > 10000:
            self.slots[angle] = energy
        # Decay: clear old small energy slots
        if len(self.slots) > 8:
            self.slots = {a: e for a, e in self.slots.items() if e > 20000}

    async def process_message(self, msg: AgentMessage):
        if msg.msg_type == MessageType.DATA:
            await self.remember(msg.payload.get('angle', 0), msg.payload.get('energy', 0))
            return AgentMessage(self.agent_id, 'triangulation', MessageType.DATA, {'targets': self.slots})
        return None
