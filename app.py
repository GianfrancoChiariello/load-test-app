from flask import Flask, render_template, request, jsonify
import requests
import concurrent.futures
import time
import psutil
import threading
from datetime import datetime
import json
import os

app = Flask(__name__)

# Variables globales para el estado del testtt
test_running = False
test_results = {}
test_thread = None

@app.route('/')
def index():
    """Página principal con interfaz de prueba de carga"""
    return render_template('index.html')

@app.route('/api/system-info')
def system_info():
    """Información del sistema en tiempo real"""
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    return jsonify({
        'cpu_percent': cpu_percent,
        'memory_percent': memory.percent,
        'memory_used_gb': round(memory.used / (1024**3), 2),
        'memory_total_gb': round(memory.total / (1024**3), 2),
        'disk_percent': disk.percent,
        'disk_used_gb': round(disk.used / (1024**3), 2),
        'disk_total_gb': round(disk.total / (1024**3), 2),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/load-test', methods=['POST'])
def start_load_test():
    """Iniciar prueba de carga"""
    global test_running, test_thread
    
    if test_running:
        return jsonify({'error': 'Test already running'}), 400
    
    data = request.get_json()
    target_url = data.get('url', 'http://httpbin.org/delay/1')
    num_requests = int(data.get('requests', 100))
    concurrency = int(data.get('concurrency', 10))
    
    test_running = True
    test_thread = threading.Thread(
        target=run_load_test, 
        args=(target_url, num_requests, concurrency)
    )
    test_thread.start()
    
    return jsonify({'message': 'Load test started', 'status': 'running'})

@app.route('/api/load-test', methods=['GET'])
def get_test_status():
    """Obtener estado del test de carga"""
    global test_results, test_running
    
    return jsonify({
        'running': test_running,
        'results': test_results
    })

def run_load_test(url, num_requests, concurrency):
    """Ejecutar la prueba de carga"""
    global test_running, test_results

    print(f"[{datetime.now().isoformat()}] Iniciando test de carga: {num_requests} requests a {url} con concurrencia {concurrency}")

    test_results = {
        'url': url,
        'num_requests': num_requests,
        'concurrency': concurrency,
        'start_time': datetime.now().isoformat(),
        'completed_requests': 0,
        'successful_requests': 0,
        'failed_requests': 0,
        'response_times': [],
        'errors': []
    }

    def make_request(session, request_id):
        try:
            start_time = time.time()
            response = session.get(url, timeout=30)
            end_time = time.time()

            response_time = (end_time - start_time) * 1000  # en ms

            test_results['completed_requests'] += 1
            test_results['response_times'].append(response_time)

            # Log de progreso por cada request
            print(f"[{datetime.now().isoformat()}] Request {request_id+1}/{num_requests} - Status: {response.status_code} - Tiempo: {round(response_time,2)} ms")

            if response.status_code == 200:
                test_results['successful_requests'] += 1
            else:
                test_results['failed_requests'] += 1
                test_results['errors'].append(f"Request {request_id}: HTTP {response.status_code}")

            return response_time, response.status_code

        except Exception as e:
            test_results['completed_requests'] += 1
            test_results['failed_requests'] += 1
            test_results['errors'].append(f"Request {request_id}: {str(e)}")
            print(f"[{datetime.now().isoformat()}] Request {request_id+1}/{num_requests} - ERROR: {str(e)}")
            return None, 'ERROR'

    # Ejecutar requests con ThreadPoolExecutor
    with requests.Session() as session:
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            start_time = time.time()

            # Enviar todas las requests
            futures = [executor.submit(make_request, session, i) for i in range(num_requests)]

            # Esperar a que terminen todas
            concurrent.futures.wait(futures)

            end_time = time.time()

    # Calcular estadísticas finales
    total_time = end_time - start_time
    response_times = [rt for rt in test_results['response_times'] if rt is not None]

    if response_times:
        test_results['stats'] = {
            'total_time_seconds': round(total_time, 2),
            'requests_per_second': round(num_requests / total_time, 2),
            'avg_response_time_ms': round(sum(response_times) / len(response_times), 2),
            'min_response_time_ms': round(min(response_times), 2),
            'max_response_time_ms': round(max(response_times), 2),
            'success_rate_percent': round((test_results['successful_requests'] / num_requests) * 100, 2)
        }

    test_results['end_time'] = datetime.now().isoformat()
    test_running = False

    # Log final de resultados
    print(f"[{datetime.now().isoformat()}] Test finalizado. Exitosos: {test_results['successful_requests']}, Fallidos: {test_results['failed_requests']}")
    if 'stats' in test_results:
        print(f"Estadísticas: {json.dumps(test_results['stats'], indent=2)}")
    if test_results['errors']:
        print(f"Errores: {test_results['errors']}")

    # Guardar logs
    save_test_log(test_results)

def save_test_log(results):
    """Guardar resultados en archivo log"""
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"logs/load_test_{timestamp}.json"
    
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)

@app.route('/api/test-local')
def test_local_services():
    """Probar servicios locales del homelab"""
    services = {
        'heimdall': 'http://192.168.1.35:8080',
        'portainer': 'http://192.168.1.35:9000',
        'minio_console': 'http://192.168.1.35:9001',
    }
    
    results = {}
    
    for service_name, url in services.items():
        try:
            start_time = time.time()
            response = requests.get(url, timeout=5)
            end_time = time.time()
            
            results[service_name] = {
                'url': url,
                'status_code': response.status_code,
                'response_time_ms': round((end_time - start_time) * 1000, 2),
                'status': 'OK' if response.status_code == 200 else 'ERROR'
            }
        except Exception as e:
            results[service_name] = {
                'url': url,
                'status_code': 'N/A',
                'response_time_ms': 'N/A',
                'status': 'ERROR',
                'error': str(e)
            }
    
    return jsonify(results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)