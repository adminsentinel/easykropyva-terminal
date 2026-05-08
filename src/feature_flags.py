from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


def _clamp_float(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(value)))


def _deep_merge_dict(dst: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _deep_merge_dict(dst[key], value)
        else:
            dst[key] = value
    return dst


class RadioMode(Enum):
    FULL = "full"
    DELTA = "delta"
    DELTA_KEY = "delta_key"
    DELTA_SKIP = "delta_skip"
    RELAY_BEACON = "relay_beacon"
    WEATHER_HEARTBEAT = "weather_heartbeat"
    WEATHER_SLEEP = "weather_sleep"
    ERROR = "error"


@dataclass
class DeltaCodecConfig:
    enabled: bool = False
    key_interval_packets: int = 24
    angle_epsilon_deg: float = 0.5
    energy_epsilon: int = 400
    force_key_seconds: float = 30.0

    def __post_init__(self) -> None:
        self.key_interval_packets = _clamp_int(self.key_interval_packets, 1, 255)
        self.angle_epsilon_deg = _clamp_float(self.angle_epsilon_deg, 0.0, 10.0)
        self.energy_epsilon = _clamp_int(self.energy_epsilon, 0, 100000)
        self.force_key_seconds = _clamp_float(self.force_key_seconds, 0.1, 600.0)


@dataclass
class RelayConfig:
    enabled: bool = False
    battery_threshold: float = 0.05
    battery_threshold_eps: float = 1e-4

    def __post_init__(self) -> None:
        self.battery_threshold = _clamp_float(self.battery_threshold, 0.001, 0.99)
        self.battery_threshold_eps = _clamp_float(self.battery_threshold_eps, 0.0, 0.05)

    def is_active(self, battery_pct: float) -> bool:
        return bool(self.enabled) and float(battery_pct) <= (
            float(self.battery_threshold) + float(self.battery_threshold_eps)
        )


@dataclass
class WeatherConfig:
    enabled: bool = False
    noise_threshold: float = 0.78
    check_interval_frames: int = 150
    min_awake_interval_frames: int = 24

    def __post_init__(self) -> None:
        self.noise_threshold = _clamp_float(self.noise_threshold, 0.0, 1.0)
        self.check_interval_frames = _clamp_int(self.check_interval_frames, 1, 5000)
        self.min_awake_interval_frames = _clamp_int(self.min_awake_interval_frames, 1, 1000)

    def is_sleep(self, weather_idx: float, frame_idx: int) -> bool:
        return bool(self.enabled) and float(weather_idx) >= float(self.noise_threshold) and (
            int(frame_idx) % int(self.min_awake_interval_frames) != 0
        )


@dataclass
class AcousticConfig:
    shadow_mask_enabled: bool = False
    shadow_mask_radius_deg: int = 5
    shadow_mask_floor_ratio: float = 0.35

    def __post_init__(self) -> None:
        self.shadow_mask_radius_deg = _clamp_int(self.shadow_mask_radius_deg, 1, 30)
        self.shadow_mask_floor_ratio = _clamp_float(self.shadow_mask_floor_ratio, 0.05, 0.95)


@dataclass
class BatterySimConfig:
    start_pct: float = 1.0
    capacity_mah: float = 2200.0
    sim_scale: float = 240.0

    def __post_init__(self) -> None:
        self.start_pct = _clamp_float(self.start_pct, 0.0, 1.0)
        self.capacity_mah = _clamp_float(self.capacity_mah, 50.0, 100000.0)
        self.sim_scale = _clamp_float(self.sim_scale, 1.0, 5000.0)


@dataclass
class LinkAdaptConfig:
    sf12_when_dense_noise: bool = True
    sf12_noise_threshold: float = 0.78

    def __post_init__(self) -> None:
        self.sf12_noise_threshold = _clamp_float(self.sf12_noise_threshold, 0.1, 1.0)

    def spreading_factor(self, weather_idx: float) -> int:
        if bool(self.sf12_when_dense_noise) and float(weather_idx) >= float(self.sf12_noise_threshold):
            return 12
        return 9


@dataclass
class FeatureFlags:
    delta_codec: DeltaCodecConfig = field(default_factory=DeltaCodecConfig)
    relay: RelayConfig = field(default_factory=RelayConfig)
    weather: WeatherConfig = field(default_factory=WeatherConfig)
    acoustic: AcousticConfig = field(default_factory=AcousticConfig)
    battery: BatterySimConfig = field(default_factory=BatterySimConfig)
    link: LinkAdaptConfig = field(default_factory=LinkAdaptConfig)

    @staticmethod
    def _group_payload(data: dict[str, Any], group: str) -> dict[str, Any]:
        payload = data.get(group, {})
        if isinstance(payload, dict):
            return dict(payload)
        return {}

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "FeatureFlags":
        data = dict(payload or {})
        delta = cls._group_payload(data, "delta_codec")
        relay = cls._group_payload(data, "relay")
        weather = cls._group_payload(data, "weather")
        acoustic = cls._group_payload(data, "acoustic")
        battery = cls._group_payload(data, "battery")
        link = cls._group_payload(data, "link")

        # Backward compatibility for previous flat schema.
        delta.setdefault("enabled", bool(data.get("hybrid_lora_delta_codec", delta.get("enabled", False))))
        delta.setdefault("key_interval_packets", data.get("delta_key_interval_packets", delta.get("key_interval_packets", 24)))
        delta.setdefault("angle_epsilon_deg", data.get("delta_angle_epsilon_deg", delta.get("angle_epsilon_deg", 0.5)))
        delta.setdefault("energy_epsilon", data.get("delta_energy_epsilon", delta.get("energy_epsilon", 400)))
        delta.setdefault("force_key_seconds", data.get("delta_force_key_seconds", delta.get("force_key_seconds", 30.0)))

        relay.setdefault("enabled", bool(data.get("beacon_relay_low_battery", relay.get("enabled", False))))
        relay.setdefault("battery_threshold", data.get("relay_battery_threshold", relay.get("battery_threshold", 0.05)))
        relay.setdefault(
            "battery_threshold_eps",
            data.get("battery_threshold_eps", relay.get("battery_threshold_eps", 1e-4)),
        )

        weather.setdefault("enabled", bool(data.get("weather_adaptive_scan", weather.get("enabled", False))))
        weather.setdefault("noise_threshold", data.get("weather_noise_threshold", weather.get("noise_threshold", 0.78)))
        weather.setdefault(
            "check_interval_frames",
            data.get("weather_check_interval_frames", weather.get("check_interval_frames", 150)),
        )
        weather.setdefault(
            "min_awake_interval_frames",
            data.get("weather_min_awake_interval_frames", weather.get("min_awake_interval_frames", 24)),
        )

        acoustic.setdefault("shadow_mask_enabled", bool(data.get("acoustic_shadow_mask", acoustic.get("shadow_mask_enabled", False))))
        acoustic.setdefault("shadow_mask_radius_deg", data.get("shadow_mask_radius_deg", acoustic.get("shadow_mask_radius_deg", 5)))
        acoustic.setdefault(
            "shadow_mask_floor_ratio",
            data.get("shadow_mask_floor_ratio", acoustic.get("shadow_mask_floor_ratio", 0.35)),
        )

        battery.setdefault("start_pct", data.get("battery_start_pct", battery.get("start_pct", 1.0)))
        battery.setdefault("capacity_mah", data.get("battery_capacity_mah", battery.get("capacity_mah", 2200.0)))
        battery.setdefault("sim_scale", data.get("battery_sim_scale", battery.get("sim_scale", 240.0)))

        link.setdefault("sf12_when_dense_noise", bool(data.get("sf12_when_dense_noise", link.get("sf12_when_dense_noise", True))))
        link.setdefault("sf12_noise_threshold", data.get("sf12_noise_threshold", link.get("sf12_noise_threshold", 0.78)))

        return cls(
            delta_codec=DeltaCodecConfig(**delta),
            relay=RelayConfig(**relay),
            weather=WeatherConfig(**weather),
            acoustic=AcousticConfig(**acoustic),
            battery=BatterySimConfig(**battery),
            link=LinkAdaptConfig(**link),
        )

    def merge_overrides(self, overrides: dict[str, Any]) -> None:
        if not overrides:
            return
        merged = self.to_dict()
        _deep_merge_dict(merged, dict(overrides))
        normalized = FeatureFlags.from_dict(merged)
        self.__dict__.update(normalized.__dict__)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    # Legacy compatibility shims (read-only aliases).
    @property
    def hybrid_lora_delta_codec(self) -> bool:
        return bool(self.delta_codec.enabled)

    @property
    def beacon_relay_low_battery(self) -> bool:
        return bool(self.relay.enabled)

    @property
    def weather_adaptive_scan(self) -> bool:
        return bool(self.weather.enabled)

    @property
    def acoustic_shadow_mask(self) -> bool:
        return bool(self.acoustic.shadow_mask_enabled)

    @property
    def delta_key_interval_packets(self) -> int:
        return int(self.delta_codec.key_interval_packets)

    @property
    def delta_angle_epsilon_deg(self) -> float:
        return float(self.delta_codec.angle_epsilon_deg)

    @property
    def delta_energy_epsilon(self) -> int:
        return int(self.delta_codec.energy_epsilon)

    @property
    def delta_force_key_seconds(self) -> float:
        return float(self.delta_codec.force_key_seconds)

    @property
    def relay_battery_threshold(self) -> float:
        return float(self.relay.battery_threshold)

    @property
    def weather_noise_threshold(self) -> float:
        return float(self.weather.noise_threshold)

    @property
    def weather_check_interval_frames(self) -> int:
        return int(self.weather.check_interval_frames)

    @property
    def weather_min_awake_interval_frames(self) -> int:
        return int(self.weather.min_awake_interval_frames)

    @property
    def shadow_mask_radius_deg(self) -> int:
        return int(self.acoustic.shadow_mask_radius_deg)

    @property
    def shadow_mask_floor_ratio(self) -> float:
        return float(self.acoustic.shadow_mask_floor_ratio)

    @property
    def battery_start_pct(self) -> float:
        return float(self.battery.start_pct)

    @property
    def battery_capacity_mah(self) -> float:
        return float(self.battery.capacity_mah)

    @property
    def battery_sim_scale(self) -> float:
        return float(self.battery.sim_scale)

    @property
    def sf12_when_dense_noise(self) -> bool:
        return bool(self.link.sf12_when_dense_noise)

    @property
    def sf12_noise_threshold(self) -> float:
        return float(self.link.sf12_noise_threshold)
