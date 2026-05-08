"""
SENTINEL-QC ECHELON AGENTS - Базовий клас агента
=================================================
Усі агенти наслідують BaseAgent та мають власні навички (skills).
"""

import asyncio
import uuid
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable
from collections import deque


class AgentState(Enum):
    """Стани агента"""
    INITIALIZING = "initializing"
    IDLE = "idle"
    PROCESSING = "processing"
    WAITING = "waiting"
    ERROR = "error"
    SHUTDOWN = "shutdown"


class MessageType(Enum):
    """Типи повідомлень між агентами"""
    DATA = "data"           # Сирі дані
    COMMAND = "command"      # Команда
    RESULT = "result"       # Результат обробки
    HEARTBEAT = "heartbeat" # Перевірка життєздатності
    SYNC = "sync"           # Синхронізація
    ALERT = "alert"         # Тривога


@dataclass
class AgentMessage:
    """Повідомлення між агентами"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    sender: str = ""
    receiver: str = ""
    msg_type: MessageType = MessageType.DATA
    payload: Any = None
    timestamp: float = field(default_factory=time.time)
    priority: int = 0
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'sender': self.sender,
            'receiver': self.receiver,
            'type': self.msg_type.value,
            'payload': self.payload,
            'timestamp': self.timestamp,
            'priority': self.priority
        }


class Skill:
    """Навичка агента - окрема функціональна одиниця"""
    
    def __init__(self, name: str, handler: Callable, priority: int = 50):
        self.name = name
        self.handler = handler
        self.priority = priority
        self.execution_count = 0
        self.total_time_ms = 0.0
    
    async def execute(self, *args, **kwargs) -> Any:
        start = time.perf_counter()
        result = await self.handler(*args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        self.execution_count += 1
        self.total_time_ms += elapsed
        return result
    
    def get_stats(self) -> Dict:
        avg_time = self.total_time_ms / max(1, self.execution_count)
        return {
            'name': self.name,
            'executions': self.execution_count,
            'total_ms': round(self.total_time_ms, 2),
            'avg_ms': round(avg_time, 3)
        }


class BaseAgent:
    """
    Базовий клас для всіх агентів системи Sentinel-QC.
    Кожен агент має:
    - Унікальний ID
    - Власний inbox для повідомлень
    - Набір навичок (skills)
    - Стан та пріоритет
    """
    
    def __init__(
        self, 
        agent_id: str, 
        name: str,
        skills: Optional[List[Skill]] = None,
        priority: int = 50
    ):
        self.agent_id = agent_id
        self.name = name
        self.priority = priority
        
        # Стан
        self.state = AgentState.INITIALIZING
        self.inbox: deque = deque(maxlen=100)
        self.outbox: deque = deque(maxlen=100)
        
        # Навички
        self.skills: Dict[str, Skill] = {}
        if skills:
            for skill in skills:
                self.skills[skill.name] = skill
        
        # Метрики
        self.metrics = {
            'messages_received': 0,
            'messages_sent': 0,
            'errors': 0,
            'uptime_s': 0,
            'start_time': time.time()
        }
        
        # Зв'язки
        self.connections: Dict[str, 'BaseAgent'] = {}
        self.subscribers: List[str] = []  # Агенти, що підписалися
        
        # Черга завдань
        self.task_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._running = False
        
    async def initialize(self) -> None:
        """Ініціалізація агента"""
        self.state = AgentState.IDLE
        print(f"[{self.name}] Ініціалізовано | Навички: {list(self.skills.keys())}")
    
    async def process_message(self, msg: AgentMessage) -> Optional[AgentMessage]:
        """Обробка вхідного повідомлення"""
        self.metrics['messages_received'] += 1
        return None
    
    async def execute_skill(self, skill_name: str, *args, **kwargs) -> Any:
        """Виконання навички"""
        if skill_name not in self.skills:
            raise ValueError(f"Skill '{skill_name}' not found in {self.name}")
        
        skill = self.skills[skill_name]
        return await skill.execute(*args, **kwargs)
    
    async def send_message(
        self, 
        receiver_id: str, 
        msg: AgentMessage,
        channel: Optional['MessageChannel'] = None
    ) -> None:
        """Надсилання повідомлення"""
        msg.sender = self.agent_id
        msg.receiver = receiver_id
        self.metrics['messages_sent'] += 1
        
        if channel:
            await channel.deliver(msg)
        else:
            self.outbox.append(msg)
    
    async def broadcast(
        self, 
        msg: AgentMessage, 
        channel: Optional['MessageChannel'] = None
    ) -> None:
        """Широкомовлення повідомлення"""
        msg.sender = self.agent_id
        for subscriber in self.subscribers:
            msg.receiver = subscriber
            if channel:
                await channel.deliver(msg)
    
    def subscribe(self, agent_id: str) -> None:
        """Підписка на повідомлення агента"""
        if agent_id not in self.subscribers:
            self.subscribers.append(agent_id)

    def connect(self, agent: 'BaseAgent') -> None:
        """Підключення до іншого агента"""
        self.connections[agent.agent_id] = agent
        agent.subscribe(self.agent_id)
    
    async def run(self) -> None:
        """Головний цикл агента"""
        self._running = True
        self.metrics['start_time'] = time.time()
        
        while self._running:
            try:
                # Обробка вхідних повідомлень
                while self.inbox:
                    msg = self.inbox.popleft()
                    response = await self.process_message(msg)
                    if response:
                        self.outbox.append(response)
                
                # Оновлення метрик
                self.metrics['uptime_s'] = time.time() - self.metrics['start_time']
                
                # Пауза
                await asyncio.sleep(0.01)
                
            except Exception as e:
                self.metrics['errors'] += 1
                self.state = AgentState.ERROR
                print(f"[{self.name}] ПОМИЛКА: {e}")
                await asyncio.sleep(1)
        
        self.state = AgentState.SHUTDOWN
    
    def stop(self) -> None:
        """Зупинка агента"""
        self._running = False
    
    def get_status(self) -> Dict:
        """Отримання статусу агента"""
        return {
            'id': self.agent_id,
            'name': self.name,
            'state': self.state.value,
            'priority': self.priority,
            'connections': len(self.connections),
            'subscribers': len(self.subscribers),
            'skills': list(self.skills.keys()),
            'metrics': self.metrics
        }
    
    def get_skills_stats(self) -> List[Dict]:
        """Статистика навичок"""
        return [skill.get_stats() for skill in self.skills.values()]


class MessageChannel:
    """Канал комунікації між агентами"""
    
    def __init__(self):
        self.subscribers: Dict[str, asyncio.Queue] = {}
        self.message_history: deque = deque(maxlen=1000)
    
    def subscribe(self, agent_id: str) -> asyncio.Queue:
        """Підписка на канал"""
        if agent_id not in self.subscribers:
            self.subscribers[agent_id] = asyncio.Queue()
        return self.subscribers[agent_id]
    
    def unsubscribe(self, agent_id: str) -> None:
        """Відписка від каналу"""
        if agent_id in self.subscribers:
            del self.subscribers[agent_id]
    
    async def deliver(self, msg: AgentMessage) -> None:
        """Доставка повідомлення"""
        self.message_history.append(msg.to_dict())
        
        if msg.receiver in self.subscribers:
            await self.subscribers[msg.receiver].put(msg)
    
    async def broadcast(self, msg: AgentMessage) -> None:
        """Широкомовлення"""
        for queue in self.subscribers.values():
            await queue.put(msg)


class AgentRegistry:
    """Реєстр всіх агентів системи"""
    
    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self.channels: Dict[str, MessageChannel] = {}
    
    def register_agent(self, agent: BaseAgent) -> None:
        self.agents[agent.agent_id] = agent
    
    def unregister_agent(self, agent_id: str) -> None:
        if agent_id in self.agents:
            del self.agents[agent_id]
    
    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        return self.agents.get(agent_id)
    
    def create_channel(self, channel_id: str) -> MessageChannel:
        if channel_id not in self.channels:
            self.channels[channel_id] = MessageChannel()
        return self.channels[channel_id]
    
    def get_all_agents(self) -> List[BaseAgent]:
        return list(self.agents.values())
    
    def get_system_status(self) -> Dict:
        return {
            'total_agents': len(self.agents),
            'total_channels': len(self.channels),
            'agents': [a.get_status() for a in self.agents.values()]
        }