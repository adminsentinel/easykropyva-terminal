"""
Adaptive Fusion Agent
=====================
Fuses multiple agent signals into one detection score and continuously adapts
to previous runs (experience state).
"""

from __future__ import annotations

from typing import Any, Optional

from .base_agent import AgentMessage, AgentState, BaseAgent, MessageType, Skill


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class AdaptiveFusionAgent(BaseAgent):
    """
    Custom algorithm:
    1. Weighted fusion of classifier/VAD/HPS/energy/LoRa/memory
    2. Dynamic threshold based on learned false-alarm/recall priors
    3. Online bias update from truth feedback
    """

    def __init__(self, agent_id: str = "adaptive_fusion", name: str = "AdaptiveFusion-Agent"):
        skills = [
            Skill("fuse_decision", self.fuse_decision, priority=100),
            Skill("update_experience", self.update_experience, priority=95),
            Skill("load_experience", self.load_experience, priority=90),
        ]
        super().__init__(agent_id, name, skills)

        self.base_threshold = 0.58
        self.learning_rate = 0.06
        self.global_bias = 0.0

        self.experience = {
            "global": {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
            "global_metrics": {"precision": 0.5, "recall": 0.5, "false_alarm_rate": 0.2},
            "scenarios": {},
        }

    @staticmethod
    def _empty_scenario() -> dict[str, float | int]:
        return {
            "tp": 0,
            "fp": 0,
            "tn": 0,
            "fn": 0,
            "precision": 0.5,
            "recall": 0.5,
            "false_alarm_rate": 0.2,
        }

    @staticmethod
    def _vad_signal(vad_label: str) -> float:
        label = (vad_label or "").lower()
        if label == "drone":
            return 1.0
        if label in {"unknown", "active"}:
            return 0.35
        if label in {"wind", "quiet", "clipped"}:
            return 0.0
        return 0.15

    @staticmethod
    def _scenario_prior(metrics: dict[str, Any]) -> float:
        precision = float(metrics.get("precision", 0.5))
        recall = float(metrics.get("recall", 0.5))
        false_alarm = float(metrics.get("false_alarm_rate", 0.2))
        # Positive if quality is good, negative if false alarms dominate.
        return _clamp(0.30 * precision + 0.20 * recall - 0.50 * false_alarm, -0.25, 0.18)

    @staticmethod
    def _metrics_from_counts(counts: dict[str, int]) -> dict[str, float]:
        tp = int(counts.get("tp", 0))
        fp = int(counts.get("fp", 0))
        tn = int(counts.get("tn", 0))
        fn = int(counts.get("fn", 0))
        precision = tp / (tp + fp) if (tp + fp) else 0.5
        recall = tp / (tp + fn) if (tp + fn) else 0.5
        false_alarm = fp / (fp + tn) if (fp + tn) else 0.2
        return {
            "precision": precision,
            "recall": recall,
            "false_alarm_rate": false_alarm,
        }

    def _get_scenario_metrics(self, scenario: str) -> dict[str, float | int]:
        scenarios = self.experience.setdefault("scenarios", {})
        data = scenarios.setdefault(scenario, {})
        baseline = self._empty_scenario()
        for key, value in baseline.items():
            data.setdefault(key, value)
        return data

    async def load_experience(self, payload: Optional[dict[str, Any]]) -> bool:
        if not payload:
            return False
        if "global" in payload:
            self.experience["global"] = dict(payload["global"])
        if "global_metrics" in payload:
            self.experience["global_metrics"] = dict(payload["global_metrics"])
        else:
            self.experience["global_metrics"] = self._metrics_from_counts(self.experience["global"])
        if "scenarios" in payload:
            loaded = {}
            for name, data in payload["scenarios"].items():
                # Backward compatibility with old format that kept only metrics.
                row = dict(self._empty_scenario())
                row.update(dict(data))
                loaded[name] = row
            self.experience["scenarios"] = loaded
        self.global_bias = float(payload.get("global_bias", self.global_bias))
        return True

    async def fuse_decision(self, observation: dict[str, Any]) -> dict[str, Any]:
        scenario = str(observation.get("scenario", "default"))
        scenario_metrics = self._get_scenario_metrics(scenario)

        classifier_conf = _clamp(float(observation.get("classifier_conf", 0.0)), 0.0, 1.0)
        vad_signal = self._vad_signal(str(observation.get("vad_label", "")))
        hps = _clamp(float(observation.get("hps_confidence", 0.0)) / 100.0, 0.0, 1.0)
        energy_norm = _clamp(float(observation.get("energy", 0.0)) / 90_000.0, 0.0, 1.0)
        memory_support = _clamp(float(observation.get("memory_support", 0.0)), 0.0, 1.0)

        snr = float(observation.get("snr", 0.0))
        lora_success = bool(observation.get("lora_success", False))
        lora_quality = 1.0 if lora_success else _clamp((snr - 2.0) / 10.0, 0.0, 1.0)

        spoof_attempt = bool(observation.get("spoof_attempt", False))
        spoof_blocked = bool(observation.get("spoof_blocked", False))
        spoof_term = 0.0
        if spoof_attempt and spoof_blocked:
            spoof_term = 0.05
        elif spoof_attempt and not spoof_blocked:
            spoof_term = -0.08

        scenario_prior = self._scenario_prior(scenario_metrics)
        agreement_bonus = 0.04 if (classifier_conf >= 0.62 and hps >= 0.62) else 0.0
        disagreement_penalty = -0.05 if (classifier_conf < 0.45 and vad_signal < 0.35 and hps < 0.45) else 0.0

        score = (
            0.34 * classifier_conf
            + 0.14 * vad_signal
            + 0.20 * hps
            + 0.08 * energy_norm
            + 0.10 * lora_quality
            + 0.06 * memory_support
            + spoof_term
            + scenario_prior
            + self.global_bias
            + agreement_bonus
            + disagreement_penalty
        )
        score = _clamp(score, 0.0, 1.0)

        # Dynamic threshold gets stricter when scenario prior false alarms are high.
        precision = float(scenario_metrics.get("precision", 0.5))
        recall = float(scenario_metrics.get("recall", 0.5))
        false_alarm = float(scenario_metrics.get("false_alarm_rate", 0.2))
        threshold = (
            self.base_threshold
            + 0.22 * false_alarm
            + 0.12 * (1.0 - precision)
            - 0.04 * recall
            - 0.03 * memory_support
        )

        strong_votes = 0
        strong_votes += int(classifier_conf >= 0.58)
        strong_votes += int(hps >= 0.62)
        strong_votes += int(vad_signal >= 0.90)
        strong_votes += int(lora_quality >= 0.70)
        strong_votes += int(energy_norm >= 0.48)
        strong_votes += int(memory_support >= 0.70)

        if strong_votes <= 2:
            threshold += 0.07
        if classifier_conf < 0.45 and hps < 0.50:
            threshold += 0.07
        if (not lora_success) and snr < 3.5:
            threshold += 0.04

        threshold = _clamp(threshold, 0.48, 0.88)
        hard_gate = strong_votes >= 2 and (classifier_conf >= 0.48 or hps >= 0.62 or vad_signal >= 0.90)
        predicted = hard_gate and score >= threshold
        return {
            "score": score,
            "threshold": threshold,
            "predicted": predicted,
            "scenario_prior": scenario_prior,
            "strong_votes": strong_votes,
        }

    async def update_experience(
        self,
        scenario: str,
        truth_target: bool,
        predicted_target: bool,
        score: float,
    ) -> dict[str, Any]:
        g = self.experience.setdefault("global", {"tp": 0, "fp": 0, "tn": 0, "fn": 0})
        s = self._get_scenario_metrics(scenario)
        if truth_target and predicted_target:
            g["tp"] += 1
            s["tp"] = int(s.get("tp", 0)) + 1
        elif (not truth_target) and predicted_target:
            g["fp"] += 1
            s["fp"] = int(s.get("fp", 0)) + 1
        elif truth_target and (not predicted_target):
            g["fn"] += 1
            s["fn"] = int(s.get("fn", 0)) + 1
        else:
            g["tn"] += 1
            s["tn"] = int(s.get("tn", 0)) + 1

        # Online correction (calibration-like).
        y = 1.0 if truth_target else 0.0
        err = y - float(score)
        self.global_bias = _clamp(self.global_bias + self.learning_rate * err * 0.35, -0.24, 0.22)
        if predicted_target and (not truth_target):
            self.global_bias = _clamp(self.global_bias - self.learning_rate * 0.30, -0.24, 0.22)
        elif truth_target and (not predicted_target):
            self.global_bias = _clamp(self.global_bias + self.learning_rate * 0.18, -0.24, 0.22)

        # Update scenario/global metrics from respective counts.
        s_metrics = self._metrics_from_counts(
            {
                "tp": int(s.get("tp", 0)),
                "fp": int(s.get("fp", 0)),
                "tn": int(s.get("tn", 0)),
                "fn": int(s.get("fn", 0)),
            }
        )
        s.update(s_metrics)

        self.experience["global_metrics"] = self._metrics_from_counts(g)

        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        return {
            "global": dict(self.experience.get("global", {})),
            "global_metrics": dict(self.experience.get("global_metrics", {})),
            "scenarios": dict(self.experience.get("scenarios", {})),
            "global_bias": self.global_bias,
        }

    async def process_message(self, msg: AgentMessage) -> Optional[AgentMessage]:
        if msg.msg_type == MessageType.COMMAND:
            payload = msg.payload or {}
            action = payload.get("action")
            if action == "fuse":
                fused = await self.fuse_decision(payload.get("observation", {}))
                return AgentMessage(
                    sender=self.agent_id,
                    receiver=payload.get("reply_to", "coordinator"),
                    msg_type=MessageType.RESULT,
                    payload=fused,
                )
        return None

    async def initialize(self) -> None:
        self.state = AgentState.IDLE
        print(f"[{self.name}] Initialized | skills={list(self.skills.keys())}")
