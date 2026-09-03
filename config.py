# -*- coding: utf-8 -*-
"""
config.py
Управление конфигурацией QWERTY Switcher.
Загрузка, сохранение и значения по умолчанию в формате JSON.
Поддерживает постоянное сохранение настроек рядом с .exe или в %APPDATA%.
"""

import os
import sys
import json
from datetime import datetime

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "enabled": True,
    "auto_switch": True,
    "double_shift_switch": True,
    "undo_on_backspace": True,
    "app_blacklist": [
        "code.exe",
        "devenv.exe",
        "powershell.exe",
        "cmd.exe",
        "windowsterminal.exe",
        "wt.exe",
        "cs2.exe",
        "dota2.exe",
        "steam.exe",
        "epicgameslauncher.exe"
    ],
    "snippets": {
        "@@": "my_email@example.com",
        "дд": "{date}",
        "dd": "{date}",
        "вв": "{time}",
        "tt": "{time}"
    },
    "custom_words": {
        "ghbdtnbr": "приветик"
    },
    "excluded_words": [
        "git", "npm", "pip", "run", "add", "commit", "push", "pull", "test"
    ]
}


def get_default_config_path() -> str:
    """
    Определяет надежный постоянный путь к config.json.
    - Для автономного .exe: папка с исполняемым файлом.
    - Если папка с .exe защищена от записи (Program Files): %APPDATA%\\QWERTY_Switcher.
    - Для исходного кода: папка со скриптом.
    """
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        test_file = os.path.join(exe_dir, ".write_test")
        try:
            with open(test_file, "w") as f:
                f.write("1")
            os.remove(test_file)
            return os.path.join(exe_dir, CONFIG_FILE)
        except (PermissionError, OSError):
            pass

    appdata = os.environ.get("APPDATA")
    if appdata:
        app_dir = os.path.join(appdata, "QWERTY_Switcher")
        os.makedirs(app_dir, exist_ok=True)
        return os.path.join(app_dir, CONFIG_FILE)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, CONFIG_FILE)


class ConfigManager:
    def __init__(self, config_path=None):
        self.config_path = config_path or get_default_config_path()
        self.config = {}
        self.load()

    def load(self):
        """Загружает настройки из JSON файла или создает значения по умолчанию."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.config = DEFAULT_CONFIG.copy()
                    self.config.update(loaded)
                    return self.config
            except Exception as e:
                print(f"Ошибка загрузки config.json: {e}. Используются настройки по умолчанию.")
        self.config = DEFAULT_CONFIG.copy()
        self.save()
        return self.config

    def save(self):
        """Сохраняет текущую конфигурацию в файл."""
        try:
            dirname = os.path.dirname(self.config_path)
            if dirname:
                os.makedirs(dirname, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения config.json: {e}")

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save()

    def expand_snippet(self, text: str) -> str:
        """Подставляет динамические переменные в сниппет."""
        now = datetime.now()
        date_str = now.strftime("%d.%m.%Y")
        time_str = now.strftime("%H:%M")
        return text.replace("{date}", date_str).replace("{time}", time_str)
