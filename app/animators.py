# app/animators.py
from PyQt5.QtCore import QTimer
from typing import Callable, List, Optional
from app.network import ConnectionManager
import random

class MouthAnimator:
    def __init__(self, voice_synth):
        self.voice_synth = voice_synth
        self.timer = QTimer()
        self.timer.timeout.connect(self._animate_mouth)
        self.is_speaking = False
        self.text_chars = []
        self.char_index = 0
        self.mouth_open = False

    def start_speaking_animation(self, text: str):
        clean_text = ''.join(ch for ch in text if ch.isalpha() or ch.isspace())
        self.text_chars = list(clean_text)
        self.char_index = 0
        self.is_speaking = True
        self.mouth_open = False
        self.timer.start(80)

    def stop_animation(self):
        self.is_speaking = False
        self.timer.stop()
        ConnectionManager.send_face_command({"mouth": 0})

    def _animate_mouth(self):
        if not self.is_speaking or not self.text_chars:
            self.stop_animation()
            return

        if self.char_index >= len(self.text_chars):
            if self.mouth_open:
                ConnectionManager.send_face_command({"mouth": 0})
                self.mouth_open = False
            self.stop_animation()
            return

        char = self.text_chars[self.char_index]
        self.char_index += 1

        if char.isspace() or not char.isalpha():
            target = 0
        else:
            vowels = "аеёиоуыэюяaeiouy"
            if char.lower() in vowels:
                target = random.randint(50, 80)
            else:
                target = random.randint(20, 40)

        ConnectionManager.send_face_command({"mouth": target})
        self.mouth_open = target > 0


class HandAnimator:
    def __init__(self, log_callback: Optional[Callable[[str, str], None]] = None):
        self.log_callback = log_callback or (lambda s, m: None)
        self.is_running = False

    def execute_gesture_sequence(self, gesture_name: str, sequences: List[List[str]]):
        if self.is_running:
            self.log_callback("Система", f"⚠️ Жест '{gesture_name}' уже выполняется")
            return

        self.is_running = True
        self._execute_next_step(0, sequences, gesture_name)

    def _execute_next_step(self, index: int, sequences: List[List[str]], gesture_name: str):
        from PyQt5.QtCore import QTimer
        if index >= len(sequences) or not self.is_running:
            self.is_running = False
            self.log_callback("Система", f"✅ Жест '{gesture_name}' завершён")
            return

        angle_str = sequences[index][0]
        try:
            angles_list = list(map(int, angle_str.split(',')))
            if len(angles_list) != 7:
                raise ValueError("Требуется 7 углов: wrist,f1,f2,f3,f4,f5,f6")
            angles = {
                "wrist": angles_list[0],
                "f1": angles_list[1],
                "f2": angles_list[2],
                "f3": angles_list[3],
                "f4": angles_list[4],
                "f5": angles_list[5],
                "f6": angles_list[6],
            }
            result = ConnectionManager.send_hand_command(angles)
            if not result.get("success"):
                self.log_callback("Система", f"❌ Ошибка жеста '{gesture_name}': {result.get('error', 'Неизвестно')}")
                self.is_running = False
                return
        except Exception as e:
            self.log_callback("Система", f"❌ Ошибка парсинга жеста '{gesture_name}': {e}")
            self.is_running = False
            return

        QTimer.singleShot(400, lambda: self._execute_next_step(index + 1, sequences, gesture_name))

    def stop(self):
        self.is_running = False