
from .base_agent import BaseAgent, Skill, AgentMessage, MessageType, AgentState

class ConsensusAgent(BaseAgent):
    def __init__(self, agent_id: str = "consensus", name: str = "Consensus-Hero"):
        skills = [Skill("vote", self.vote, priority=90)]
        super().__init__(agent_id, name, skills)
        self.angle = 0
        self.conf = 0

    async def vote(self, neighbors: list):
        if not neighbors: return
        
        # Hero Logic: Find the most confident neighbor
        best_n = max(neighbors, key=lambda n: n.get('confidence', 0))
        n_conf = int(best_n.get('confidence', 0) * 65536) if isinstance(best_n.get('confidence', 0), float) else best_n.get('confidence', 0)
        
        if n_conf > self.conf:
            # Follow the leader
            diff = (best_n['angle_q16'] - self.angle + 32768) % 65536 - 32768
            self.angle = (self.angle + (diff >> 2)) % 65536 # Slow pull to leader
            self.conf = (self.conf + n_conf) >> 1

    async def process_message(self, msg: AgentMessage):
        if msg.msg_type == MessageType.DATA:
            await self.vote(msg.payload.get('neighbors', []))
            return AgentMessage(self.agent_id, 'memory', MessageType.DATA, 
                                {'angle': self.angle, 'conf': self.conf})
        return None
