# -*- coding: utf-8 -*-
"""
keyboard_hook.py
Низкоуровневый перехватчик клавиатуры (WH_KEYBOARD_LL) с расширенным функционалом:
- Буферизация и автоисправление слов
- Откат ошибочной замены по Backspace (Undo) с сессионным черным списком
- Переключение раскладки по двойному нажатию Shift
- Смена регистра текста (Alt + Pause или Shift + F3)
- Поддержка текстовых сниппетов (@@, дд, dd, вв, tt)
- Пропуск автоисправления в играх и программах из черного списка
"""

import threading
import time
import ctypes
from ctypes import wintypes
import layout_mapper as lm
import win32_helper as w32
from config import ConfigManager

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

# Виртуальные коды клавиш
VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_PAUSE = 0x13
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_DELETE = 0x2E
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4
VK_RMENU = 0xA5
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_F3 = 0x72

LLKHF_INJECTED = 0x00000010


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong)
    ]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class KeyboardHookManager:
    def __init__(self, config_manager=None):
        self.config_mgr = config_manager or ConfigManager()
        self.enabled = self.config_mgr.get("enabled", True)
        self.auto_switch = self.config_mgr.get("auto_switch", True)

        self.hook_id = None
        self._hook_thread = None
        self._thread_id = None
        self._callback_ref = None

        # Буферы ввода
        self.current_word = []
        self.current_line = []
        self.lock = threading.Lock()

        # Состояния модификаторов
        self.shift_down = False
        self.ctrl_down = False
        self.alt_down = False
        self.win_down = False

        # Отслеживание двойного Shift
        self._last_shift_up_time = 0.0
        self._intervening_key_pressed = False

        # Откат по Backspace (Undo)
        self._last_replacement = None  # { "original", "converted_full", "orig_lang", "time" }
        self.session_blacklist = set()

    def start(self):
        """Запускает хук в отдельном фоновом потоке."""
        if self._hook_thread and self._hook_thread.is_alive():
            return
        self._hook_thread = threading.Thread(target=self._run_hook, daemon=True)
        self._hook_thread.start()

    def stop(self):
        """Останавливает хук."""
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)
        if self.hook_id:
            user32.UnhookWindowsHookEx(self.hook_id)
            self.hook_id = None

    def _run_hook(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        self._callback_ref = HOOKPROC(self._hook_proc)

        self.hook_id = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self._callback_ref,
            None,
            0
        )

        if not self.hook_id:
            print("Не удалось установить хук клавиатуры.")
            return

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self.hook_id:
            user32.UnhookWindowsHookEx(self.hook_id)
            self.hook_id = None

    def _get_char_from_vk(self, vk_code: int, scan_code: int, hkl) -> str:
        key_state = (ctypes.c_byte * 256)()
        if self.shift_down:
            key_state[0x10] = 0x80
        if user32.GetKeyState(0x14) & 0x0001:  # CapsLock
            key_state[0x14] = 0x01

        buff = ctypes.create_unicode_buffer(8)
        res = user32.ToUnicodeEx(vk_code, scan_code, key_state, buff, 8, 0, hkl)
        if res > 0:
            return buff.value
        return ""

    def _handle_undo(self):
        """Выполняет откат последней автозамены при нажатии Backspace."""
        if not self._last_replacement:
            return False

        elapsed = time.time() - self._last_replacement["time"]
        if elapsed > 3.0:
            self._last_replacement = None
            return False

        replacement = self._last_replacement
        self._last_replacement = None

        def task():
            # Удаляем замененное слово с разделителем
            w32.send_backspaces(len(replacement["converted_full"]))
            # Переключаем раскладку обратно на исходную
            w32.switch_layout_to(replacement["orig_lang"])
            time.sleep(0.01)
            # Впечатываем исходное слово
            w32.send_unicode_text(replacement["original"])
            # Добавляем в черный список текущей сессии
            self.session_blacklist.add(replacement["original"].lower())

        threading.Thread(target=task, daemon=True).start()
        return True

    def _convert_last_word_or_line(self, use_full_line=False):
        """Конвертирует последнее слово или всю строку из буфера."""
        with self.lock:
            if use_full_line and self.current_line:
                raw_text = "".join(self.current_line)
                self.current_line.clear()
                self.current_word.clear()
            elif self.current_word:
                raw_text = "".join(self.current_word)
                self.current_word.clear()
            elif self.current_line:
                raw_text = "".join(self.current_line)
                self.current_line.clear()
            else:
                return

        char_count = len(raw_text)
        w32.send_backspaces(char_count)
        converted = lm.convert_auto(raw_text)
        w32.toggle_layout()
        time.sleep(0.01)
        w32.send_unicode_text(converted)

    def _handle_hotkey_pause(self):
        """Обработка Pause / Break (конвертация раскладки)."""
        def task():
            copied = w32.copy_selection()
            if copied and len(copied.strip()) > 0:
                converted = lm.convert_auto(copied)
                w32.paste_text(converted)
                w32.toggle_layout()
                with self.lock:
                    self.current_word.clear()
                    self.current_line.clear()
            else:
                use_line = self.shift_down
                self._convert_last_word_or_line(use_full_line=use_line)

        threading.Thread(target=task, daemon=True).start()

    def _handle_case_toggle(self):
        """Обработка смены регистра выделенного текста (Alt + Pause или Shift + F3)."""
        def task():
            copied = w32.copy_selection()
            if copied and len(copied) > 0:
                new_text = lm.toggle_case(copied)
                w32.paste_text(new_text)

        threading.Thread(target=task, daemon=True).start()

    def _handle_auto_switch(self, delimiter_char: str):
        """Проверяет слово на сниппеты и ошибочную раскладку."""
        with self.lock:
            word = "".join(self.current_word)
            self.current_word.clear()
            self.current_line.append(delimiter_char)
            if len(self.current_line) > 300:
                self.current_line = self.current_line[-200:]

        if not word or len(word) < 1:
            return False

        # 1. Проверка черного списка приложений (игры, IDE, консоли)
        blacklist = self.config_mgr.get("app_blacklist", [])
        if w32.is_process_blacklisted(blacklist):
            return False

        # 2. Проверка текстовых сниппетов (автозамена)
        snippets = self.config_mgr.get("snippets", {})
        if word in snippets:
            expanded = self.config_mgr.expand_snippet(snippets[word])
            def task_snippet():
                w32.send_backspaces(len(word))
                w32.send_unicode_text(expanded + delimiter_char)
            threading.Thread(target=task_snippet, daemon=True).start()
            return True

        # Если слово в черном списке сессии — пропускаем
        if word.lower() in self.session_blacklist:
            return False

        # 3. Проверка необходимости автоисправления
        custom_words = self.config_mgr.get("custom_words", {})
        excluded_words = set(self.config_mgr.get("excluded_words", []))

        should_to_ru = lm.should_convert_en_to_ru(word, custom_words, excluded_words)
        should_to_en = lm.should_convert_ru_to_en(word, custom_words, excluded_words)

        if not should_to_ru and not should_to_en:
            return False

        target_lang = "ru" if should_to_ru else "en"
        orig_lang = "en" if should_to_ru else "ru"
        converted_word = lm.convert_to_ru(word) if should_to_ru else lm.convert_to_en(word)

        # Сохраняем состояние для отката по Backspace
        if self.config_mgr.get("undo_on_backspace", True):
            self._last_replacement = {
                "original": word,
                "converted_full": converted_word + delimiter_char,
                "orig_lang": orig_lang,
                "time": time.time()
            }

        def task():
            w32.send_backspaces(len(word))
            w32.switch_layout_to(target_lang)
            time.sleep(0.01)
            w32.send_unicode_text(converted_word + delimiter_char)

        threading.Thread(target=task, daemon=True).start()
        return True

    def _hook_proc(self, nCode, wParam, lParam):
        if nCode < 0:
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        try:
            p_kbd = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            vk = p_kbd.vkCode
            flags = p_kbd.flags

            if flags & LLKHF_INJECTED:
                return user32.CallNextHookEx(None, nCode, wParam, lParam)

            is_down = (wParam == WM_KEYDOWN or wParam == WM_SYSKEYDOWN)
            is_up = (wParam == WM_KEYUP or wParam == WM_SYSKEYUP)

            # Отслеживание модификаторов
            if vk in (VK_LSHIFT, VK_RSHIFT):
                self.shift_down = is_down
                if is_up and self.config_mgr.get("double_shift_switch", True) and self.enabled:
                    now = time.time()
                    if not self._intervening_key_pressed and (now - self._last_shift_up_time < 0.35):
                        # Двойное нажатие Shift зафиксировано!
                        w32.toggle_layout()
                        self._last_shift_up_time = 0.0
                    else:
                        self._last_shift_up_time = now
                    self._intervening_key_pressed = False
                elif is_down:
                    pass
            elif vk in (VK_LCONTROL, VK_RCONTROL):
                self.ctrl_down = is_down
                self._intervening_key_pressed = True
            elif vk in (VK_LMENU, VK_RMENU):
                self.alt_down = is_down
                self._intervening_key_pressed = True
            elif vk in (VK_LWIN, VK_RWIN):
                self.win_down = is_down
                self._intervening_key_pressed = True
            else:
                if is_down:
                    self._intervening_key_pressed = True

            if not is_down:
                return user32.CallNextHookEx(None, nCode, wParam, lParam)

            # 1. Хоткей смены регистра (Alt + Pause или Shift + F3)
            if (vk == VK_PAUSE and self.alt_down) or (vk == VK_F3 and self.shift_down):
                if self.enabled:
                    self._handle_case_toggle()
                    return 1

            # 2. Хоткей Pause / Break (конвертация текста)
            if vk == VK_PAUSE:
                if self.enabled:
                    self._handle_hotkey_pause()
                    return 1

            if not self.enabled:
                return user32.CallNextHookEx(None, nCode, wParam, lParam)

            # Сочетания клавиш (Ctrl+C, Alt+Tab и т.п.)
            if self.ctrl_down or self.alt_down or self.win_down:
                if vk in (ord('C'), ord('V'), ord('X'), ord('Z'), ord('A')):
                    with self.lock:
                        self.current_word.clear()
                        self.current_line.clear()
                return user32.CallNextHookEx(None, nCode, wParam, lParam)

            # Навигация и Esc
            if vk in (VK_ESCAPE, VK_LEFT, VK_RIGHT, VK_UP, VK_DOWN, VK_DELETE):
                with self.lock:
                    self.current_word.clear()
                self._last_replacement = None
                return user32.CallNextHookEx(None, nCode, wParam, lParam)

            # Клавиша Backspace (с поддержкой Undo)
            if vk == VK_BACK:
                if self.config_mgr.get("undo_on_backspace", True) and self._last_replacement:
                    if self._handle_undo():
                        return 1

                with self.lock:
                    if self.current_word:
                        self.current_word.pop()
                    if self.current_line:
                        self.current_line.pop()
                return user32.CallNextHookEx(None, nCode, wParam, lParam)

            # Любая другая клавиша сбрасывает возможность отката по Backspace
            self._last_replacement = None

            # Раскладка и печатный символ
            hkl = w32.get_window_layout()
            char = self._get_char_from_vk(vk, p_kbd.scanCode, hkl)

            # Разделители слов
            if vk in (VK_SPACE, VK_RETURN) or (char in " \t\r\n"):
                delim = "\n" if vk == VK_RETURN else " "
                if self.auto_switch:
                    handled = self._handle_auto_switch(delim)
                    if handled:
                        return 1
                else:
                    with self.lock:
                        self.current_word.clear()
                        self.current_line.append(delim)
                return user32.CallNextHookEx(None, nCode, wParam, lParam)

            if char:
                with self.lock:
                    self.current_word.append(char)
                    self.current_line.append(char)

        except Exception:
            pass

        return user32.CallNextHookEx(None, nCode, wParam, lParam)
