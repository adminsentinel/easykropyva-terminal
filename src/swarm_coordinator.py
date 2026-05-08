"""
SENTINEL-QC ECHELON AGENTS - Swarm Coordinator
================================================
Координатор рою агентів. Керує ініціалізацією, запуском та комунікацією агентів.
"""

import asyncio
import time
from typing import Dict, Optional, TYPE_CHECKING

# Lazy imports для уникнення циклічних залежностей
AGENTS_AVAILABLE = False
_agent_classes = None

def _get_agent_classes():
    global _agent_classes
    if _agent_classes is None:
        try:
            from .dsp_agent import DSPAgent
            from .vad_agent import VADAgent
            from .classifier_agent import ClassifierAgent
            from .ekf_tracker_agent import EKFTrackerAgent
            from .wavefield_agent import WaveFieldAgent
            from .kuramoto_agent import KuramotoAgent
            from .consensus_agent import ConsensusAgent
            from .memory_agent import MemoryAgent
            from .triangulation_agent import TriangulationAgent
            from .lora_agent import LoRaAgent
            from .mesh_router_agent import MeshRouterAgent
            from .energy_gov_agent import EnergyGovAgent
            from .ew_defense_agent import EWDefenseAgent
            from .target_acq_agent import TargetAcquisitionAgent
            from .threat_intel_agent import ThreatIntelAgent
            
            _agent_classes = {
                'dsp': DSPAgent,
                'vad': VADAgent,
                'classifier': ClassifierAgent,
                'ekf': EKFTrackerAgent,
                'wavefield': WaveFieldAgent,
                'kuramoto': KuramotoAgent,
                'consensus': ConsensusAgent,
                'memory': MemoryAgent,
                'triangulation': TriangulationAgent,
                'lora': LoRaAgent,
                'mesh': MeshRouterAgent,
                'energy': EnergyGovAgent,
                'ew_defense': EWDefenseAgent,
                'threat_intel': ThreatIntelAgent,
                'target_acq': TargetAcquisitionAgent,
            }
        except ImportError as e:
            print(f"[WARN] Some agents not available: {e}")
            _agent_classes = {}
    return _agent_classes


class SwarmCoordinator:
    """
    Swarm Coordinator - Командир рою агентів.
    Героїчна версія з повним керуванням системою.
    """
    
    def __init__(self, agent_id: str = "coordinator", name: str = "Swarm-Commander", node_id: int = 0, role: str = "SENSOR"):
        self.agent_id = agent_id
        self.name = name
        self.node_id = node_id
        self.role = role
        self.active_targets = 0
        
        # Агенти системи
        self.agents: Dict = {}
        
        # Статус системи
        self.system_status = {
            'running': False,
            'frame_count': 0,
            'uptime': 0,
            'last_energy': 0,
            'peak_angle': 0,
            'peak_energy': 0,
        }
        
        # Час запуску
        self._start_time = 0
        self._running = False
        
        # Синхронізація
        self.sync_lock = asyncio.Lock()
        
        print(f"[COMMANDER] Node {node_id} initialized as {role}")
    
    async def initialize(self) -> None:
        """Ініціалізація координатора"""
        print(f"[{self.name}] Координатор готовий | Node: {self.node_id}, Role: {self.role}")
    
    async def init_agents(self) -> None:
        """Ініціалізація всіх агентів системи"""
        print(f"\n[{self.name}] === ІНІЦІАЛІЗАЦІЯ АГЕНТІВ ===")
        
        agent_classes = _get_agent_classes()
        
        if agent_classes:
            for name, AgentClass in agent_classes.items():
                try:
                    self.agents[name] = AgentClass()
                    print(f"[{self.name}] Created {name}")
                except Exception as e:
                    print(f"[WARN] Agent {name} creation failed: {e}")
            
            # Ініціалізація кожного агента
            for name, agent in self.agents.items():
                try:
                    if hasattr(agent, 'initialize'):
                        await agent.initialize()
                except Exception as e:
                    print(f"[WARN] Agent {name} init failed: {e}")
            
            print(f"[{self.name}] Ініціалізовано {len(self.agents)} агентів")
        else:
            print(f"[{self.name}] Режим демо - агенти не завантажені")
    
    async def orchestrate(self, msg) -> None:
        """Оркестрація - головна логіка координації"""
        
        msg_type = msg.get('type', 'data') if isinstance(msg, dict) else 'data'
        
        if msg_type == 'alert':
            print(f"\n[COMMANDER] ALERT! Target detected")
            self.active_targets += 1
            
            if 'wavefield' in self.agents and hasattr(self.agents['wavefield'], 'process_message'):
                await self.agents['wavefield'].process_message(msg)
            
        elif msg_type == 'data':
            payload = msg.get('payload', {}) if isinstance(msg, dict) else {}
            
            if 'energy' in payload:
                self.system_status['last_energy'] = payload['energy']
                
                if 'energy' in self.agents:
                    eg = self.agents['energy']
                    if hasattr(eg, 'update_temperature'):
                        await eg.update_temperature(payload['energy'])
            
        elif msg_type == 'command':
            payload = msg.get('payload', {}) if isinstance(msg, dict) else {}
            cmd = payload.get('action', '')
            
            if cmd == 'inject_target':
                angle = payload.get('angle', 0)
                energy = payload.get('energy', 50000)
                
                if 'wavefield' in self.agents:
                    wf = self.agents['wavefield']
                    if hasattr(wf, 'inject_energy'):
                        await wf.inject_energy(angle, energy)
                        print(f"[COMMANDER] Target injected @ {angle} deg (E={energy})")
    
    async def process_message(self, msg) -> Optional[Dict]:
        """Обробка вхідних повідомлень"""
        await self.orchestrate(msg)
        
        return {
            'status': 'processed',
            'active_targets': self.active_targets,
            'node_id': self.node_id
        }
    
    async def run(self) -> None:
        """Головний цикл координатора"""
        self._running = True
        self._start_time = time.time()
        self.system_status['running'] = True
        
        print(f"\n[{self.name}] === ЗАПУСК СИСТЕМИ ===")
        print(f"Node ID: {self.node_id}")
        print(f"Role: {self.role}")
        print(f"Active Agents: {len(self.agents)}")
        
        import random
        frame = 0
        
        while self._running:
            try:
                frame += 1
                self.system_status['frame_count'] = frame
                self.system_status['uptime'] = time.time() - self._start_time
                
                # Інжект демо-цілей кожні 30 секунд
                if frame % 30 == 0:
                    angle = random.randint(0, 359)
                    energy = random.randint(30000, 70000)
                    
                    if 'wavefield' in self.agents:
                        wf = self.agents['wavefield']
                        if hasattr(wf, 'inject_energy'):
                            await wf.inject_energy(angle, energy)
                            self.system_status['peak_angle'] = wf.get_peak_angle()
                            self.system_status['peak_energy'] = wf.energy[self.system_status['peak_angle']]
                
                # Оновлення EnergyGov температури
                if 'energy' in self.agents:
                    eg = self.agents['energy']
                    if hasattr(eg, 'state_transition'):
                        await eg.state_transition(self.system_status['last_energy'])
                
                await asyncio.sleep(1)
                
            except Exception as e:
                print(f"[{self.name}] Error in run loop: {e}")
                await asyncio.sleep(1)
        
        self.system_status['running'] = False
    
    def stop(self) -> None:
        """Зупинка системи"""
        print(f"\n[{self.name}] === ЗУПИНКА ===")
        self._running = False
        
        for name, agent in self.agents.items():
            if hasattr(agent, 'stop'):
                agent.stop()
    
    def get_system_status(self) -> Dict:
        """Отримання статусу системи"""
        return {
            'node_id': self.node_id,
            'role': self.role,
            'running': self.system_status['running'],
            'frame_count': self.system_status['frame_count'],
            'uptime': self.system_status['uptime'],
            'active_targets': self.active_targets,
            'active_agents': len(self.agents),
        }
    
    def get_energy_gov_status(self) -> Dict:
        """Отримання статусу EnergyGov для API"""
        if 'energy' in self.agents:
            eg = self.agents['energy']
            return {
                'current_state': getattr(eg, 'current_state', 'UNKNOWN'),
                'consumption_ua': getattr(eg, 'consumption_ua', 0),
                'temperature': getattr(eg, 'temperature', 0),
            }
        return {'current_state': 'SLEEP', 'consumption_ua': 50, 'temperature': 25}
