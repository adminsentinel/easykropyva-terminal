"""
TRIANGULATION AGENT - Тріангуляція та RANSAC
==============================================
Агент виконує тріангуляцію позиції цілі за пеленгами.
"""

import math
from typing import List, Tuple, Optional
from .base_agent import BaseAgent, Skill, AgentMessage, MessageType, AgentState


class TriangulationAgent(BaseAgent):
    """
    Triangulation Agent - тріангуляція позиції з RANSAC.
    """
    
    def __init__(self, agent_id: str = "triangulation", name: str = "Triangulation-Agent"):
        skills = [
            Skill("bearing_intersect", self.bearing_intersect, priority=90),
            Skill("ransac_lite", self.ransac_lite, priority=85),
            Skill("sin_cos_lookup", self.sin_q15, priority=80)
        ]
        super().__init__(agent_id, name, skills)
        
        # Sin/Cos LUT (Q15) - 91 елемент для 0°..90°
        self.sin_lut = self._build_sin_lut()
        
        # Відомі позиції вузлів (x, y в мм)
        self.node_positions = {}
        
        # RANSAC параметри
        self.inlier_threshold_mm = 100
        self.min_inliers_ratio = 0.5
        
    def _build_sin_lut(self) -> List[int]:
        """Побудова Sin LUT (Q15)"""
        lut = []
        for i in range(91):
            angle_rad = i * math.pi / 180
            sin_val = math.sin(angle_rad)
            lut.append(int(sin_val * 32768))
        return lut
    
    def sin_q15(self, deg: int) -> int:
        """Sin через LUT"""
        # Нормалізація до 0-360
        while deg < 0:
            deg += 360
        while deg >= 360:
            deg -= 360
        
        if deg <= 90:
            return self.sin_lut[deg]
        elif deg <= 180:
            return self.sin_lut[180 - deg]
        elif deg <= 270:
            return -self.sin_lut[deg - 180]
        else:
            return -self.sin_lut[360 - deg]
    
    def cos_q15(self, deg: int) -> int:
        """Cos через LUT"""
        return self.sin_q15((deg + 90) % 360)
    
    async def bearing_intersect(
        self, 
        p1_x: int, p1_y: int, bearing1_deg: float,
        p2_x: int, p2_y: int, bearing2_deg: float
    ) -> Optional[Tuple[int, int]]:
        """
        Skill: Перетин двох пеленгів (метод Крамера)
        """
        # Вектори напрямку
        dx1 = self.cos_q15(int(bearing1_deg))
        dy1 = self.sin_q15(int(bearing1_deg))
        dx2 = self.cos_q15(int(bearing2_deg))
        dy2 = self.sin_q15(int(bearing2_deg))
        
        # Дельта позицій
        dx_a = p2_x - p1_x
        dy_a = p2_y - p1_y
        
        # Векторний добуток в Q15
        det = dx1 * dy2 - dy1 * dx2  # Q30
        
        # Захист від паралельних променів
        max_det = max(abs(dx1), abs(dy1), abs(dx2), abs(dy2)) * 100
        if abs(det) < max_det // 100:
            return None
        
        # Cramer's rule (в Q15)
        c1 = dx_a * dy2 - dy_a * dx2
        c2 = dy_a * dx1 - dx_a * dy1
        
        x = (c1 * 32768) // det
        y = (c2 * 32768) // det
        
        # Повертаємо у мм
        return (p1_x + x, p1_y + y)
    
    async def ransac_lite(self, node_bearings: List[dict]) -> Optional[dict]:
        """
        Skill: RANSAC-Lite для знаходження позиції
        All-pairs intersection + inlier counting
        """
        if len(node_bearings) < 2:
            return None
        
        n = len(node_bearings)
        best_position = None
        best_score = 0
        best_inliers = []
        
        # Всі пари (n*(n-1)/2)
        for i in range(n):
            for j in range(i + 1, n):
                node1 = node_bearings[i]
                node2 = node_bearings[j]
                
                # Перетин
                pos = await self.bearing_intersect(
                    node1['x'], node1['y'], node1['bearing'],
                    node2['x'], node2['y'], node2['bearing']
                )
                
                if pos is None:
                    continue
                
                # Підрахунок inliers
                inliers = []
                for k, node in enumerate(node_bearings):
                    if k == i or k == j:
                        continue
                    
                    dist = self._perpendicular_distance(
                        pos[0], pos[1],
                        node['x'], node['y'], node['bearing']
                    )
                    
                    if dist < self.inlier_threshold_mm:
                        inliers.append(k)
                
                # Score = сума Confidence inliers
                score = sum(node_bearings[idx].get('confidence', 1.0) for idx in inliers)
                
                if len(inliers) >= n * self.min_inliers_ratio and score > best_score:
                    best_score = score
                    best_position = pos
                    best_inliers = [i, j] + inliers
        
        if best_position is None:
            return None
        
        # Weighted refinement всіх inliers
        refined_pos = self._weighted_refinement(best_position, node_bearings, best_inliers)
        
        return {
            'position': refined_pos,
            'score': best_score,
            'inliers_count': len(best_inliers),
            'total_nodes': n
        }
    
    def _perpendicular_distance(
        self, 
        px: int, py: int, 
        nx: int, ny: int, 
        bearing_deg: float
    ) -> float:
        """Відстань від точки до лінії пеленгу"""
        # Напрямок пеленгу
        dx = self.cos_q15(int(bearing_deg))
        dy = self.sin_q15(int(bearing_deg))
        
        # Вектор до точки
        vx = px - nx
        vy = py - ny
        
        # Проекція
        proj = (vx * dx + vy * dy) / 32768
        
        # Точка на лінії
        lx = nx + (dx * proj) // 32768
        ly = ny + (dy * proj) // 32768
        
        # Відстань
        return math.sqrt((px - lx)**2 + (py - ly)**2)
    
    def _weighted_refinement(
        self, 
        init_pos: Tuple[int, int], 
        nodes: List[dict], 
        inliers: List[int]
    ) -> Tuple[int, int]:
        """Зважене уточнення позиції"""
        total_weight = 0
        sum_x = 0
        sum_y = 0
        
        for idx in inliers:
            node = nodes[idx]
            weight = node.get('confidence', 1.0)
            
            sum_x += int(init_pos[0] * weight)
            sum_y += int(init_pos[1] * weight)
            total_weight += weight
        
        if total_weight > 0:
            return (sum_x // int(total_weight), sum_y // int(total_weight))
        
        return init_pos
    
    def set_node_position(self, node_id: str, x: int, y: int) -> None:
        """Встановлення позиції вузла"""
        self.node_positions[node_id] = {'x': x, 'y': y}
    
    async def process_message(self, msg: AgentMessage) -> Optional[AgentMessage]:
        """Обробка повідомлень"""
        
        if msg.msg_type == MessageType.DATA:
            # Збір пеленгів від інших агентів
            bearings = msg.payload.get('bearings', [])
            
            if len(bearings) >= 2:
                result = await self.ransac_lite(bearings)
                
                return AgentMessage(
                    sender=self.agent_id,
                    receiver='coordinator',
                    msg_type=MessageType.RESULT,
                    payload=result
                )
        
        return None
    
    async def initialize(self) -> None:
        """Ініціалізація"""
        self.state = AgentState.IDLE
        print(f"[{self.name}] Triangulation ініціалізовано | LUT: {len(self.sin_lut)} entries")
