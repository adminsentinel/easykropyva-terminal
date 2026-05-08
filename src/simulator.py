"""
SENTINEL-QC ECHELON AGENTS - Симулятор системи
================================================
Симуляція роботи рою агентів з візуалізацією.
"""

import asyncio
import random
import math
from typing import List, Dict
from .swarm_coordinator import SwarmCoordinator


class TargetSimulator:
    """Симулятор цілей"""
    
    def __init__(self):
        self.targets = []
        self.energy_base = 30000
        
    def add_target(self, angle: float, speed: float, signature: str = 'drone'):
        self.targets.append({
            'angle': angle,
            'speed': speed,
            'signature': signature,
            'active': True
        })
    
    def update(self, dt: float):
        for t in self.targets:
            if t['active']:
                # Рух
                t['angle'] = (t['angle'] + t['speed'] * dt) % 360
                
    def get_energy_at_angle(self, angle: float) -> int:
        total = 0
        for t in self.targets:
            if t['active']:
                diff = min(abs(angle - t['angle']), 360 - abs(angle - t['angle']))
                if diff < 15:  # В межах beamwidth
                    # Gaussian falloff
                    strength = math.exp(-diff * diff / 50) * self.energy_base
                    total += int(strength)
        return total


async def simulate_swarm():
    """Запуск симуляції"""
    print("\n" + "=" * 60)
    print("SENTINEL-QC ECHELON AGENTS - СИМУЛЯТОР")
    print("=" * 60 + "\n")
    
    # Створення координатора
    coordinator = SwarmCoordinator(node_id=42, role="SENSOR")
    await coordinator.init_agents()
    
    # Симулятор цілей
    target_sim = TargetSimulator()
    target_sim.add_target(angle=45, speed=2, signature='drone')
    target_sim.add_target(angle=180, speed=1.5, signature='drone')
    
    # Імітація LoRa отримання даних
    async def simulate_lora():
        while coordinator._running:
            # Симуляція отримання даних від сусіда
            neighbor_data = {
                'angle_q16': int(90 * 65536 / 360),  # 90°
                'confidence': 0.8,
                'node_id': 'node_1'
            }
            
            # Обробка
            wavefield = coordinator.agents.get('wavefield')
            if wavefield:
                await wavefield.inject_energy(90, 40000, width=10)
            
            await asyncio.sleep(2)  # Кожні 2 секунди
    
    # Головний цикл
    print("[Симуляція] Запуск...")
    
    # Запуск задач
    lora_task = asyncio.create_task(simulate_lora())
    main_task = asyncio.create_task(coordinator.run())
    
    # Симуляція 60 секунд
    for i in range(60):
        await asyncio.sleep(1)
        
        # Оновлення цілей
        target_sim.update(1)
        
        # Отримання енергії в напрямку цілі
        for t in target_sim.targets:
            if t['active']:
                energy = target_sim.get_energy_at_angle(t['angle'])
                coordinator.system_status['last_energy'] = energy
        
        # Вивід кожні 10 секунд
        if (i + 1) % 10 == 0:
            status = coordinator.get_system_status()
            print(f"\n--- Час: {i+1}с ---")
            print(f"Frames: {status['frame_count']}, Uptime: {status['uptime']:.1f}с")
            
            wavefield = coordinator.agents.get('wavefield')
            if wavefield:
                peak_angle = wavefield.get_peak_angle()
                peak_energy = wavefield.energy[peak_angle]
                print(f"WaveField: Peak @ {peak_angle}° (E={peak_energy})")
            
            energy_gov = coordinator.agents.get('energy')
            if energy_gov:
                status_eg = energy_gov.get_status()
                print(f"EnergyGov: {status_eg['current_state']} ({status_eg['consumption_ua']}мкА)")
    
    # Зупинка
    coordinator.stop()
    await asyncio.sleep(0.1)
    
    print("\n" + "=" * 60)
    print("Симуляція завершена")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(simulate_swarm())
