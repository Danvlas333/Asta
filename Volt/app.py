# app.py
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from datetime import datetime
import logging
from flask import request

# Убираем лишние логи
logging.getLogger('werkzeug').setLevel(logging.WARNING)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'messenger-secret-key-2024'
socketio = SocketIO(app, 
                    cors_allowed_origins="*",
                    ping_timeout=60,
                    ping_interval=25,
                    logger=False,
                    engineio_logger=False)

messages = []
users = {}

# ВАЖНО: Добавляем главный маршрут!
@app.route('/')
def index():
    return render_template('index.html')

# Дополнительный маршрут для проверки
@app.route('/test')
def test():
    return "✅ Сервер работает! Время: " + datetime.now().strftime("%H:%M:%S")

@socketio.on('connect')
def handle_connect():
    print('✅ Новое подключение')
    emit('connected', {'status': 'ok', 'count': len(messages)})

@socketio.on('join')
def handle_join(data):
    username = data.get('username', 'Аноним')
    users[request.sid] = username
    message = f'👤 {username} присоединился'
    print(message)
    emit('new_message', {
        'user': 'Система',
        'text': message,
        'time': datetime.now().strftime('%H:%M')
    }, broadcast=True)

@socketio.on('send_message')
def handle_message(data):
    username = users.get(request.sid, 'Аноним')
    text = data.get('text', '').strip()
    
    if text:
        msg = {
            'id': len(messages),
            'user': username,
            'text': text,
            'time': datetime.now().strftime('%H:%M:%S')
        }
        messages.append(msg)
        
        print(f'💬 {username}: {text}')
        emit('new_message', msg, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    username = users.pop(request.sid, 'Аноним')
    print(f'❌ {username} отключился')

# В начало файла app.py
import socket

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

# В if __name__ == '__main__':
if __name__ == '__main__':
    local_ip = get_local_ip()
    
    print('=' * 50)
    print('🚀 МЕССЕНДЖЕР ЗАПУЩЕН')
    print('=' * 50)
    print(f'📡 Ваш локальный IP: {local_ip}')
    print(f'📱 Локальный доступ: http://localhost:5000')
    print(f'🌐 Сетевой доступ:   http://{local_ip}:5000')
    print('=' * 50)
    
    socketio.run(app,
                 host='0.0.0.0',
                 port=5000,
                 debug=False,
                 allow_unsafe_werkzeug=True)