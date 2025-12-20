# app/config.py
import os
from typing import Dict, Any

RASPBERRY_IP = "192.168.137.157"
BASE_URL = f"http://{RASPBERRY_IP}:5000"

ENDPOINTS = {
    "hand": f"{BASE_URL}/hand",
    "face": f"{BASE_URL}/face",
    "face_expression": f"{BASE_URL}/face_expression",
    "status": f"{BASE_URL}/status",
    "health": f"{BASE_URL}/health",
    "camera_start": f"{BASE_URL}/camera/start",
    "camera_stop": f"{BASE_URL}/camera/stop",
    "camera_stream": f"{BASE_URL}/camera/stream",
    "camera_snapshot": f"{BASE_URL}/camera/snapshot",
}

# 🔧 ИСПРАВЛЕНО: каждый жест — список списков строк
HAND_GESTURES = {
    "🖐️ Открыть": [["0,0,0,0,180,180,0"]],
    "✊ Кулак": [["0,180,180,180,0,0,180"]],
    "👋 Привет": [
        ["50,0,0,180,180,180,0"],
        ["0,0,0,180,180,180,0"],
        ["50,0,0,180,180,180,0"],
        ["0,0,0,180,180,180,0"],
        ["50,0,0,180,180,180,0"],
        ["0,0,0,180,180,180,0"],
    ],
    "👌 OK": [["0,180,180,180,0,180,0"]],
    "👍 Хорошо": [["0,180,180,180,180,180,0"]],
    "☝️ Указать": [["0,180,180,180,180,0,180"]],
}

FACE_EXPRESSIONS = {
    "neutral": {"name": "😐 Нейтральное", "eyes": 90, "mouth": 0},
    "happy": {"name": "😊 Радость", "eyes": 85, "mouth": 60},
    "surprise": {"name": "😮 Удивление", "eyes": 110, "mouth": 40},
    "sad": {"name": "😢 Грусть", "eyes": 70, "mouth": 20},
    "blink": {"name": "😉 Моргание", "eyes": 100, "mouth": 0},
    "angry": {"name": "😠 Злость", "eyes": 75, "mouth": 10},
    "talking": {"name": "💬 Разговор", "eyes": 90, "mouth": 60},
}

SERVO_LIMITS = {
    "wrist": {"min": 0, "max": 90},
    "fingers": {"min": 0, "max": 180},
    "eyes": {"min": 70, "max": 110},
    "mouth": {"min": 0, "max": 80},
}

STYLES = {
    "primary_button": """
        QPushButton {
            background-color: #007bff;
            color: white;
            border: none;
            border-radius: 5px;
            padding: 8px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #0056b3;
        }
        QPushButton:disabled {
            background-color: #6c757d;
        }
    """,
    "success_button": """
        QPushButton {
            background-color: #28a745;
            color: white;
            border: none;
            border-radius: 5px;
            padding: 8px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #218838;
        }
    """,
    "danger_button": """
        QPushButton {
            background-color: #dc3545;
            color: white;
            border: none;
            border-radius: 5px;
            padding: 8px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #c82333;
        }
    """,
    "info_button": """
        QPushButton {
            background-color: #17a2b8;
            color: white;
            border: none;
            border-radius: 5px;
            padding: 8px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #138496;
        }
    """,
    "group_box": """
        QGroupBox {
            font-weight: bold;
            border: 2px solid #6c757d;
            border-radius: 5px;
            margin-top: 10px;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px 0 5px;
        }
    """,
    "chat_window": """
        font-family: Consolas, monospace; 
        font-size: 10pt;
        background-color: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 5px;
        padding: 10px;
    """
}

def validate_ip_address(ip: str) -> bool:
    try:
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        for part in parts:
            if not part.isdigit() or not 0 <= int(part) <= 255:
                return False
        return True
    except:
        return False

def get_config() -> Dict[str, Any]:
    return {
        "raspberry_ip": RASPBERRY_IP,
        "base_url": BASE_URL,
        "endpoints": ENDPOINTS,
        "valid_ip": validate_ip_address(RASPBERRY_IP),
    }