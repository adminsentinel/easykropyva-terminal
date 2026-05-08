from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(value)))


def _angle_diff_deg(a: float, b: float) -> float:
    return abs((float(a) - float(b) + 180.0) % 360.0 - 180.0)


def _signed_to_bits(value: int, width: int) -> int:
    limit_lo = -(1 << (width - 1))
    limit_hi = (1 << (width - 1)) - 1
    v = _clamp_int(value, limit_lo, limit_hi)
    if v < 0:
        v = (1 << width) + v
    return v


class BitWriter:
    def __init__(self) -> None:
        self._value = 0
        self._bits = 0

    def put(self, value: int, width: int) -> None:
        if width <= 0:
            return
        mask = (1 << width) - 1
        self._value = (self._value << width) | (int(value) & mask)
        self._bits += width

    def to_bytes(self) -> bytes:
        if self._bits == 0:
            return b""
        byte_len = (self._bits + 7) // 8
        pad = byte_len * 8 - self._bits
        payload = self._value << pad
        return payload.to_bytes(byte_len, byteorder="big", signed=False)


@dataclass
class RadioObservation:
    target_id: int
    angle_deg: float
    energy: int
    battery_pct: float
    target_present: bool

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RadioObservation":
        return cls(
            target_id=_clamp_int(payload.get("target_id", 0), 0, 255),
            angle_deg=float(payload.get("angle_deg", 0.0)) % 360.0,
            energy=_clamp_int(payload.get("energy", 0), 0, 65535),
            battery_pct=max(0.0, min(100.0, float(payload.get("battery_pct", 100.0)))),
            target_present=bool(payload.get("target_present", False)),
        )


class HybridLoRaDeltaCodec:
    """
    Key + Delta LoRa packing codec.

    Frame types:
    - key: absolute compact packet
    - delta: relative packet against last key/delta state
    """

    FRAME_KEY = 0
    FRAME_DELTA = 1

    MASK_ANGLE = 1 << 0
    MASK_ENERGY = 1 << 1
    MASK_BATTERY = 1 << 2
    MASK_PRESENT = 1 << 3

    def __init__(
        self,
        *,
        key_interval_packets: int = 24,
        angle_epsilon_deg: float = 0.5,
        energy_epsilon: int = 400,
        force_key_seconds: float = 30.0,
    ) -> None:
        self.key_interval_packets = _clamp_int(key_interval_packets, 4, 255)
        self.angle_epsilon_deg = max(0.1, float(angle_epsilon_deg))
        self.energy_epsilon = _clamp_int(energy_epsilon, 1, 100000)
        self.force_key_seconds = max(1.0, float(force_key_seconds))

        self.last_obs: RadioObservation | None = None
        self.last_seq = -1
        self.last_key_ts = 0.0
        self.packets_since_key = 0

    def reset(self) -> None:
        self.last_obs = None
        self.last_seq = -1
        self.last_key_ts = 0.0
        self.packets_since_key = 0

    def _next_seq(self) -> int:
        self.last_seq = (self.last_seq + 1) % 64
        return self.last_seq

    def _needs_forced_key(self, timestamp: float) -> bool:
        if self.last_obs is None:
            return True
        if self.packets_since_key >= self.key_interval_packets:
            return True
        if (float(timestamp) - float(self.last_key_ts)) >= self.force_key_seconds:
            return True
        return False

    def should_skip(self, obs: RadioObservation) -> bool:
        if self.last_obs is None:
            return False
        if int(obs.target_id) != int(self.last_obs.target_id):
            return False
        angle_stable = _angle_diff_deg(obs.angle_deg, self.last_obs.angle_deg) <= self.angle_epsilon_deg
        energy_stable = abs(int(obs.energy) - int(self.last_obs.energy)) <= self.energy_epsilon
        battery_stable = abs(float(obs.battery_pct) - float(self.last_obs.battery_pct)) < 1.0
        present_stable = bool(obs.target_present) == bool(self.last_obs.target_present)
        return angle_stable and energy_stable and battery_stable and present_stable

    def _encode_key(self, obs: RadioObservation, timestamp: float) -> dict[str, Any]:
        seq = self._next_seq()
        writer = BitWriter()
        writer.put(self.FRAME_KEY, 2)
        writer.put(seq, 6)
        writer.put(int(obs.target_id), 8)
        writer.put(_clamp_int(round(obs.angle_deg), 0, 359), 9)
        writer.put(_clamp_int(obs.energy, 0, 65535), 16)
        writer.put(_clamp_int(round(obs.battery_pct), 0, 100), 7)
        writer.put(1 if obs.target_present else 0, 1)
        data = writer.to_bytes()

        self.last_obs = obs
        self.last_key_ts = float(timestamp)
        self.packets_since_key = 0

        return {
            "frame_type": "key",
            "seq": seq,
            "base_seq": seq,
            "bytes": data,
            "size_bytes": len(data),
        }

    def _encode_delta(self, obs: RadioObservation, timestamp: float) -> dict[str, Any] | None:
        if self.last_obs is None:
            return None
        if int(obs.target_id) != int(self.last_obs.target_id):
            return None

        prev = self.last_obs
        angle_delta = int(round((obs.angle_deg - prev.angle_deg + 180.0) % 360.0 - 180.0))
        energy_delta_q = int(round((int(obs.energy) - int(prev.energy)) / 256.0))
        battery_delta = int(round(float(obs.battery_pct) - float(prev.battery_pct)))
        present_delta = int(bool(obs.target_present) != bool(prev.target_present))

        # If delta does not fit compact format, force key frame.
        if angle_delta < -31 or angle_delta > 31:
            return None
        if energy_delta_q < -128 or energy_delta_q > 127:
            return None
        if battery_delta < -8 or battery_delta > 7:
            return None

        mask = 0
        if abs(angle_delta) >= 1:
            mask |= self.MASK_ANGLE
        if abs(int(obs.energy) - int(prev.energy)) >= self.energy_epsilon:
            mask |= self.MASK_ENERGY
        if abs(float(obs.battery_pct) - float(prev.battery_pct)) >= 1.0:
            mask |= self.MASK_BATTERY
        if present_delta:
            mask |= self.MASK_PRESENT

        if mask == 0:
            return None

        base_seq = self.last_seq if self.last_seq >= 0 else 0
        seq = self._next_seq()
        writer = BitWriter()
        writer.put(self.FRAME_DELTA, 2)
        writer.put(seq, 6)
        writer.put(base_seq, 6)
        writer.put(mask, 4)
        if mask & self.MASK_ANGLE:
            writer.put(_signed_to_bits(angle_delta, 6), 6)
        if mask & self.MASK_ENERGY:
            writer.put(_signed_to_bits(energy_delta_q, 8), 8)
        if mask & self.MASK_BATTERY:
            writer.put(_signed_to_bits(battery_delta, 4), 4)
        if mask & self.MASK_PRESENT:
            writer.put(1 if obs.target_present else 0, 1)
        data = writer.to_bytes()

        self.last_obs = obs
        self.packets_since_key += 1

        return {
            "frame_type": "delta",
            "seq": seq,
            "base_seq": (seq - 1) % 64,
            "mask": mask,
            "bytes": data,
            "size_bytes": len(data),
        }

    def encode(self, payload: dict[str, Any], *, timestamp: float, force_key: bool = False) -> dict[str, Any] | None:
        obs = RadioObservation.from_dict(payload)
        if force_key or self._needs_forced_key(timestamp):
            return self._encode_key(obs, timestamp)

        if self.should_skip(obs):
            return None

        delta = self._encode_delta(obs, timestamp)
        if delta is not None:
            return delta
        return self._encode_key(obs, timestamp)
