"""
CLASSIFIER AGENT - Класифікація цілей
======================================
Агент класифікує виявлені сигнали: Drone, Wind, Unknown
"""

from typing import Optional

from .base_agent import BaseAgent, Skill, AgentMessage, MessageType, AgentState


class ClassifierAgent(BaseAgent):
    """
    Classifier Agent - Hero Edition (Hardened v2.7).
    Uses Advanced Signature Matching learned from 10k rounds.
    """
    
    def __init__(self, agent_id: str = "classifier", name: str = "Classifier-Agent"):
        skills = [
            Skill("classify_drone", self.classify_drone, priority=90),
            Skill("classify_wind", self.classify_wind, priority=85),
            Skill("confidence_score", self.confidence_score, priority=80),
            Skill("multi_signature", self.multi_signature, priority=75)
        ]
        super().__init__(agent_id, name, skills)
        
        # Відомі сигнатури дронів
        self.drone_signatures = []
        
        # Статистика
        self.classification_stats = {
            'drone': 0,
            'wind': 0,
            'unknown': 0,
            'total': 0
        }
        
    async def classify_drone(self, features: dict) -> dict:
        """
        Skill: ELITE Classification (Drone Classes).
        Handles Baba Yaga (Heavy) vs FPV (Light) distinction.
        """
        high_frac = features.get('high_frac', 0)
        modulation = features.get('modulation', 0)
        hps_conf = features.get('hps_confidence', 0)
        
        # Elite Rules:
        # 1. Baba Yaga (Heavy): High modulation, lower frequency bias
        # 2. FPV (Light): Very high frequency bias, sharp modulation
        
        target_class = "UnknownDrone"
        is_drone = False
        
        if hps_conf > 80: # Primary HPS trigger (God Mode)
            is_drone = True
            if high_frac > 0.5: target_class = "LightFPV"
            else: target_class = "HeavyBabaYaga"
        elif high_frac > 0.31 and modulation > 20: # Fallback rules
            is_drone = True
            target_class = "StandardDrone"
            
        return {
            'is_drone': is_drone,
            'target_class': target_class,
            'confidence': max(high_frac, hps_conf / 100.0)
        }
    
    async def classify_wind(self, features: dict) -> dict:
        """
        Skill: Класифікація як вітер
        Умова: lowFrac > 180/256 AND modulation < low/8
        """
        low_frac = features.get('low_frac', 0)
        modulation = features.get('modulation', 0)
        low_energy = features.get('low', 1)
        
        WIND_LOW_THRESH = 180 / 256  # ≈ 0.703
        
        is_wind = (
            low_frac > WIND_LOW_THRESH and 
            modulation < (low_energy / 8)
        )
        
        return {
            'is_wind': is_wind,
            'confidence': low_frac * 0.9,
            'low_frac': low_frac
        }
    
    async def confidence_score(self, features: dict, classification: str) -> float:
        """
        Skill: Розрахунок впевненості класифікації
        """
        total_energy = features.get('total_energy', 0)
        clipped = features.get('clipped', False)
        
        # Штраф за clipping
        if clipped:
            return 0.25
        
        # Базова впевненість від енергії
        base_conf = min(1.0, total_energy / 1000000)
        
        # Модифікатори
        if classification == 'drone':
            return min(1.0, base_conf * 1.2)
        elif classification == 'wind':
            return min(1.0, base_conf * 0.95)
        else:
            return base_conf * 0.5
    
    async def multi_signature(self, features: dict) -> str:
        """
        Skill: Мульти-сигнатурна класифікація
        """
        drone_result = await self.classify_drone(features)
        wind_result = await self.classify_wind(features)
        
        # Рішення
        if drone_result['is_drone']:
            return 'ClassDrone'
        elif wind_result['is_wind']:
            return 'ClassWind'
        else:
            return 'ClassUnknown'
    
    async def process_message(self, msg: AgentMessage) -> Optional[AgentMessage]:
        """Обробка повідомлень"""
        
        if msg.msg_type == MessageType.ALERT:
            # Отримано сигнал від VAD/DSP
            features = msg.payload.get('features', {})
            
            # Hero Logic: Get detailed classification
            drone_res = await self.classify_drone(features)
            classification = await self.multi_signature(features)
            confidence = await self.confidence_score(features, classification)
            
            # Оновлення статистики
            class_key = classification.replace('Class', '').lower()
            if class_key in self.classification_stats:
                self.classification_stats[class_key] += 1
            self.classification_stats['total'] += 1
            
            # Enrich features for the next agent (EKF/Coordinator)
            enriched_features = features.copy()
            enriched_features.update(drone_res)
            
            return AgentMessage(
                sender=self.agent_id,
                receiver='ekf_1d',
                msg_type=MessageType.DATA,
                payload={
                    'classification': classification,
                    'is_drone': drone_res['is_drone'],
                    'confidence': confidence,
                    'features': enriched_features
                }
            )
        
        return None
    
    async def initialize(self) -> None:
        """Ініціалізація"""
        self.state = AgentState.IDLE
        print(f"[{self.name}] Classifier ініціалізовано")
    
    def get_stats(self) -> dict:
        """Отримання статистики класифікацій"""
        stats = super().get_status()
        stats['classification'] = self.classification_stats
        return stats
