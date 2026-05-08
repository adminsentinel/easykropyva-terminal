from __future__ import annotations

import math
from typing import Any


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _angle_norm(angle_deg: float) -> float:
    angle = float(angle_deg) % 360.0
    if angle < 0.0:
        angle += 360.0
    return angle


class InformationFilterCore:
    def __init__(
        self,
        *,
        decay: float = 0.988,
        min_lambda: float = 0.85,
        coherence_threshold: float = 0.35,
        decision_threshold: float = 0.455,
    ) -> None:
        self.decay = float(decay)
        self.min_lambda = float(min_lambda)
        self.coherence_threshold = float(coherence_threshold)
        self.decision_threshold = float(decision_threshold)
        self.reset()

    def reset(self) -> None:
        self.lambda_value = 1e-6
        self.eta_x = 0.0
        self.eta_y = 0.0
        self.last_local_lambda = 0.0
        self.last_angle_deg = 0.0
        self.last_evidence_conf = 0.0

    @staticmethod
    def _confidence_to_lambda(
        evidence_conf: float,
        snr: float,
        lora_success: bool,
        spoof_attempt: bool,
        spoof_blocked: bool,
    ) -> float:
        conf = _clamp(float(evidence_conf), 0.0, 1.0)
        snr_term = _clamp((float(snr) - 3.0) / 12.0, 0.0, 0.25)
        link_term = 0.08 if bool(lora_success) else -0.04
        spoof_term = 0.0
        if bool(spoof_attempt) and (not bool(spoof_blocked)):
            spoof_term = -0.12
        lam = 0.35 + 2.4 * conf + snr_term + link_term + spoof_term
        return _clamp(lam, 0.05, 3.80)

    def _apply_decay(self) -> None:
        d = _clamp(self.decay, 0.90, 1.0)
        self.eta_x *= d
        self.eta_y *= d
        self.lambda_value = max(1e-6, self.lambda_value * d)

    def _merge_vector(self, angle_deg: float, lam: float) -> None:
        theta = math.radians(_angle_norm(angle_deg))
        self.eta_x += float(lam) * math.cos(theta)
        self.eta_y += float(lam) * math.sin(theta)
        self.lambda_value += float(lam)

    def update_local(
        self,
        *,
        angle_deg: float,
        evidence_conf: float,
        snr: float,
        lora_success: bool,
        spoof_attempt: bool,
        spoof_blocked: bool,
    ) -> dict[str, Any]:
        self._apply_decay()
        local_lambda = self._confidence_to_lambda(
            evidence_conf=evidence_conf,
            snr=snr,
            lora_success=lora_success,
            spoof_attempt=spoof_attempt,
            spoof_blocked=spoof_blocked,
        )
        self._merge_vector(angle_deg, local_lambda)
        self.last_local_lambda = local_lambda
        self.last_angle_deg = _angle_norm(angle_deg)
        self.last_evidence_conf = _clamp(evidence_conf, 0.0, 1.0)
        out = self.current_decision()
        out["local_lambda"] = local_lambda
        out["packet"] = self.build_packet(angle_deg, local_lambda)
        return out

    def merge_packet(self, packet: dict[str, Any]) -> bool:
        lam = float(packet.get("lambda", 0.0))
        eta_x = float(packet.get("eta_x", 0.0))
        eta_y = float(packet.get("eta_y", 0.0))
        if lam <= 0.0:
            return False
        if abs(eta_x) > lam + 1e-6 or abs(eta_y) > lam + 1e-6:
            return False
        self.eta_x += eta_x
        self.eta_y += eta_y
        self.lambda_value += lam
        return True

    def export_packet(self) -> dict[str, float]:
        return {
            "lambda": float(self.lambda_value),
            "eta_x": float(self.eta_x),
            "eta_y": float(self.eta_y),
        }

    def build_packet(self, angle_deg: float, lam: float) -> dict[str, float]:
        theta = math.radians(_angle_norm(angle_deg))
        return {
            "lambda": float(lam),
            "eta_x": float(lam) * math.cos(theta),
            "eta_y": float(lam) * math.sin(theta),
        }

    def current_decision(self) -> dict[str, float | bool]:
        lam = max(self.lambda_value, 1e-6)
        mux = self.eta_x / lam
        muy = self.eta_y / lam
        coherence = _clamp(math.sqrt(mux * mux + muy * muy), 0.0, 1.0)
        precision_term = _clamp(self.last_local_lambda / 2.5, 0.0, 1.0)
        score = _clamp(
            0.68 * coherence
            + 0.24 * self.last_evidence_conf
            + 0.08 * precision_term,
            0.0,
            1.0,
        )
        threshold = self.decision_threshold
        predicted = (
            coherence >= self.coherence_threshold
            and score >= threshold
            and self.last_evidence_conf >= 0.34
            and self.last_local_lambda >= self.min_lambda
        )
        angle = _angle_norm(math.degrees(math.atan2(muy, mux)))
        return {
            "predicted": bool(predicted),
            "score": float(score),
            "threshold": float(threshold),
            "lambda": float(lam),
            "coherence": float(coherence),
            "angle_deg": float(angle),
        }

    def snapshot(self) -> dict[str, float]:
        return {
            "lambda": float(self.lambda_value),
            "eta_x": float(self.eta_x),
            "eta_y": float(self.eta_y),
            "last_local_lambda": float(self.last_local_lambda),
            "last_angle_deg": float(self.last_angle_deg),
            "last_evidence_conf": float(self.last_evidence_conf),
            "decay": float(self.decay),
            "min_lambda": float(self.min_lambda),
            "coherence_threshold": float(self.coherence_threshold),
            "decision_threshold": float(self.decision_threshold),
        }

    def load(self, state: dict[str, Any] | None) -> bool:
        if not state:
            return False
        self.lambda_value = max(1e-6, float(state.get("lambda", self.lambda_value)))
        self.eta_x = float(state.get("eta_x", self.eta_x))
        self.eta_y = float(state.get("eta_y", self.eta_y))
        self.last_local_lambda = float(state.get("last_local_lambda", self.last_local_lambda))
        self.last_angle_deg = _angle_norm(float(state.get("last_angle_deg", self.last_angle_deg)))
        self.last_evidence_conf = _clamp(float(state.get("last_evidence_conf", self.last_evidence_conf)), 0.0, 1.0)
        self.decay = float(state.get("decay", self.decay))
        self.min_lambda = float(state.get("min_lambda", self.min_lambda))
        self.coherence_threshold = float(state.get("coherence_threshold", self.coherence_threshold))
        self.decision_threshold = float(state.get("decision_threshold", self.decision_threshold))
        return True
