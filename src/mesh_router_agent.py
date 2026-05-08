
from .base_agent import BaseAgent, Skill, AgentMessage, MessageType, AgentState

class MeshRouterAgent(BaseAgent):
    def __init__(self, agent_id: str = "mesh", name: str = "Mesh-Hero"):
        skills = [Skill("forward", self.forward, priority=90)]
        super().__init__(agent_id, name, skills)
        self.seen_mask = 0 # 64-bit mask for seq_no dedup
        
    async def forward(self, packet: dict):
        seq = packet.get('seq_no', 0) % 64
        if not (self.seen_mask & (1 << seq)):
            self.seen_mask |= (1 << seq)
            return True # Forward it
        return False # Drop duplicate

    async def process_message(self, msg: AgentMessage):
        if msg.msg_type == MessageType.DATA:
            packet = msg.payload.get('packet', {})
            if await self.forward(packet):
                return AgentMessage(self.agent_id, 'lora', MessageType.COMMAND, {'send': packet})
        return None
