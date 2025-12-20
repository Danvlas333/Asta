# flask_controller.py - Исправленная версия для Raspberry Pi с камерой
from flask import Flask, request, jsonify, Response
import serial
import time
import threading
import cv2
import numpy as np
from datetime import datetime
import os

app = Flask(__name__)

# Настройки для Arduino руки
HAND_SERIAL_PORT = '/dev/ttyUSB0'  
HAND_BAUD_RATE = 115200
hand_arduino = None

# Настройки для Arduino лица
FACE_SERIAL_PORT = '/dev/ttyUSB1'  # Второй Arduino
FACE_BAUD_RATE = 9600
face_arduino = None

# Настройки для камеры
CAMERA_INDEX = 0  # Индекс камеры (0 - встроенная камера на Raspberry Pi)
camera = None
camera_lock = threading.Lock()
camera_running = False
latest_frame = None

# Ограничения для лица
EYE_MIN = 70
EYE_MAX = 110
EYE_CENTER = 90
MOUTH_MIN = 0
MOUTH_MAX = 80

# Блокировка для потокобезопасности
serial_lock = threading.Lock()

def init_camera():
    """Инициализация камеры"""
    global camera, camera_running
    try:
        camera = cv2.VideoCapture(CAMERA_INDEX)
        # Настройки камеры для Raspberry Pi
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        camera.set(cv2.CAP_PROP_FPS, 30)
        
        # Проверяем, работает ли камера
        if camera.isOpened():
            ret, frame = camera.read()
            if ret:
                camera_running = True
                print(f"Камера подключена (индекс {CAMERA_INDEX})")
                return True
        print("Камера не инициализирована")
        return False
    except Exception as e:
        print(f"Ошибка инициализации камеры: {e}")
        return False

def camera_thread_func():
    """Функция потока для получения кадров с камеры"""
    global camera, camera_running, latest_frame
    
    while camera_running:
        try:
            with camera_lock:
                if camera and camera.isOpened():
                    ret, frame = camera.read()
                    if ret:
                        # Ресайзим для экономии пропускной способности
                        frame = cv2.resize(frame, (320, 240))
                        latest_frame = frame
                    else:
                        print("Не удалось получить кадр с камеры")
                else:
                    time.sleep(0.1)
                    continue
        except Exception as e:
            print(f"Ошибка в потоке камеры: {e}")
            time.sleep(0.1)
        
        time.sleep(0.03)  # ~30 FPS

def init_hand_arduino():
    """Инициализация Arduino для руки"""
    global hand_arduino
    try:
        # Закрываем соединение если оно уже открыто
        if hand_arduino and hand_arduino.is_open:
            hand_arduino.close()
        
        hand_arduino = serial.Serial(
            HAND_SERIAL_PORT, 
            HAND_BAUD_RATE, 
            timeout=1,
            write_timeout=1,
            bytesize=8,
            parity='N',
            stopbits=1
        )
        time.sleep(2)  # Даем время Arduino на инициализацию
        
        # Очищаем буфер
        hand_arduino.reset_input_buffer()
        hand_arduino.reset_output_buffer()
        
        # Тестовая команда для проверки связи
        test_command = "0,0,0,0,180,180,0\n"
        with serial_lock:
            hand_arduino.write(test_command.encode('utf-8'))
            hand_arduino.flush()
            time.sleep(0.1)
            
        print(f"Arduino Hand подключён на {HAND_SERIAL_PORT}")
        return True
    except Exception as e:
        hand_arduino = None
        print(f"Arduino Hand недоступен ({HAND_SERIAL_PORT}): {e}")
        return False

def init_face_arduino():
    """Инициализация Arduino для лица"""
    global face_arduino
    try:
        # Закрываем соединение если оно уже открыто
        if face_arduino and face_arduino.is_open:
            face_arduino.close()
        
        face_arduino = serial.Serial(
            FACE_SERIAL_PORT, 
            FACE_BAUD_RATE, 
            timeout=1,
            write_timeout=1,
            bytesize=8,
            parity='N',
            stopbits=1
        )
        time.sleep(2)  # Даем время Arduino на инициализацию
        
        # Очищаем буфер
        face_arduino.reset_input_buffer()
        face_arduino.reset_output_buffer()
        
        # Тестовая команда для проверки связи
        test_command = "E90 M0\n"
        with serial_lock:
            face_arduino.write(test_command.encode('utf-8'))
            face_arduino.flush()
            time.sleep(0.1)
            
        print(f"Arduino Face подключён на {FACE_SERIAL_PORT}")
        return True
    except Exception as e:
        face_arduino = None
        print(f"Arduino Face недоступен ({FACE_SERIAL_PORT}): {e}")
        return False

def send_to_hand_arduino(data_str):
    """Отправка данных на Arduino руки"""
    if hand_arduino is None or not hand_arduino.is_open:
        return False, "Arduino Hand не подключен"
    
    try:
        # Убеждаемся, что строка заканчивается новой строкой
        if not data_str.endswith('\n'):
            data_str += '\n'
        
        with serial_lock:
            cmd_bytes = data_str.encode('utf-8')
            hand_arduino.write(cmd_bytes)
            hand_arduino.flush()
            time.sleep(0.05)
                
        return True, "Команда отправлена"
    except Exception as e:
        print(f"Ошибка отправки на Hand Arduino: {e}")
        return False, f"Ошибка отправки: {e}"

def send_to_face_arduino(data_str):
    """Отправка данных на Arduino лица"""
    if face_arduino is None or not face_arduino.is_open:
        return False, "Arduino Face не подключен"
    
    try:
        # Убеждаемся, что строка заканчивается новой строкой
        if not data_str.endswith('\n'):
            data_str += '\n'
        
        with serial_lock:
            cmd_bytes = data_str.encode('utf-8')
            face_arduino.write(cmd_bytes)
            face_arduino.flush()
            time.sleep(0.1)
            
        return True, "Команда отправлена"
    except Exception as e:
        print(f"Ошибка отправки на Face Arduino: {e}")
        return False, f"Ошибка отправки: {e}"

def add_cors_headers(response):
    """Добавляем CORS заголовки вручную"""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS, PUT, DELETE'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

@app.before_request
def before_request():
    """Проверка перед каждым запросом"""
    if request.method == 'OPTIONS':
        return add_cors_headers(make_response('', 200))

# Эндпоинты для руки
@app.route('/hand', methods=['POST', 'OPTIONS'])
def set_hand():
    """Управление рукой"""
    if request.method == 'OPTIONS':
        response = app.make_response('')
        return add_cors_headers(response)
        
    global hand_arduino
    
    # Проверяем подключение
    if hand_arduino is None or not hand_arduino.is_open:
        if not init_hand_arduino():
            response = jsonify({
                "status": "error", 
                "message": "Arduino Hand не подключен",
                "timestamp": time.time()
            })
            return add_cors_headers(response), 503

    try:
        data = request.json
        if not data:
            response = jsonify({
                "status": "error", 
                "message": "Нет данных в запросе"
            })
            return add_cors_headers(response), 400
            
        # Извлекаем углы с значениями по умолчанию
        wrist = int(data.get('wrist', 0))
        f1 = int(data.get('f1', 0))
        f2 = int(data.get('f2', 0))
        f3 = int(data.get('f3', 0))
        f4 = int(data.get('f4', 0))
        f5 = int(data.get('f5', 0))
        f6 = int(data.get('f6', 0))
        
        # Применяем ограничения
        wrist = max(0, min(90, wrist))   
        f1 = max(0, min(180, f1))
        f2 = max(0, min(180, f2))
        f3 = max(0, min(180, f3))
        f4 = max(0, min(180, f4))
        f5 = max(0, min(180, f5))
        f6 = max(0, min(180, f6))
        
        # Формируем команду для Arduino
        command = f"{wrist},{f1},{f2},{f3},{f4},{f5},{f6}"
        
        # Отправляем команду
        success, message = send_to_hand_arduino(command)
        
        response = jsonify({
            "status": "success" if success else "error", 
            "message": message,
            "angles": {
                "wrist": wrist,
                "f1": f1,
                "f2": f2, 
                "f3": f3,
                "f4": f4,
                "f5": f5,
                "f6": f6
            },
            "timestamp": time.time()
        })
        
        return add_cors_headers(response)

    except Exception as e:
        print(f"Ошибка обработки команды руки: {e}")
        response = jsonify({
            "status": "error", 
            "message": str(e),
            "timestamp": time.time()
        })
        return add_cors_headers(response), 400

# Эндпоинты для лица
@app.route('/face', methods=['POST', 'OPTIONS'])
def set_face():
    """Управление лицом"""
    if request.method == 'OPTIONS':
        response = app.make_response('')
        return add_cors_headers(response)
        
    global face_arduino
    
    # Проверяем подключение
    if face_arduino is None or not face_arduino.is_open:
        if not init_face_arduino():
            response = jsonify({
                "status": "error", 
                "message": "Arduino Face не подключен",
                "timestamp": time.time()
            })
            return add_cors_headers(response), 503

    try:
        data = request.json
        if not data:
            response = jsonify({
                "status": "error", 
                "message": "Нет данных в запросе"
            })
            return add_cors_headers(response), 400
            
        command = ""
        
        # Обработка глаз
        if 'eyes' in data:
            eyes = int(data['eyes'])
            eyes = max(EYE_MIN, min(eyes, EYE_MAX))
            command += f"E{eyes} "
        
        # Обработка рта
        if 'mouth' in data:
            mouth = int(data['mouth'])
            mouth = max(MOUTH_MIN, min(mouth, MOUTH_MAX))
            command += f"M{mouth}"
        
        if command:
            success, message = send_to_face_arduino(command.strip())
            
            response = jsonify({
                "status": "success" if success else "error", 
                "message": message,
                "timestamp": time.time()
            })
            
            return add_cors_headers(response)
        else:
            response = jsonify({
                "status": "error", 
                "message": "Нет корректных команд для лица",
                "timestamp": time.time()
            })
            return add_cors_headers(response), 400

    except Exception as e:
        print(f"Ошибка обработки команды лица: {e}")
        response = jsonify({
            "status": "error", 
            "message": str(e),
            "timestamp": time.time()
        })
        return add_cors_headers(response), 400

@app.route('/face_expression', methods=['POST', 'OPTIONS'])
def set_face_expression():
    """Предустановленные выражения лица"""
    if request.method == 'OPTIONS':
        response = app.make_response('')
        return add_cors_headers(response)
        
    global face_arduino
    
    # Проверяем подключение
    if face_arduino is None or not face_arduino.is_open:
        if not init_face_arduino():
            response = jsonify({
                "status": "error", 
                "message": "Arduino Face не подключен",
                "timestamp": time.time()
            })
            return add_cors_headers(response), 503

    try:
        data = request.json
        if not data:
            response = jsonify({
                "status": "error", 
                "message": "Нет данных в запросе"
            })
            return add_cors_headers(response), 400
            
        expression = data.get('expression', '').lower()
        
        expressions = {
            "neutral": {"eyes": EYE_CENTER, "mouth": MOUTH_MIN},
            "happy": {"eyes": 85, "mouth": 60},
            "surprise": {"eyes": EYE_MAX, "mouth": 40},
            "sad": {"eyes": EYE_MIN, "mouth": 20},
            "blink": {"eyes": 100, "mouth": MOUTH_MIN},
            "angry": {"eyes": 75, "mouth": 10},
            "talking": {"eyes": EYE_CENTER, "mouth": 60}
        }
        
        if expression in expressions:
            angles = expressions[expression]
            command = f"E{angles['eyes']} M{angles['mouth']}"
            
            success, message = send_to_face_arduino(command)
            
            response = jsonify({
                "status": "success" if success else "error", 
                "message": message,
                "expression": expression,
                "timestamp": time.time()
            })
            
            return add_cors_headers(response)
        else:
            response = jsonify({
                "status": "error", 
                "message": f"Неизвестное выражение: {expression}",
                "timestamp": time.time()
            })
            return add_cors_headers(response), 400

    except Exception as e:
        print(f"Ошибка выражения лица: {e}")
        response = jsonify({
            "status": "error", 
            "message": str(e),
            "timestamp": time.time()
        })
        return add_cors_headers(response), 400

# Эндпоинты для камеры
@app.route('/camera/start', methods=['POST', 'OPTIONS'])
def start_camera():
    """Запуск камеры"""
    if request.method == 'OPTIONS':
        response = app.make_response('')
        return add_cors_headers(response)
    
    global camera_running
    
    try:
        if not camera_running:
            if init_camera():
                camera_running = True
                # Запускаем поток камеры
                camera_thread = threading.Thread(target=camera_thread_func, daemon=True)
                camera_thread.start()
                
                response = jsonify({
                    "status": "success",
                    "message": "Камера запущена",
                    "timestamp": time.time()
                })
            else:
                response = jsonify({
                    "status": "error",
                    "message": "Не удалось инициализировать камеру",
                    "timestamp": time.time()
                })
                return add_cors_headers(response), 500
        else:
            response = jsonify({
                "status": "success",
                "message": "Камера уже запущена",
                "timestamp": time.time()
            })
        
        return add_cors_headers(response)
        
    except Exception as e:
        print(f"Ошибка запуска камеры: {e}")
        response = jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": time.time()
        })
        return add_cors_headers(response), 500

@app.route('/camera/stop', methods=['POST', 'OPTIONS'])
def stop_camera():
    """Остановка камеры"""
    if request.method == 'OPTIONS':
        response = app.make_response('')
        return add_cors_headers(response)
    
    global camera_running, camera
    
    try:
        camera_running = False
        if camera:
            with camera_lock:
                camera.release()
                camera = None
        
        response = jsonify({
            "status": "success",
            "message": "Камера остановлена",
            "timestamp": time.time()
        })
        
        return add_cors_headers(response)
        
    except Exception as e:
        print(f"Ошибка остановки камеры: {e}")
        response = jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": time.time()
        })
        return add_cors_headers(response), 500

@app.route('/camera/stream')
def camera_stream():
    """Потоковое видео с камеры (MJPEG)"""
    def generate():
        global latest_frame
        
        while camera_running:
            if latest_frame is not None:
                try:
                    # Кодируем кадр в JPEG
                    ret, jpeg = cv2.imencode('.jpg', latest_frame, 
                                             [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if ret:
                        # Формируем MJPEG кадр
                        frame_bytes = jpeg.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + 
                               frame_bytes + b'\r\n')
                except Exception as e:
                    print(f"Ошибка кодирования кадра: {e}")
            
            time.sleep(0.033)  # ~30 FPS
    
    return Response(generate(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/camera/snapshot')
def camera_snapshot():
    """Получение одного снимка с камеры"""
    global latest_frame
    
    if not camera_running or latest_frame is None:
        response = jsonify({
            "status": "error",
            "message": "Камера не запущена или нет кадра",
            "timestamp": time.time()
        })
        return add_cors_headers(response), 503
    
    try:
        # Кодируем кадр в JPEG
        ret, jpeg = cv2.imencode('.jpg', latest_frame)
        if ret:
            # Возвращаем изображение
            return Response(jpeg.tobytes(),
                          mimetype='image/jpeg')
        else:
            response = jsonify({
                "status": "error",
                "message": "Ошибка кодирования изображения",
                "timestamp": time.time()
            })
            return add_cors_headers(response), 500
    except Exception as e:
        print(f"Ошибка получения снимка: {e}")
        response = jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": time.time()
        })
        return add_cors_headers(response), 500

# Эндпоинт для проверки статуса
@app.route('/status', methods=['GET'])
def get_status():
    """Получение статуса подключения"""
    # Проверяем подключения
    hand_connected = False
    face_connected = False
    
    try:
        if hand_arduino and hand_arduino.is_open:
            hand_connected = True
        else:
            hand_connected = init_hand_arduino()
    except:
        hand_connected = False
    
    try:
        if face_arduino and face_arduino.is_open:
            face_connected = True
        else:
            face_connected = init_face_arduino()
    except:
        face_connected = False
    
    status = {
        "hand_connected": hand_connected,
        "face_connected": face_connected,
        "camera_running": camera_running,
        "hand_port": HAND_SERIAL_PORT,
        "face_port": FACE_SERIAL_PORT,
        "camera_index": CAMERA_INDEX,
        "server": "running",
        "timestamp": time.time()
    }
    
    response = jsonify(status)
    return add_cors_headers(response)

# Эндпоинт для тестирования
@app.route('/test', methods=['GET'])
def test():
    """Тестовый эндпоинт"""
    response = jsonify({
        "status": "ok",
        "message": "Сервер работает",
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": time.time()
    })
    return add_cors_headers(response)

# Эндпоинт для отправки произвольной команды (для отладки)
@app.route('/debug/send', methods=['POST', 'OPTIONS'])
def debug_send():
    """Отправка произвольной команды для отладки"""
    if request.method == 'OPTIONS':
        response = app.make_response('')
        return add_cors_headers(response)
        
    try:
        data = request.json
        if not data:
            response = jsonify({
                "status": "error", 
                "message": "Нет данных в запросе"
            })
            return add_cors_headers(response), 400
            
        command = data.get('command', '')
        target = data.get('target', 'hand')
        
        if target == 'hand':
            success, message = send_to_hand_arduino(command)
        else:
            success, message = send_to_face_arduino(command)
            
        response = jsonify({
            "status": "success" if success else "error",
            "message": message,
            "timestamp": time.time()
        })
        return add_cors_headers(response)
    except Exception as e:
        response = jsonify({
            "status": "error", 
            "message": str(e),
            "timestamp": time.time()
        })
        return add_cors_headers(response), 400

@app.after_request
def after_request(response):
    """Добавляем CORS заголовки ко всем ответам"""
    return add_cors_headers(response)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check эндпоинт"""
    response = jsonify({
        "status": "healthy",
        "timestamp": time.time()
    })
    return add_cors_headers(response)

if __name__ == '__main__':
    print("Запуск сервера для руки и лица...")
    
    # Инициализация Arduino
    init_hand_arduino()
    init_face_arduino()
    
    print("\nДоступные эндпоинты:")
    print("  POST /hand              - Управление рукой")
    print("  POST /face              - Управление лицом")
    print("  POST /face_expression   - Выражения лица")
    print("  POST /camera/start      - Запуск камеры")
    print("  POST /camera/stop       - Остановка камеры")
    print("  GET  /camera/stream     - Потоковое видео (MJPEG)")
    print("  GET  /camera/snapshot   - Один снимок с камеры")
    print("  GET  /status            - Статус подключения")
    print("  GET  /health            - Health check")
    print("\nСервер запущен на http://0.0.0.0:5000")
    
    try:
        app.run(
            host='0.0.0.0', 
            port=5000, 
            threaded=True, 
            debug=False,
            use_reloader=False
        )
    except KeyboardInterrupt:
        print("\nОстановка сервера...")
        camera_running = False
        if camera:
            camera.release()
        if hand_arduino and hand_arduino.is_open:
            hand_arduino.close()
        if face_arduino and face_arduino.is_open:
            face_arduino.close()
    except Exception as e:
        print(f"\nОшибка запуска сервера: {e}")