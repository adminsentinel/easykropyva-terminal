"""
LORA AGENT - LoRa мережевий шар
================================
Агент керує LoRa зв'язком з frequency hopping та channel quality scoring.
"""

import hashlib
import time
from typing import Dict, Optional
from .base_agent import BaseAgent, Skill, AgentMessage, MessageType, AgentState
from .config import HardwareConfig
from .lora_delta_codec import HybridLoRaDeltaCodec


class LoRaAgent(BaseAgent):
    """
    LoRa Agent - радіо зв'язок через SX1262.
    Підтримує:
    - MTD Frequency Hopping (Anti-Jamming)
    - Channel Quality Scoring
    - 6-становий FSM
    """
    
    def __init__(self, agent_id: str = "lora", name: str = "LoRa-Agent"):
        skills = [
            Skill("frequency_hopping", self.frequency_hopping, priority=90),
            Skill("channel_quality", self.channel_quality, priority=85),
            Skill("tx_packet", self.tx_packet, priority=80),
            Skill("rx_packet", self.rx_packet, priority=80),
            Skill("set_spreading_factor", self.set_spreading_factor, priority=78),
            Skill("encode_hybrid_frame", self.encode_hybrid_frame, priority=76),
        ]
        super().__init__(agent_id, name, skills)
        
        self.config = HardwareConfig()
        
        # FSM стани
        self.fsm_state = 'DeepSleep'
        self.state_transitions = {
            'DeepSleep': ['Standby'],
            'Standby': ['CAD', 'TX', 'RX'],
            'CAD': ['Standby', 'TX', 'RX'],
            'TX': ['Standby'],
            'RX': ['Standby']
        }
        
        # Канали
        self.channel_count = self.config.LORA_CONFIG['channel_count']  # 64
        self.current_channel = 0
        self.spreading_factor = int(self.config.LORA_CONFIG.get('spreading_factor', 9))
        self.delta_codec = HybridLoRaDeltaCodec()
        
        # Channel quality
        self.channel_scores: Dict[int, Dict] = {}
        for ch in range(self.channel_count):
            self.channel_scores[ch] = {
                'snr_ema': -100,  # dB
                'per': 0,         # Packet error rate
                'last_update': 0
            }
        
        # Master key для MTD
        self.master_key = bytes(64)  # SHA-256 key
        
        # Статистика
        self.stats = {
            'tx_count': 0,
            'rx_count': 0,
            'errors': 0,
            'hop_count': 0,
            'delta_key': 0,
            'delta': 0,
            'delta_skipped': 0
        }
    
    def _hash_channel(self, epoch: int, slot: int) -> int:
        """MTD: channel = SHA256(MasterKey || epoch || slot)[0] % 64"""
        data = self.master_key + str(epoch).encode() + str(slot).encode()
        hash_val = hashlib.sha256(data).digest()[0]
        return hash_val % self.channel_count
    
    def _compute_freq(self, channel: int) -> float:
        """Обчислення частоти: 433.05 + channel × 0.025 МГц"""
        return self.config.LORA_CONFIG['frequency_mhz'] + channel * 0.025
    
    async def frequency_hopping(self, epoch: int, slot: int) -> float:
        """
        Skill: Frequency Hopping
        channel = SHA256(MasterKey || epoch || slot)[0] % 64
        """
        self.current_channel = self._hash_channel(epoch, slot)
        freq = self._compute_freq(self.current_channel)
        
        self.stats['hop_count'] += 1
        
        return freq
    
    async def channel_quality(self, snr: float, success: bool) -> int:
        """
        Skill: Channel Quality Scoring
        Score = SNR - PER × 2
        """
        ch = self.current_channel
        cs = self.channel_scores[ch]
        
        # EMA для SNR (вага 7/8 + 1/8 нове)
        alpha_new = 1.0 / 8
        cs['snr_ema'] = cs['snr_ema'] * (1 - alpha_new) + snr * alpha_new
        
        # PER: +5 при помилці, -1 при успіху
        if success:
            cs['per'] = max(0, cs['per'] - 1)
        else:
            cs['per'] = cs['per'] + 5
        
        cs['last_update'] = time.time()
        
        # Score
        score = int(cs['snr_ema'] - cs['per'] * 2)
        
        return score
    
    def _find_best_channel(self) -> int:
        """Знайти найкращий канал за SNR/PER"""
        best_ch = 0
        best_score = -1000
        
        for ch, cs in self.channel_scores.items():
            score = cs['snr_ema'] - cs['per'] * 2
            if score > best_score:
                best_score = score
                best_ch = ch
        
        return best_ch
    
    async def _transition(self, new_state: str) -> bool:
        """Перехід FSM"""
        if new_state in self.state_transitions.get(self.fsm_state, []):
            self.fsm_state = new_state
            return True
        return False
    
    async def tx_packet(self, data: bytes) -> bool:
        """
        Skill: Передача пакету
        """
        await self._transition('TX')
        
        # Симуляція передачі
        success = True  # В реальності - результат SPI
        
        if success:
            self.stats['tx_count'] += 1
        else:
            self.stats['errors'] += 1
        
        await self._transition('Standby')
        
        return success

    async def set_spreading_factor(self, sf: int) -> int:
        """Runtime SF adaptation (bounded to LoRa-safe values)."""
        self.spreading_factor = max(7, min(12, int(sf)))
        return self.spreading_factor

    async def encode_hybrid_frame(self, payload: dict, force_key: bool = False) -> Optional[dict]:
        """
        Key+Delta encoder wrapper.
        Returns dict with packed bytes and metadata or None when frame is skipped.
        """
        encoded = self.delta_codec.encode(payload, timestamp=time.time(), force_key=bool(force_key))
        if encoded is None:
            self.stats['delta_skipped'] += 1
            return None
        if encoded.get('frame_type') == 'key':
            self.stats['delta_key'] += 1
        else:
            self.stats['delta'] += 1
        return encoded
    
    async def rx_packet(self, timeout_ms: int = 1000) -> Optional[bytes]:
        """
        Skill: Прийом пакету
        """
        await self._transition('RX')
        
        # Симуляція прийому
        packet = None  # В реальності - дані з SPI
        
        if packet:
            self.stats['rx_count'] += 1
        else:
            self.stats['errors'] += 1
        
        await self._transition('Standby')
        
        return packet
    
    def set_master_key(self, key: bytes) -> None:
        """Встановлення Master Key для MTD"""
        self.master_key = key
    
    async def process_message(self, msg: AgentMessage) -> Optional[AgentMessage]:
        """Обробка повідомлень"""
        
        if msg.msg_type == MessageType.COMMAND:
            payload = msg.payload
            
            if payload.get('action') == 'send':
                # Передача даних
                data = payload.get('data', b'')
                epoch = payload.get('epoch', int(time.time()))
                slot = payload.get('slot', 0)
                
                freq = await self.frequency_hopping(epoch, slot)
                success = await self.tx_packet(data)
                
                return AgentMessage(
                    sender=self.agent_id,
                    receiver='mesh',
                    msg_type=MessageType.RESULT,
                    payload={
                        'success': success,
                        'frequency': freq,
                        'channel': self.current_channel
                    }
                )
        
        return None
    
    async def initialize(self) -> None:
        """Ініціалізація"""
        await self._transition('Standby')
        self.state = AgentState.IDLE
        print(f"[{self.name}] LoRa ініціалізовано | Channels: {self.channel_count}, Freq: {self._compute_freq(0):.3f} MHz")
