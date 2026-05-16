"""
SENTINEL-QC WEB SERVER - Веб-сервер для управління системою
=============================================================
"""

from flask import Flask, render_template, jsonify, request, Response
import asyncio
import threading
import time
import sys
import os
from pathlib import Path
import requests
import math

app = Flask(__name__)

# EasyKropyva in-memory state
nodes = []
targets_store = []
node_id_counter = 0
target_id_counter = 0
home_point = None  # Домашня база: {"lat": ..., "lng": ..., "name": "HOME"}


@app.route('/')
def index():
    """Головна сторінка"""
    # Для Render: HTML в корені репозиторію поруч з app.py
    easyk_path = Path(__file__).parent / "easykropyva_terminal_v1_3.html"
    if easyk_path.exists():
        return Response(easyk_path.read_text(encoding="utf-8"), mimetype="text/html")
    return render_template('index.html')


@app.route('/api/nodes', methods=['GET', 'POST'])
def api_nodes():
    """EasyKropyva nodes API"""
    global nodes, node_id_counter
    if request.method == 'GET':
        return jsonify(nodes)

    payload = request.get_json(silent=True) or {}
    node_id_counter += 1
    item = {
        'id': node_id_counter,
        'name': payload.get('name', f'NODE-{node_id_counter:03d}'),
        'type': payload.get('type', 'sensor'),
        'lat': payload.get('lat'),
        'lng': payload.get('lng'),
        'altitude_m': payload.get('altitude_m', 2.0),
        'mesh_active': payload.get('mesh_active', True),
        'model': payload.get('model', '1'),
        'battery': payload.get('battery', 100),
    }
    nodes.append(item)
    return jsonify(item), 201


@app.route('/api/nodes/<int:node_id>', methods=['DELETE', 'PATCH'])
def api_node_detail(node_id: int):
    """Detail view for a node (Delete or Update)"""
    global nodes
    if request.method == 'DELETE':
        nodes = [n for n in nodes if n.get('id') != node_id]
        return jsonify({'ok': True})
    
    if request.method == 'PATCH':
        payload = request.get_json(silent=True) or {}
        for node in nodes:
            if node.get('id') == node_id:
                node.update({
                    'altitude_m': payload.get('altitude_m', node['altitude_m']),
                    'mesh_active': payload.get('mesh_active', node['mesh_active']),
                    'model': payload.get('model', node['model']),
                    'name': payload.get('name', node['name']),
                    'lat': payload.get('lat', node['lat']),
                    'lng': payload.get('lng', node['lng']),
                })
                return jsonify(node)
        return jsonify({'error': 'Not found'}), 404


@app.route('/api/targets', methods=['GET', 'POST'])
def api_targets():
    """EasyKropyva targets API з підтримкою висоти (ground/air)"""
    global targets_store, target_id_counter
    if request.method == 'GET':
        return jsonify(targets_store)

    payload = request.get_json(silent=True) or {}
    target_id_counter += 1
    item = {
        'id': target_id_counter,
        'name': payload.get('name', f'TGT-{target_id_counter:03d}'),
        'type': payload.get('type', 'FPV'),
        'altitude_type': payload.get('altitude_type', 'ground'),  # 'ground' або 'air'
        'altitude_m': payload.get('altitude_m', 0),  # висота в метрах
        'confidence': payload.get('confidence', 0.8),
        'lat': payload.get('lat'),
        'lng': payload.get('lng'),
    }
    targets_store.append(item)
    return jsonify(item), 201


@app.route('/api/targets/<int:target_id>', methods=['DELETE', 'PATCH'])
def api_target_detail(target_id: int):
    """Detail view for a target (Delete or Update)"""
    global targets_store
    if request.method == 'DELETE':
        targets_store = [t for t in targets_store if t.get('id') != target_id]
        return jsonify({'ok': True})
    
    if request.method == 'PATCH':
        payload = request.get_json(silent=True) or {}
        for target in targets_store:
            if target.get('id') == target_id:
                target.update({
                    'name': payload.get('name', target['name']),
                    'lat': payload.get('lat', target['lat']),
                    'lng': payload.get('lng', target['lng']),
                    'altitude_m': payload.get('altitude_m', target['altitude_m']),
                    'altitude_type': payload.get('altitude_type', target['altitude_type']),
                    'type': payload.get('type', target['type']),
                })
                return jsonify(target)
        return jsonify({'error': 'Not found'}), 404


@app.route('/api/clear', methods=['POST'])
def api_clear():
    """Clear all EasyKropyva entities"""
    global nodes, targets_store, node_id_counter, target_id_counter
    nodes = []
    targets_store = []
    node_id_counter = 0
    target_id_counter = 0
    return jsonify({'ok': True, 'cleared': True})


@app.route('/api/status')
def get_status():
    """Отримання статусу системи"""
    global coordinator
    if coordinator:
        return jsonify(coordinator.get_system_status())
    return jsonify({
        'node_id': 0,
        'role': 'SENSOR',
        'running': False,
        'frame_count': 0,
        'uptime': 0,
        'active_targets': 0,
        'active_agents': 0
    })


@app.route('/api/energy')
def get_energy_status():
    """Отримання статусу енергоспоживання"""
    global coordinator
    if coordinator:
        return jsonify(coordinator.get_energy_gov_status())
    return jsonify({
        'current_state': 'STANDBY',
        'consumption_ua': 10,
        'temperature': 25
    })


@app.route('/api/wavefield')
def get_wavefield():
    """Отримання енергетичної карти"""
    global coordinator
    if coordinator and 'wavefield' in coordinator.agents:
        wf = coordinator.agents['wavefield']
        return jsonify({
            'map': wf.get_energy_map(),
            'peak_angle': wf.get_peak_angle(),
        })
    return jsonify({'map': [], 'peak_angle': 0})


@app.route('/api/agents')
def get_agents():
    """Отримання списку агентів"""
    global coordinator
    if coordinator:
        agents_info = []
        for name, agent in coordinator.agents.items():
            agents_info.append({
                'name': name,
                'id': agent.agent_id,
                'state': agent.state.value if hasattr(agent.state, 'value') else 'idle',
                'connections': len(agent.connections),
                'skills': list(agent.skills.keys()) if hasattr(agent, 'skills') else []
            })
        return jsonify(agents_info)
    return jsonify([])


@app.route('/api/start', methods=['POST'])
def start_system():
    """Запуск системи"""
    global coordinator, coordinator_loop, coordinator_thread, running_event
    
    if coordinator is None or not getattr(coordinator, '_running', False):
        node_id = request.json.get('node_id', 42) if request.json else 42
        role = request.json.get('role', 'SENSOR') if request.json else 'SENSOR'
        
        async def init_and_run():
            global coordinator
            await coordinator.init_agents()
            await coordinator.run()
        
        async def run_loop():
            global running_event
            try:
                await coordinator.init_agents()
                await coordinator.run()
            except asyncio.CancelledError:
                pass
            finally:
                if running_event:
                    running_event.set()
        
        # Створення нового event loop в окремому потоці
        coordinator = SwarmCoordinator(node_id=node_id, role=role)
        coordinator_loop = asyncio.new_event_loop()
        running_event = asyncio.Event()
        coordinator_thread = threading.Thread(
            target=lambda: coordinator_loop.run_until_complete(run_loop()),
            daemon=True
        )
        coordinator_thread.start()

        # Чекаємо на ініціалізацію
        time.sleep(0.5)
        
        return jsonify({
            'status': 'started', 
            'node_id': coordinator.node_id,
            'role': coordinator.role
        })
    
    return jsonify({'status': 'already_running'})


@app.route('/api/stop', methods=['POST'])
def stop_system():
    """Зупинка системи"""
    global coordinator, coordinator_loop, running_event
    
    if coordinator:
        coordinator.stop()
        
        # Зупинка event loop
        if coordinator_loop:
            coordinator_loop.call_soon_threadsafe(lambda: running_event.set() if running_event else None)
        
        return jsonify({'status': 'stopped'})
    return jsonify({'status': 'not_running'})


@app.route('/api/simulate_target', methods=['POST'])
def simulate_target():
    """Симуляція цілі"""
    global coordinator
    
    target_data = request.json or {}
    angle = target_data.get('angle', 0)
    energy = target_data.get('energy', 50000)
    
    if coordinator and 'wavefield' in coordinator.agents:
        wavefield = coordinator.agents['wavefield']
        
        # Запуск у event loop
        if coordinator_loop:
            asyncio.run_coroutine_threadsafe(
                wavefield.inject_energy(angle, energy),
                coordinator_loop
            )
        
        return jsonify({
            'status': 'injected', 
            'angle': angle, 
            'energy': energy
        })
    
    return jsonify({'error': 'System not running'})


@app.route('/api/inject_multi', methods=['POST'])
def inject_multi_targets():
    """Ін'єкція кількох цілей"""
    global coordinator
    
    targets = request.json.get('targets', [])
    results = []
    
    if coordinator and 'wavefield' in coordinator.agents:
        wavefield = coordinator.agents['wavefield']
        
        for t in targets:
            angle = t.get('angle', 0)
            energy = t.get('energy', 50000)
            
            if coordinator_loop:
                asyncio.run_coroutine_threadsafe(
                    wavefield.inject_energy(angle, energy),
                    coordinator_loop
                )
            
            results.append({'angle': angle, 'energy': energy})
        
        return jsonify({'status': 'injected', 'count': len(results)})
    
    return jsonify({'error': 'System not running'})


def calculate_diffraction_loss(h, d1, d2, f_mhz):
    """
    Розрахунок втрат на дифракцію (Knife-edge diffraction) в dB.
    h: висота перешкоди над лінією прямої видимості (метрів)
    d1, d2: відстані від точок до перешкоди (метрів)
    f_mhz: частота в МГц
    """
    if h <= 0:
        return 0.0
    
    # Швидкість світла / частота = довжина хвилі
    wavelength = 300.0 / f_mhz
    
    # Параметр Френеля-Кірхгофа (v)
    v = h * math.sqrt((2 * (d1 + d2)) / (wavelength * d1 * d2))
    
    # Наближена формула для втрат (dB)
    if v <= -1:
        loss = 0.0
    elif v <= 0:
        loss = 20 * math.log10(0.5 - 0.62 * v)
    elif v <= 1:
        loss = 20 * math.log10(0.5 * math.exp(-0.95 * v))
    elif v <= 2.4:
        # Уникаємо від'ємного підкореневого виразу
        inner = 0.1184 - (0.38 - 0.1 * v)**2
        val = 0.4 - math.sqrt(max(0, inner))
        loss = 20 * math.log10(max(0.001, val))
    else:
        loss = 20 * math.log10(0.225 / v)
        
    return abs(loss)


def haversine_distance(lat1, lng1, lat2, lng2):
    """Розрахунок відстані між двома точками в метрах (Haversine)"""
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c


def calculate_diffraction_loss(h, d1, d2, freq_mhz):
    """
    Knife-edge diffraction loss calculation.
    h: obstruction height above LOS line (m). Negative means clearance.
    d1, d2: distance from start/end to obstruction (m).
    freq_mhz: frequency (MHz).
    """
    if h <= 0:
        return 0.0
        
    wavelength = 300.0 / freq_mhz
    # Nu (v) parameter
    v = h * math.sqrt(2.0 * (d1 + d2) / (wavelength * d1 * d2))
    
    # Approximation of Lee's diffraction loss model
    if v > -0.7:
        loss = 6.9 + 20.0 * math.log10(math.sqrt((v - 0.1)**2 + 1) + v - 0.1)
    else:
        loss = 0.0
        
    return round(max(0, loss), 1)


def calculate_earth_curvature(dist_km):
    """
    Calculates the earth's curvature drop (m) for a given distance.
    Uses standard K-factor of 4/3 for refraction.
    """
    # h = d^2 / (2 * K * R) -> d^2 / 12.74 for K=4/3, R=6371km
    return (dist_km**2) / 12.74


def sample_line(p1_lat, p1_lng, p2_lat, p2_lng, samples=30):
    """Генерація проміжних точок між двома координатами"""
    coords = []
    for i in range(samples + 1):
        f = i / samples
        lat = p1_lat + (p2_lat - p1_lat) * f
        lng = p1_lng + (p2_lng - p1_lng) * f
        coords.append((lat, lng))
    return coords


def compute_los(elevations, base_height_a=2.0, base_height_b=2.0, freq_mhz=433.0, distance_m=0.0):
    """
    Розрахунок прямої видимості (Line of Sight) з урахуванням зони Френеля.
    
    base_height_a/b — стандартна висота антени/датчика над рельєфом (м).
    Повертає dict з результатами аналізу (українською мовою).
    """
    if len(elevations) < 2:
        return {'пряма_видимість': False, 'помилка': 'Недостатньо даних про рельєф'}

    n = len(elevations)
    elev_a = elevations[0] + base_height_a
    elev_b = elevations[-1] + base_height_b

    los_clear = True
    max_obstruction = 0.0
    obstruction_idx = -1

    # Додаємо кривизну Землі (опціонально, але для LOS аналізу корисно)
    # h_drop = d^2 / 12.74 (спрощена формула для стандартної рефракції)
    # Тут d в км
    distance_km = distance_m / 1000.0
    
    for i in range(n):
        f = i / (n - 1)
        dist_from_start_km = f * distance_km
        # Висота "просідання" горизонту через кривизну
        earth_drop = (dist_from_start_km * (distance_km - dist_from_start_km)) / 12.74
        elevations[i] += earth_drop

    for i in range(1, n - 1):
        f = i / (n - 1)
        line_height = elev_a + f * (elev_b - elev_a)
        terrain = elevations[i]

        # Розрахунок зони Френеля для цієї точки
        clearance_required = 0.0
        if distance_m > 0 and freq_mhz > 0:
            d1_km = (f * distance_m) / 1000.0
            d2_km = ((1 - f) * distance_m) / 1000.0
            f_ghz = freq_mhz / 1000.0
            # Радіо-горизонт (км) = 4.12 * (sqrt(h1) + sqrt(h2))
            radio_horizon_km = 4.12 * (math.sqrt(base_height_a) + math.sqrt(base_height_b))
            distance_km = distance_m / 1000.0
            
            fresnel_radius = 17.32 * math.sqrt((d1_km * d2_km) / (f_ghz * distance_km))
            clearance_required = 0.6 * fresnel_radius  # Потрібно 60% чистої зони

        if terrain > (line_height - clearance_required):
            los_clear = False
            diff = terrain - (line_height - clearance_required)
            if diff > max_obstruction:
                max_obstruction = diff
                obstruction_idx = i

    # Розрахунок бюджету лінку (RSSI)
    # FSPL = 20log10(d_km) + 20log10(f_mhz) + 32.44
    if distance_m > 0:
        d_km = max(0.01, distance_m / 1000.0)
        fspl = 20 * math.log10(d_km) + 20 * math.log10(freq_mhz) + 32.44
    else:
        fspl = 0
        
    diffraction_loss = 0.0
    if not los_clear and obstruction_idx > 0:
        f = obstruction_idx / (n - 1)
        d1 = f * distance_m
        d2 = (1 - f) * distance_m
        # h - висота перешкоди над лінією LOS
        line_at_obs = elev_a + f * (elev_b - elev_a)
        h_obs = elevations[obstruction_idx] - line_at_obs
        diffraction_loss = calculate_diffraction_loss(h_obs, d1, d2, freq_mhz)

    total_path_loss = fspl + diffraction_loss

    # Створення профілів для графіку
    terrain_profile = [round(e, 1) for e in elevations]
    los_beam = []
    fresnel_60 = []

    for i in range(n):
        f = i / (n - 1)
        line_height = elev_a + f * (elev_b - elev_a)
        los_beam.append(round(line_height, 1))

        clearance_required = 0.0
        if distance_m > 0 and freq_mhz > 0:
            d1_km = (f * distance_m) / 1000.0
            d2_km = ((1 - f) * distance_m) / 1000.0
            f_ghz = freq_mhz / 1000.0
            fresnel_radius = 17.32 * math.sqrt((d1_km * d2_km) / (f_ghz * distance_km))
            clearance_required = 0.6 * fresnel_radius
        fresnel_60.append(round(line_height - clearance_required, 1))

    radio_horizon_km = 4.12 * (math.sqrt(base_height_a) + math.sqrt(base_height_b))
    is_beyond_horizon = (distance_m / 1000.0) > radio_horizon_km

    return {
        'пряма_видимість': los_clear and not is_beyond_horizon,
        'terrain_los': los_clear,
        'beyond_horizon': is_beyond_horizon,
        'radio_horizon_km': round(radio_horizon_km, 2),
        'статус': 'ВИДИМІСТЬ Є' if (los_clear and not is_beyond_horizon) else ('ЗА ГОРИЗОНТОМ' if is_beyond_horizon else f"ЗАБЛОКОВАНО (-{round(max_obstruction, 1)}м)"),
        'висота_початку_рельєф': round(elevations[0], 1),
        'висота_кінця_рельєф': round(elevations[-1], 1),
        'path_loss_db': round(total_path_loss, 1),
        'fspl_db': round(fspl, 1),
        'diffraction_loss_db': round(diffraction_loss, 1),
        'terrain_profile': terrain_profile,
        'los_beam': los_beam,
        'fresnel_60': fresnel_60,
        'необхідний_підйом_м': round(max_obstruction, 1) if not los_clear else 0.0,
        'відстань_м': round(distance_m, 1)
    }
    }


def generate_synthetic_elevation(lat1, lng1, lat2, lng2, samples=30):
    """Генерує синтетичні дані рельєфу на основі координат (як fallback)."""
    import random
    random.seed(int(abs(lat1 * 1000) + abs(lng1 * 1000)))
    
    # Базова висота залежить від широти (імітація гір на північних широтах)
    base_elev = 200 + (lat1 - 48) * 50  # ~200-400м для України
    
    elevations = []
    for i in range(samples + 1):
        f = i / samples
        # Лінійна інтерполяція + шум + "горби"
        noise = random.gauss(0, 15)
        hill = 30 * (1 - abs(f - 0.5) * 2) if f > 0.3 and f < 0.7 else 0  # Горб посередині
        elevations.append(round(base_elev + noise + hill, 1))
    
    return elevations


@app.route('/api/los', methods=['POST'])
def api_los():
    """
    POST /api/los
    Body: {"lat1": 49.84, "lng1": 24.03, "lat2": 49.85, "lng2": 24.04,
           "base_height_a": 2.0, "base_height_b": 2.0, "samples": 30}
    Повертає результат аналізу прямої видимості (українською мовою).
    При недоступності open-elevation використовує синтетичні дані.
    """
    payload = request.get_json(silent=True) or {}
    lat1 = payload.get('lat1')
    lng1 = payload.get('lng1')
    lat2 = payload.get('lat2')
    lng2 = payload.get('lng2')

    if lat1 is None or lng1 is None or lat2 is None or lng2 is None:
        return jsonify({'помилка': 'Відсутні координати (lat1, lng1, lat2, lng2)'}), 400

    base_h_a = payload.get('base_height_a', 2.0)
    base_h_b = payload.get('base_height_b', 2.0)
    samples = payload.get('samples', 30)
    freq_mhz = payload.get('freq_mhz', 433.0)

    # Підтримка повітряних цілей
    target_type = payload.get('target_type', 'ground')  # 'ground' або 'air'
    target_altitude_m = payload.get('target_altitude_m', 0.0)

    elevations = None
    using_fallback = False

    # Спроба отримати реальні дані рельєфу
    try:
        coords = sample_line(lat1, lng1, lat2, lng2, samples=samples)
        loc_str = '|'.join(f'{lat},{lng}' for lat, lng in coords)

        resp = requests.get(
            f'https://api.open-elevation.com/api/v1/lookup?locations={loc_str}',
            timeout=2
        )
        if resp.status_code == 200:
            data = resp.json()
            elevations = [r['elevation'] for r in data.get('results', [])]
            if len(elevations) != len(coords):
                elevations = None
    except Exception as e:
        print(f"[LOS] Open-elevation failed: {e}, using fallback")

    # Fallback на синтетичні дані
    if elevations is None:
        elevations = generate_synthetic_elevation(lat1, lng1, lat2, lng2, samples)
        using_fallback = True

    try:
        distance_m = haversine_distance(lat1, lng1, lat2, lng2)
        result = compute_los(elevations, base_height_a=base_h_a, base_height_b=base_h_b, freq_mhz=freq_mhz, distance_m=distance_m)
        result['відстань_м'] = round(distance_m, 1)
        result['відстань_км'] = round(result['відстань_м'] / 1000, 2)
        result['синтетичні_дані'] = using_fallback
        result['target_type'] = target_type
        result['target_altitude_m'] = target_altitude_m
        result['efektivna_visota_b'] = round(base_h_b, 1)  # Ефективна висота точки B
        return jsonify(result)
    except Exception as e:
        return jsonify({'помилка': f'Помилка розрахунку LOS: {str(e)}'}), 500


@app.route('/api/mesh_topology', methods=['GET'])
def api_mesh_topology():
    """Розрахунок топології меш-мережі з урахуванням реального LOS."""
    global nodes
    
    mesh_nodes = [n for n in nodes if n.get('mesh_active', False)]
    if len(mesh_nodes) < 2:
        return jsonify({'links': [], 'masters': []})
        
    pairs = []
    coords_list = []
    samples = 15
    
    # 1. Збираємо всі пари
    for i in range(len(mesh_nodes)):
        for j in range(i + 1, len(mesh_nodes)):
            n1 = mesh_nodes[i]
            n2 = mesh_nodes[j]
            dist = haversine_distance(n1['lat'], n1['lng'], n2['lat'], n2['lng'])
            if dist > 15000:
                continue
                
            line_coords = sample_line(n1['lat'], n1['lng'], n2['lat'], n2['lng'], samples=samples)
            pairs.append({
                'n1': n1, 'n2': n2, 'dist': dist, 
                'start_idx': len(coords_list),
                'count': len(line_coords)
            })
            coords_list.extend(line_coords)
            
    if not pairs:
        return jsonify({'links': [], 'masters': []})
        
    # 2. Отримуємо висоти пакетом
    elevations = []
    try:
        if len(coords_list) > 0:
            # Обмежуємо до 500 точок для API, якщо більше - синтетика (щоб не покласти)
            if len(coords_list) < 500:
                loc_str = '|'.join(f'{lat},{lng}' for lat, lng in coords_list)
                resp = requests.get(f'https://api.open-elevation.com/api/v1/lookup?locations={loc_str}', timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    elevations = [r['elevation'] for r in data.get('results', [])]
    except Exception as e:
        print(f"[MESH] Bulk elevation failed: {e}")
        
    if len(elevations) != len(coords_list):
        # Fallback
        elevations = []
        for p in pairs:
            n1 = p['n1']
            n2 = p['n2']
            synth = generate_synthetic_elevation(n1['lat'], n1['lng'], n2['lat'], n2['lng'], samples)
            elevations.extend(synth)
            
    # 3. Аналізуємо LOS для кожної пари
    links = []
    connections = {n['id']: 0 for n in mesh_nodes}
    
    for p in pairs:
        elev_slice = elevations[p['start_idx'] : p['start_idx'] + p['count']]
        h_a = p['n1'].get('altitude_m', 2.0)
        h_b = p['n2'].get('altitude_m', 2.0)
        
        # Визначаємо частоту: 1 Micro=433, 3 Micro=433, Relay=900 (наприклад)
        freq = 900.0 if p['n1'].get('model') == 'relay' or p['n2'].get('model') == 'relay' else 433.0
        
        los_res = compute_los(elev_slice, base_height_a=h_a, base_height_b=h_b, freq_mhz=freq, distance_m=p['dist'])
        
        links.append({
            'source': p['n1']['id'],
            'target': p['n2']['id'],
            'distance_m': round(p['dist'], 1),
            'has_los': los_res['пряма_видимість'],
            'terrain_los': los_res['terrain_los'],
            'beyond_horizon': los_res['beyond_horizon'],
            'fresnel_m': los_res.get('макс_зона_френеля_м', 0)
        })
        
        if los_res['пряма_видимість']:
            connections[p['n1']['id']] += 1
            connections[p['n2']['id']] += 1
            
    # 4. Визначаємо майстер-ноди (Masters)
    masters = []
    total_other = len(mesh_nodes) - 1
    if total_other > 0:
        for n in mesh_nodes:
            conn_ratio = connections[n['id']] / total_other
            # Реле отримують бонус 20%
            if n.get('model') == 'relay':
                conn_ratio += 0.2
                
            if conn_ratio >= 0.8:
                masters.append(n['id'])
                
    return jsonify({'links': links, 'masters': masters})

# ---- HOME POINT API ----

@app.route('/api/home', methods=['GET', 'POST', 'DELETE'])
def api_home():
    """
    GET    - отримати координати домашньої бази
    POST   - встановити/оновити домашню базу {"lat": 49.84, "lng": 24.03, "name": "BASE-01"}
    DELETE - видалити домашню базу
    """
    global home_point
    
    if request.method == 'GET':
        if home_point:
            return jsonify(home_point)
        return jsonify({'повідомлення': 'Домашня база не встановлена'}), 404
    
    elif request.method == 'POST':
        payload = request.get_json(silent=True) or {}
        lat = payload.get('lat')
        lng = payload.get('lng')
        name = payload.get('name', 'HOME')
        
        if lat is None or lng is None:
            return jsonify({'помилка': 'Відсутні координати (lat, lng)'}), 400
        
        home_point = {
            'lat': lat,
            'lng': lng,
            'name': name,
            'встановлено': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        return jsonify({'ок': True, 'домашня_база': home_point}), 201
    
    elif request.method == 'DELETE':
        home_point = None
        return jsonify({'ок': True, 'повідомлення': 'Домашня база видалена'})


@app.route('/api/home/los', methods=['POST'])
def api_home_los():
    """
    POST /api/home/los
    Body: {"lat": 49.85, "lng": 24.04, "base_height_home": 2.0, "base_height_remote": 2.0}
    Перевіряє прямую видимість від домашньої бази до вказаної точки.
    """
    global home_point
    
    if home_point is None:
        return jsonify({'помилка': 'Домашня база не встановлена. Спочатку POST /api/home'}), 400
    
    payload = request.get_json(silent=True) or {}
    lat = payload.get('lat')
    lng = payload.get('lng')
    
    if lat is None or lng is None:
        return jsonify({'помилка': 'Відсутні координати цілі (lat, lng)'}), 400
    
    # Використовуємо той самий алгоритм LOS
    base_h_home = payload.get('base_height_home', 2.0)
    base_h_remote = payload.get('base_height_remote', 2.0)
    samples = payload.get('samples', 30)
    
    try:
        coords = sample_line(home_point['lat'], home_point['lng'], lat, lng, samples=samples)
        loc_str = '|'.join(f'{lat},{lng}' for lat, lng in coords)
        
        resp = requests.get(
            f'https://api.open-elevation.com/api/v1/lookup?locations={loc_str}',
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        elevations = [r['elevation'] for r in data.get('results', [])]
        
        if len(elevations) != len(coords):
            return jsonify({'помилка': 'API рельєфу повернуло неповні дані'}), 502
        
        result = compute_los(elevations, base_height_a=base_h_home, base_height_b=base_h_remote)
        result['відстань_м'] = round(haversine_distance(home_point['lat'], home_point['lng'], lat, lng), 1)
        result['відстань_км'] = round(result['відстань_м'] / 1000, 2)
        result['домашня_база'] = home_point['name']
        result['координати_цілі'] = {'lat': lat, 'lng': lng}
        return jsonify(result)
        
    except requests.exceptions.RequestException as e:
        return jsonify({'помилка': f'Помилка API рельєфу: {str(e)}'}), 502
    except Exception as e:
        return jsonify({'помилка': f'Помилка розрахунку LOS: {str(e)}'}), 500


if __name__ == '__main__':
    print("\n" + "=" * 50)
    print("SENTINEL-QC WEB SERVER")
    print("Open: http://localhost:5000")
    print("=" * 50 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)