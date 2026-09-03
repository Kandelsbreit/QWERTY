# -*- coding: utf-8 -*-
"""
tray_app.py
Управление иконкой приложения в системном трее Windows:
- Динамический индикатор текущей раскладки (RU / EN) в реальном времени
- Меню переключения режимов (Вкл/Выкл, автоисправление, двойной Shift, Undo)
- Управление автозапуском при старте Windows в реестре
- Быстрый доступ к конфигурационному файлу config.json
"""

import os
import sys
import time
import threading
import subprocess
import ctypes
from PIL import Image, ImageDraw, ImageFont
import pystray
from pystray import MenuItem, Menu

import win32_helper as w32


def create_tray_icon_image(status_text: str = "EN", enabled: bool = True) -> Image.Image:
    """
    Генерирует аккуратную пиктограмму для трея:
    - Синяя плашка для EN
    - Красно-рубиновая плашка для RU
    - Серая плашка для выключенного состояния
    """
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    if not enabled:
        bg_color = "#5A6268"
        text = "OFF"
    elif status_text == "RU":
        bg_color = "#D9383A"  # Приятный рубиново-красный
        text = "RU"
    else:
        bg_color = "#1F6FEB"  # Синий
        text = "EN"

    draw.rounded_rectangle((3, 3, size - 3, size - 3), radius=14, fill=bg_color)

    text_color = "#FFFFFF"
    try:
        font = ImageFont.truetype("arialbd.ttf", 28)
        draw.text((12, 14), text, fill=text_color, font=font)
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", 28)
            draw.text((12, 14), text, fill=text_color, font=font)
        except Exception:
            draw.text((14, 16), text, fill=text_color)

    return image


class TrayApplication:
    def __init__(self, hook_manager):
        self.hook_manager = hook_manager
        self.config_mgr = hook_manager.config_mgr
        self.icon = None
        self._running = False
        self._current_lang = "EN"

    def _toggle_enabled(self, icon, item):
        self.hook_manager.enabled = not self.hook_manager.enabled
        self.config_mgr.set("enabled", self.hook_manager.enabled)
        self._update_icon()

    def _toggle_auto_switch(self, icon, item):
        self.hook_manager.auto_switch = not self.hook_manager.auto_switch
        self.config_mgr.set("auto_switch", self.hook_manager.auto_switch)

    def _toggle_double_shift(self, icon, item):
        cur = self.config_mgr.get("double_shift_switch", True)
        self.config_mgr.set("double_shift_switch", not cur)

    def _toggle_undo(self, icon, item):
        cur = self.config_mgr.get("undo_on_backspace", True)
        self.config_mgr.set("undo_on_backspace", not cur)

    def _toggle_autostart(self, icon, item):
        current_state = w32.is_autostart_enabled()
        new_state = not current_state
        w32.set_autostart(new_state)

    def _convert_manual(self, icon, item):
        self.hook_manager._handle_hotkey_pause()

    def _case_toggle_manual(self, icon, item):
        self.hook_manager._handle_case_toggle()

    def _open_config(self, icon, item):
        try:
            os.startfile(self.config_mgr.config_path)
        except Exception as e:
            subprocess.Popen(["notepad.exe", self.config_mgr.config_path])

    def _show_about(self, icon, item):
        msg = (
            "QWERTY Switcher v1.0.0\n\n"
            "• Автоматическое исправление слов при опечатках в неверной раскладке (Пробел/Enter).\n"
            "• Pause / Break: мгновенная конвертация последнего слова или выделенного текста.\n"
            "• Shift + Pause: конвертация всей набранной строки.\n"
            "• Alt + Pause / Shift + F3: смена регистра выделения (ЗАГЛАВНЫЕ/строчные/Как В Заголовке).\n"
            "• Двойной Shift: быстрое переключение раскладки.\n"
            "• Backspace (Undo): мгновенный откат ошибочной автозамены.\n"
            "• Текстовые сниппеты: ввод @@ вставит email, дд или dd — текущую дату.\n"
            "• Черный список приложений: автоисправление отключается в играх и IDE (настраивается в config.json).\n\n"
            "Потребление памяти: ~20 МБ. Полная приватность и локальная работа."
        )
        ctypes.windll.user32.MessageBoxW(0, msg, "О программе QWERTY Switcher", 0x40 | 0x10000)

    def _exit_app(self, icon, item):
        self._running = False
        self.hook_manager.stop()
        icon.stop()

    def _update_icon(self):
        if not self.icon:
            return
        if not self.hook_manager.enabled:
            self.icon.icon = create_tray_icon_image("OFF", enabled=False)
            self.icon.title = "QWERTY Switcher: Приостановлен"
        else:
            self.icon.icon = create_tray_icon_image(self._current_lang, enabled=True)
            self.icon.title = f"QWERTY Switcher: Активен [{self._current_lang}]"

    def _monitor_active_layout(self):
        """Фоновый поток отслеживания смены раскладки для обновления иконки в трее."""
        while self._running:
            try:
                if self.hook_manager.enabled:
                    is_ru = w32.is_russian_layout()
                    new_lang = "RU" if is_ru else "EN"
                    if new_lang != self._current_lang:
                        self._current_lang = new_lang
                        self._update_icon()
            except Exception:
                pass
            time.sleep(0.3)

    def build_menu(self):
        return Menu(
            MenuItem("QWERTY Switcher v1.0.0", None, enabled=False),
            Menu.SEPARATOR,
            MenuItem(
                "Включено",
                self._toggle_enabled,
                checked=lambda item: self.hook_manager.enabled
            ),
            MenuItem(
                "Автоисправление слов",
                self._toggle_auto_switch,
                checked=lambda item: self.hook_manager.auto_switch
            ),
            MenuItem(
                "Переключение по двойному Shift",
                self._toggle_double_shift,
                checked=lambda item: self.config_mgr.get("double_shift_switch", True)
            ),
            MenuItem(
                "Откат по Backspace (Undo)",
                self._toggle_undo,
                checked=lambda item: self.config_mgr.get("undo_on_backspace", True)
            ),
            MenuItem(
                "Автозапуск при старте Windows",
                self._toggle_autostart,
                checked=lambda item: w32.is_autostart_enabled()
            ),
            Menu.SEPARATOR,
            MenuItem("Конвертировать (Pause / Break)", self._convert_manual),
            MenuItem("Сменить регистр (Alt + Pause)", self._case_toggle_manual),
            MenuItem("Настройки (config.json)", self._open_config),
            MenuItem("Справка / О программе", self._show_about),
            Menu.SEPARATOR,
            MenuItem("Выход", self._exit_app)
        )

    def run(self):
        """Запускает приложение трея."""
        self._running = True
        init_lang = "RU" if w32.is_russian_layout() else "EN"
        self._current_lang = init_lang

        image = create_tray_icon_image(init_lang, enabled=self.hook_manager.enabled)
        menu = self.build_menu()

        self.icon = pystray.Icon(
            "QWERTY_Switcher",
            image,
            f"QWERTY Switcher: Активен [{init_lang}]",
            menu
        )

        # Запускаем поток мониторинга раскладки
        monitor_thread = threading.Thread(target=self._monitor_active_layout, daemon=True)
        monitor_thread.start()

        self.icon.run()
