"""
SENTINEL-QC ECHELON AGENTS - Конфігурація системи
===================================================
"""

# === АПАРАТНА КОНФІГУРАЦІЯ ===
class HardwareConfig:
    # RP2350 (ARM Cortex-M33)
    CPU_FREQUENCY_HZ = 150_000_000
    CORE_COUNT = 2
    
    # Мікрофонна матриця (рівносторонній трикутник 120мм)
    MIC_CONFIG = {
        'count': 3,
        'spacing_mm': 120,
        'sample_rate': 16000,
        'block_size': 512,  # ~32ms
        'positions': [
            {'id': 'A', 'x': 0, 'y': 0},
            {'id': 'B', 'x': 120, 'y': 0},
            {'id': 'C', 'x': 60, 'y': 103.9}
        ]
    }
    
    # Розрахунок максимальної затримки
    # MaxDelay = 0.12 / 343 * 16000 ≈ 5.6 семплів
    SOUND_SPEED_MPS = 343
    MAX_DELAY_SAMPLES = 6
    
    # LoRa SX1262
    LORA_CONFIG = {
        'frequency_mhz': 433.05,
        'spreading_factor': 9,
        'bandwidth_hz': 125_000,
        'coding_rate': 4/5,
        'tx_power_dbm': 14,
        'channel_count': 64
    }


# === DSP КОНФІГУРАЦІЯ ===
class DSPConfig:
    BLOCK_SIZE = 512
    SAMPLE_RATE = 16000
    
    # IIR High-Pass фільтр (300 Гц)
    HP_ALPHA_Q15 = 30768  # ≈ 0.939
    HP_BETA_Q15 = 31752   # ≈ 0.969
    
    # Beamforming
    BEAM_ANGLES = 32  # 11.25° крок
    COARSE_STEP = 4
    FINE_RANGE = 2
    
    # VAD
    VAD_ALPHA = 1.0 / 1024
    VAD_THRESHOLD_MULT = 1.25
    VAD_MIN_FLOOR = 3000
    
    # Класифікація
    WIND_LOW_FRAC = 180 / 256
    WIND_MOD_THRESH = 8
    DRONE_HIGH_FRAC = 80 / 256
    DRONE_MOD_THRESH = 8


# === EKF КОНФІГУРАЦІЯ ===
class EKFConfig:
    # Q16 арифметика: 1.0 = 65536
    
    # Процесний шум Q (мм, мм/с)
    Q_POSITION = 500
    Q_VELOCITY = 50
    
    # Вимірювальний шум R (градуси)
    R_ANGLE_Q16 = int(5 * 65536 / 180)  # 5°
    
    # Joseph Form стабілізатор
    JOSEPH_DAMPING = 0.1
    
    # Information Filter coupling
    IF_CLOSE_WEIGHT = 1.0 / 8
    IF_FAR_WEIGHT = 1.0 / 32
    IF_CONSISTENCY_THRESH = 65536  # ~10°


# === SWARM КОНФІГУРАЦІЯ ===
class SwarmConfig:
    # WaveField
    FIELD_SIZE = 360  # 1° на комірку
    DECAY_Q16 = int(0.95 * 65536)
    DIFFUSE_WEIGHT = 0.25
    
    # Attention boost/suppress
    ATTENTION_BOOST = int(0.5 * 65536)
    ATTENTION_SUPPRESS = int(-0.25 * 65536)
    ATTENTION_RANGE_DEG = 30
    
    # Kuramoto
    KURAMOTO_COUPLING = 0.05
    KURAMOTO_GATE_RAD = 90  # ігноруємо > 90°
    
    # Consensus
    CONSENSUS_GATE_Q16 = int(30 * 65536 / 180)
    CONSENSUS_WEIGHT = 0.1
    
    # Memory
    MEMORY_SLOTS = 8
    MEMORY_DECAY = 0.99


# === ЕНЕРГЕТИЧНА КОНФІГУРАЦІЯ ===
class EnergyConfig:
    STATES = {
        'HIBERNATE': {'current_ua': 10, 'threshold_s': 600},   # 10 мкА
        'SLEEP': {'current_ua': 50},                           # 50 мкА
        'DSP_VERIFY': {'current_ma': 15, 'duration_ms': 2000},
        'FULL_ALERT': {'current_ma': 80}
    }
    
    TRIGGER_THRESHOLD = 50000
    COOLING_DELTA = 10
    WARMING_DELTA = 5
    HYSTERESIS_MS = 3000


# === МЕРЕЖЕВА КОНФІГУРАЦІЯ ===
class NetworkConfig:
    MAX_NODES = 16
    SLOT_DURATION_MS = 200
    HEALTH_PULSE_INTERVAL_S = 3600  # 1 baseline pulse per hour
    
    # Gossip
    GOSSIP_TIMEOUT_S = 300
    DEDUP_CACHE_SIZE = 64
    
    # TDMA
    BEACON_INTERVAL_MS = 5000


# === НАЗВИ АГЕНТІВ ===
AGENT_NAMES = {
    'dsp': 'DAQA-Agent',
    'vad': 'VAD-Agent',
    'classifier': 'Classifier-Agent',
    'ekf_1d': 'EKF-1D-Agent',
    'ekf_2d': 'EKF-2D-Agent',
    'info_filter': 'InfoFilter-Agent',
    'wavefield': 'WaveField-Agent',
    'kuramoto': 'Kuramoto-Agent',
    'consensus': 'Consensus-Agent',
    'memory': 'Memory-Agent',
    'triangulation': 'Triangulation-Agent',
    'ransac': 'RANSAC-Agent',
    'lora': 'LoRa-Agent',
    'mesh': 'MeshRouter-Agent',
    'energy_gov': 'EnergyGov-Agent',
    'coordinator': 'SwarmCoordinator'
}
