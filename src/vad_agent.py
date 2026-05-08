"""
VAD AGENT - Voice Activity Detection
=====================================
Агент визначає активність голосу/звуку з адаптивним порогом.
"""

from typing import Optional
from .base_agent import BaseAgent, Skill, AgentMessage, MessageType, AgentState
from .config import DSPConfig


class VADAgent(BaseAgent):
    """
    VAD Agent - Voice Activity Detection з адаптивним порогом.
    Використовує EMA (Exponential Moving Average) для адаптації до шуму.
    """
    
    def __init__(self, agent_id: str = "vad", name: str = "VAD-Agent"):
        skills = [
            Skill("detect_activity", self.detect_activity, priority=85),
            Skill("adapt_threshold", self.adapt_threshold, priority=80),
            Skill("classify_signal", self.classify_signal, priority=75)
        ]
        super().__init__(agent_id, name, skills)
        
        self.config = DSPConfig()
        
        # Noise floor (адаптивний)
        self.noise_floor = 3000
        
        # Пороги
        self.vad_threshold = 3750  # noise_floor * 1.25
        
        # Історія для аналізу
        self.energy_history = []
        self.max_history = 100
        
    async def detect_activity(self, energy: int) -> bool:
        """
        Skill: Визначення активності
        Повертає True якщо енергія вище адаптивного порогу
        """
        # Оновлення історії
        self.energy_history.append(energy)
        if len(self.energy_history) > self.max_history:
            self.energy_history.pop(0)
        
        # Адаптація порогу
        self.vad_threshold = await self.adapt_threshold(energy)
        
        return energy > self.vad_threshold
    
    async def adapt_threshold(self, sample: int) -> int:
        """
        Skill: Адаптивне оновлення порогу через EMA
        noiseFloor = noiseFloor + α × (sample - noiseFloor) / 1024
        vadThreshold = noiseFloor × 1.25 (min 3000)
        """
        alpha = self.config.VAD_ALPHA
        
        # EMA update
        diff = sample - self.noise_floor
        self.noise_floor = self.noise_floor + (alpha * diff)
        
        # Обмеження мінімуму
        self.noise_floor = max(self.config.VAD_MIN_FLOOR, self.noise_floor)
        
        # VAD threshold = 1.25 × noise_floor
        threshold = int(self.noise_floor * self.config.VAD_THRESHOLD_MULT)
        
        return max(self.config.VAD_MIN_FLOOR, threshold)
    
    async def classify_signal(self, features: dict) -> str:
        """
        Skill: Класифікація сигналу на основі ознак
        Повертає: 'active', 'quiet', 'wind', 'drone'
        """
        energy = features.get('total_energy', 0)
        is_clipped = features.get('clipped', False)
        
        # Перевірка на clipping
        if is_clipped:
            return 'clipped'
        
        # Чи є активність?
        is_active = await self.detect_activity(energy)
        
        if not is_active:
            return 'quiet'
        
        # Аналіз спектру
        low_frac = features.get('low_frac', 0)
        high_frac = features.get('high_frac', 0)
        modulation = features.get('modulation', 0)
        
        # Вітер: багато низьких частот, мало модуляції
        if low_frac > self.config.WIND_LOW_FRAC and modulation < low_frac / 8:
            return 'wind'
        
        # Дрон: багато високих частот, багато модуляції
        mid_energy = features.get('mid', 0)
        if high_frac > self.config.DRONE_HIGH_FRAC and modulation > mid_energy / 8:
            return 'drone'
        
        return 'unknown'
    
    async def process_message(self, msg: AgentMessage) -> Optional[AgentMessage]:
        """Обробка повідомлень"""
        
        if msg.msg_type == MessageType.DATA:
            features = msg.payload.get('features', {})
            classification = await self.classify_signal(features)
            
            # Якщо виявлено дрон — сигнал тривоги
            if classification == 'drone':
                return AgentMessage(
                    sender=self.agent_id,
                    receiver='classifier',
                    msg_type=MessageType.ALERT,
                    payload={
                        'type': 'target_detected',
                        'classification': classification,
                        'features': features,
                        'confidence': 0.85
                    }
                )
        
        return None
    
    async def initialize(self) -> None:
        """Ініціалізація VAD агента"""
        self.state = AgentState.IDLE
        print(f"[{self.name}] VAD ініціалізовано | Noise Floor: {self.noise_floor}, Threshold: {self.vad_threshold}")
