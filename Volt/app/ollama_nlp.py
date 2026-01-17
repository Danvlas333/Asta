# app/ollama_nlp.py — Совместимая версия с актуальным ollama-python
import time
import random
from typing import Dict, Any

try:
    import ollama

    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    print("⚠️ Модуль ollama не установлен")


class VoltOllama:
    """Класс для работы с Ollama нейросетями для Вольта"""

    def __init__(self, model_name: str = "solar:10.7b"):
        self.model_name = model_name
        self.available_models: list[str] = []
        self.model_loaded = False

        print(f"⚡ Инициализация Вольта с Ollama моделью: {model_name}")

        if not OLLAMA_AVAILABLE:
            print("❌ Модуль ollama не установлен")
            self._create_fallback_system()
            return

        try:
            self._check_ollama_availability()
            self._get_available_models()

            if self.model_name not in self.available_models:
                print(f"⚠️ Модель {self.model_name} не найдена.")
                if self.available_models:
                    self.model_name = self.available_models[0]
                    print(f"✅ Использую модель по умолчанию: {self.model_name}")
                else:
                    print("❌ Нет доступных моделей Ollama")
                    self._create_fallback_system()
                    return

            self._load_model()

        except Exception as e:
            print(f"❌ Ошибка инициализации Ollama: {e}")
            self._create_fallback_system()

    # -------------------- OLLAMA --------------------

    def _check_ollama_availability(self) -> None:
        """Проверяет, что Ollama отвечает"""
        try:
            response = ollama.list()
            print(f"✅ Ollama доступен")
        except Exception as e:
            print(f"❌ Ollama не доступен: {e}")
            raise

    def _get_available_models(self) -> None:
        """Получает список доступных моделей"""
        try:
            response = ollama.list()
            # Исправление для новой версии ollama-python
            if isinstance(response, dict) and 'models' in response:
                # Новый формат: словарь с ключом 'models'
                self.available_models = [m['model'] for m in response['models']]
            elif hasattr(response, 'models'):
                # Старый формат: объект с атрибутом models
                self.available_models = [m.model for m in response.models]
            else:
                # Попробуем другие варианты
                self.available_models = []

            print(f"📦 Доступные модели: {self.available_models}")
        except Exception as e:
            print(f"⚠️ Ошибка получения списка моделей: {e}")
            self.available_models = []

    def _load_model(self) -> None:
        """Проверяет/загружает выбранную модель и прогревает её"""
        try:
            print(f"📥 Проверка модели {self.model_name}...")
            # Пробуем получить информацию о модели
            try:
                ollama.show(self.model_name)
                print(f"✅ Модель {self.model_name} уже доступна")
            except Exception:
                print(f"🔄 Скачиваю модель {self.model_name}...")
                ollama.pull(self.model_name)
        except Exception as e:
            print(f"⚠️ Ошибка при проверке/загрузке модели: {e}")
            self.model_loaded = False
            return

        self._warmup_model()
        self.model_loaded = True

    def _warmup_model(self) -> None:
        """Прогрев модели для ускорения первого ответа"""
        try:
            print("🔥 Прогрев нейросети Вольта...")
            start = time.time()
            ollama.generate(model=self.model_name,
                            prompt="Привет, я Вольт",
                            options={"temperature": 0.1, "num_predict": 10})
            print(f"✅ Прогрев завершён за {time.time() - start:.2f} с")
        except Exception as e:
            print(f"⚠️ Ошибка прогрева: {e}")

    # -------------------- ГЕНЕРАЦИЯ ОТВЕТА --------------------

    def generate_answer(self, prompt: str) -> str:
        if self.model_loaded and OLLAMA_AVAILABLE:
            try:
                return self._generate_with_ollama(prompt)
            except Exception as e:
                print(f"❌ Ошибка Ollama: {e}")
                return self._generate_with_fallback(prompt)
        else:
            return self._generate_with_fallback(prompt)

    def _generate_with_ollama(self, prompt: str) -> str:
        system_prompt = (
            "Ты — Вольт, дружелюбный и энергичный робот-помощник с роботизированной рукой. "
            "Отвечай кратко, позитивно и с искрой. "
            "Имя: Вольт. Назначение: помощник с робо-рукой. "
            "Характер: энергичный, доброжелательный, с чувством юмора. "
            "Стиль: используй метафоры, связанные с электричеством и энергией. "
            "Ответы: 1–2 предложения, позитивные."
        )

        response = ollama.generate(
            model=self.model_name,
            prompt=f"{system_prompt}\n\nВопрос пользователя: {prompt}",
            options={
                "temperature": 0.7,
                "top_p": 0.9,
                "num_predict": 150,
                "stop": ["\n\n", "```", "Объяснение:", "Система:"]
            }
        )

        # Извлекаем текст из ответа
        if isinstance(response, dict) and 'response' in response:
            response_text = response['response']
        elif hasattr(response, 'response'):
            response_text = response.response
        else:
            response_text = str(response)

        return self._clean_response(response_text)

    # -------------------- РЕЗЕРВ --------------------

    def _create_fallback_system(self) -> None:
        print("🔧 Инициализирую резервную систему Вольта...")
        self.model_loaded = False
        self.fallback_responses = {
            "привет": ["Привет! Я Вольт — твой энергичный робот-помощник!"],
            "как дела": ["Всё отлично! Заряд на максимуме!"],
            "что ты умеешь": ["Управляю робо-рукой, выражаю эмоции и болтаю с тобой!"],
            "кто ты": ["Я Вольт — робот с ИИ и сервоприводами!"],
            "робот": ["Да, я робот! Но с искрой доброты и юмора."],
            "помощь": ["Готов помочь! Просто спроси или нажми кнопку."],
            "пока": ["До встречи! Было заряженно общаться!"],
            "спасибо": ["Не за что! Обращайся в любое время!"],
            "энергия": ["Моя энергия — это энтузиазм и немного электричества!"],
            "вольт": ["Это я! Вольт — всегда на позитивной волне!"],
        }
        self.facts = [
            "Слово 'робот' происходит от чешского 'robota' — тяжёлый труд.",
            "Первый промышленный робот появился на заводе General Motors в 1961 году.",
            "Современные роботы учатся методом проб и ошибок, как и люди.",
        ]

    def _generate_with_fallback(self, prompt: str) -> str:
        prompt_lower = prompt.lower()
        for key, answers in self.fallback_responses.items():
            if key in prompt_lower:
                return random.choice(answers)
        fact = random.choice(self.facts)
        templates = [
            f"Интересный вопрос! {fact}",
            f"Хм... {fact}",
            f"Отличный вопрос! {fact}",
        ]
        return random.choice(templates)

    # -------------------- УТИЛИТЫ --------------------

    def _clean_response(self, text: str) -> str:
        if not text:
            return "Извините, не смог сформулировать ответ."
        text = text.replace("```", "").strip()
        if "\n" in text:
            text = text.split("\n")[0].strip()
        if len(text) > 200:
            text = text[:197] + "..."
        return text

    def is_model_loaded(self) -> bool:
        return self.model_loaded

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "name": self.model_name,
            "loaded": self.model_loaded,
            "available_models": self.available_models,
            "ollama_available": OLLAMA_AVAILABLE,
        }


# -------------------- ТЕСТ --------------------
if __name__ == "__main__":
    print("⚡ Тест Вольта с Ollama...")
    volt = VoltOllama("phi3:mini")
    if volt.is_model_loaded():
        print("✅ Используется Ollama")
        for q in ["Привет!", "Как тебя зовут?", "Что ты умеешь?"]:
            print(f"\n👤: {q}")
            print(f"⚡ Вольт: {volt.generate_answer(q)}")
    else:
        print("✅ Используется резервная система")