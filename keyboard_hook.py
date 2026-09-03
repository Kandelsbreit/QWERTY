# -*- coding: utf-8 -*-
"""
keyboard_hook.py
Низкоуровневый перехватчик клавиатуры (WH_KEYBOARD_LL):
- Атомарная замена слов и разделителей (SendInput)
- Сохранение пунктуации при автозамене (исключает превращение запятой в 'б' или точки в 'ю')
- Поддержка дефиса '-' в сложных словах (что-то, как-нибудь, well-known)
- Строгая проверка текущей раскладки: исключает ложную конвертацию уже русских слов
- Откат ошибочной замены по Backspace (Undo)
- Переключение раскладки по двойному нажатию Shift
- Смена регистра текста (Alt + Pause или Shift + F3)
- Текстовые сниппеты (@@, дд, dd, вв, tt)
- Игнорирование черного списка приложений
"""

import threading
import time
import atexit
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
VK_CAPITAL = 0x14
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

# Таблицы маппинга символов
VK_LETTERS_EN = {vk: chr(vk + 32) for vk in range(0x41, 0x5B)}
VK_LETTERS_RU = {
    0x41: "ф", 0x42: "и", 0x43: "с", 0x44: "в", 0x45: "у", 0x46: "а",
    0x47: "п", 0x48: "р", 0x49: "ш", 0x4A: "о", 0x4B: "л", 0x4C: "д",
    0x4D: "ь", 0x4E: "т", 0x4F: "щ", 0x50: "з", 0x51: "й", 0x52: "к",
    0x53: "ы", 0x54: "е", 0x55: "г", 0x56: "м", 0x57: "ц", 0x58: "ч",
    0x59: "н", 0x5A: "я"
}

# Включаем дефис 0xBD и равно 0xBB
VK_OEM_EN = {
    0xBA: ";", 0xBF: "/", 0xC0: "`", 0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'",
    0xBC: ",", 0xBE: ".", 0xBD: "-", 0xBB: "="
}
VK_OEM_RU = {
    0xBA: "ж", 0xBF: ".", 0xC0: "ё", 0xDB: "х", 0xDC: "\\", 0xDD: "ъ", 0xDE: "э",
    0xBC: "б", 0xBE: "ю", 0xBD: "-", 0xBB: "="
}

VK_SHIFT_NUMS_EN = {
    0x31: "!", 0x32: "@", 0x33: "#", 0x34: "$", 0x35: "%",
    0x36: "^", 0x37: "&", 0x38: "*", 0x39: "(", 0x30: ")"
}
VK_SHIFT_NUMS_RU = {
    0x31: "!", 0x32: '"', 0x33: "№", 0x34: ";", 0x35: "%",
    0x36: ":", 0x37: "?", 0x38: "*", 0x39: "(", 0x30: ")"
}


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong)
    ]


HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_longlong,
    ctypes.c_int,
    wintypes.WPARAM,
    ctypes.POINTER(KBDLLHOOKSTRUCT)
)

user32.CallNextHookEx.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
    wintypes.WPARAM,
    ctypes.POINTER(KBDLLHOOKSTRUCT)
]
user32.CallNextHookEx.restype = ctypes.c_longlong

user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int,
    HOOKPROC,
    ctypes.c_void_p,
    wintypes.DWORD
]
user32.SetWindowsHookExW.restype = ctypes.c_void_p

user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL


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
        self._last_replacement = None
        self.session_blacklist = set()

        atexit.register(self.stop)

    def start(self):
        """Запускает хук в отдельном фоновом потоке."""
        if self._hook_thread and self._hook_thread.is_alive():
            return
        self._hook_thread = threading.Thread(target=self._run_hook, daemon=True)
        self._hook_thread.start()

    def stop(self):
        """Останавливает хук."""
        hook_handle = self.hook_id
        self.hook_id = None

        if hook_handle:
            try:
                user32.UnhookWindowsHookEx(hook_handle)
            except Exception:
                pass

        if self._thread_id:
            try:
                user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)
            except Exception:
                pass
            self._thread_id = None

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
            print("Ошибка: не удалось установить низкоуровневый хук клавиатуры.")
            return

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self.hook_id:
            user32.UnhookWindowsHookEx(self.hook_id)
            self.hook_id = None

    def _get_char_from_vk_safe(self, vk: int, is_ru: bool) -> str:
        caps = bool(user32.GetKeyState(VK_CAPITAL) & 0x0001)
        uppercase = (self.shift_down ^ caps)

        if 0x41 <= vk <= 0x5A:
            ch = VK_LETTERS_RU.get(vk, "") if is_ru else VK_LETTERS_EN.get(vk, "")
            return ch.upper() if uppercase else ch

        if is_ru and vk in VK_OEM_RU:
            return VK_OEM_RU[vk]
        elif not is_ru and vk in VK_OEM_EN:
            return VK_OEM_EN[vk]

        if 0x30 <= vk <= 0x39:
            if self.shift_down:
                return (VK_SHIFT_NUMS_RU if is_ru else VK_SHIFT_NUMS_EN).get(vk, "")
            return chr(vk)

        return ""

    def _handle_undo(self):
        """Откат последней автозамены при нажатии Backspace."""
        if not self._last_replacement:
            return False

        elapsed = time.time() - self._last_replacement["time"]
        if elapsed > 3.0:
            self._last_replacement = None
            return False

        replacement = self._last_replacement
        self._last_replacement = None

        w32.atomic_replace_text(
            backspaces=len(replacement["converted_full"]),
            new_text=replacement["original"],
            target_lang=replacement["orig_lang"]
        )
        self.session_blacklist.add(replacement["original"].lower())
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

        converted = lm.convert_auto(raw_text)
        w32.atomic_replace_text(
            backspaces=len(raw_text),
            new_text=converted
        )
        w32.toggle_layout()

    def _handle_hotkey_pause(self):
        """Обработка Pause / Break с сохранением буфера обмена."""
        def task():
            try:
                copied, old_clip = w32.copy_selection()
                if copied and len(copied.strip()) > 0:
                    converted = lm.convert_auto(copied)
                    w32.paste_text(converted, restore_old_clipboard=old_clip)
                    w32.toggle_layout()
                    with self.lock:
                        self.current_word.clear()
                        self.current_line.clear()
                else:
                    use_line = self.shift_down
                    self._convert_last_word_or_line(use_full_line=use_line)
            except Exception:
                pass

        threading.Thread(target=task, daemon=True).start()

    def _handle_case_toggle(self):
        """Смена регистра выделенного текста с сохранением буфера обмена."""
        def task():
            try:
                copied, old_clip = w32.copy_selection()
                if copied and len(copied) > 0:
                    new_text = lm.toggle_case(copied)
                    w32.paste_text(new_text, restore_old_clipboard=old_clip)
            except Exception:
                pass

        threading.Thread(target=task, daemon=True).start()

    def _handle_auto_switch(self, delimiter_char: str):
        """Проверяет слово на сниппеты и ошибочную раскладку с сохранением пунктуации."""
        with self.lock:
            word = "".join(self.current_word)
            self.current_word.clear()
            self.current_line.append(delimiter_char)
            if len(self.current_line) > 300:
                self.current_line = self.current_line[-200:]

        if not word or len(word) < 1:
            return False

        # Черный список приложений
        blacklist = self.config_mgr.get("app_blacklist", [])
        if w32.is_process_blacklisted(blacklist):
            return False

        # Текстовые сниппеты
        snippets = self.config_mgr.get("snippets", {})
        if word in snippets:
            expanded = self.config_mgr.expand_snippet(snippets[word])
            w32.atomic_replace_text(
                backspaces=len(word),
                new_text=expanded + delimiter_char
            )
            return True

        if word.lower() in self.session_blacklist:
            return False

        custom_words = self.config_mgr.get("custom_words", {})
        excluded_words = set(self.config_mgr.get("excluded_words", []))

        # СТРОГАЯ ПРИВЯЗКА К ТЕКУЩЕЙ РАСКЛАДКЕ:
        is_ru_layout = w32.is_russian_layout()
        should_to_ru = False
        should_to_en = False

        if is_ru_layout:
            # Активна русская раскладка: проверяем ТОЛЬКО ошибочный ввод английских слов (руддщ -> hello)
            should_to_en = lm.should_convert_ru_to_en(word, custom_words, excluded_words)
        else:
            # Активна английская раскладка: проверяем ТОЛЬКО ошибочный ввод русских слов (ghbdtn -> привет)
            should_to_ru = lm.should_convert_en_to_ru(word, custom_words, excluded_words)

        if not should_to_ru and not should_to_en:
            return False

        target_lang = "ru" if should_to_ru else "en"
        orig_lang = "en" if should_to_ru else "ru"

        # Сохраняем завершающие знаки препинания (. , ! ? ; : " ')
        converted_word = lm.convert_preserving_punctuation(word, to_ru=should_to_ru)

        if self.config_mgr.get("undo_on_backspace", True):
            self._last_replacement = {
                "original": word,
                "converted_full": converted_word + delimiter_char,
                "orig_lang": orig_lang,
                "time": time.time()
            }

        # Атомарная замена в одном SendInput
        w32.atomic_replace_text(
            backspaces=len(word),
            new_text=converted_word + delimiter_char,
            target_lang=target_lang
        )
        return True

    def _hook_proc(self, nCode, wParam, p_kbd_ptr):
        if nCode < 0 or not p_kbd_ptr:
            return user32.CallNextHookEx(None, nCode, wParam, p_kbd_ptr)

        try:
            p_kbd = p_kbd_ptr.contents
            flags = p_kbd.flags

            if flags & LLKHF_INJECTED:
                return user32.CallNextHookEx(None, nCode, wParam, p_kbd_ptr)

            vk = p_kbd.vkCode
            is_down = (wParam == WM_KEYDOWN or wParam == WM_SYSKEYDOWN)
            is_up = (wParam == WM_KEYUP or wParam == WM_SYSKEYUP)

            # Отслеживание Shift / Ctrl / Alt / Win
            if vk in (VK_LSHIFT, VK_RSHIFT):
                self.shift_down = is_down
                if is_up and self.config_mgr.get("double_shift_switch", True) and self.enabled:
                    now = time.time()
                    if not self._intervening_key_pressed and (now - self._last_shift_up_time < 0.35):
                        w32.toggle_layout()
                        self._last_shift_up_time = 0.0
                    else:
                        self._last_shift_up_time = now
                    self._intervening_key_pressed = False
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
                return user32.CallNextHookEx(None, nCode, wParam, p_kbd_ptr)

            # Хоткей смены регистра (Alt + Pause или Shift + F3)
            if (vk == VK_PAUSE and self.alt_down) or (vk == VK_F3 and self.shift_down):
                if self.enabled:
                    self._handle_case_toggle()
                    return 1

            # Хоткей Pause / Break
            if vk == VK_PAUSE:
                if self.enabled:
                    self._handle_hotkey_pause()
                    return 1

            if not self.enabled:
                return user32.CallNextHookEx(None, nCode, wParam, p_kbd_ptr)

            # Комбинации Ctrl/Alt/Win
            if self.ctrl_down or self.alt_down or self.win_down:
                if vk in (ord('C'), ord('V'), ord('X'), ord('Z'), ord('A')):
                    with self.lock:
                        self.current_word.clear()
                        self.current_line.clear()
                return user32.CallNextHookEx(None, nCode, wParam, p_kbd_ptr)

            # Навигация
            if vk in (VK_ESCAPE, VK_LEFT, VK_RIGHT, VK_UP, VK_DOWN, VK_DELETE):
                with self.lock:
                    self.current_word.clear()
                self._last_replacement = None
                return user32.CallNextHookEx(None, nCode, wParam, p_kbd_ptr)

            # Backspace
            if vk == VK_BACK:
                if self.config_mgr.get("undo_on_backspace", True) and self._last_replacement:
                    if self._handle_undo():
                        return 1

                with self.lock:
                    if self.current_word:
                        self.current_word.pop()
                    if self.current_line:
                        self.current_line.pop()
                return user32.CallNextHookEx(None, nCode, wParam, p_kbd_ptr)

            self._last_replacement = None

            # Разделители слов (Space / Enter)
            if vk in (VK_SPACE, VK_RETURN):
                delim = "\n" if vk == VK_RETURN else " "
                if self.auto_switch:
                    handled = self._handle_auto_switch(delim)
                    if handled:
                        return 1
                else:
                    with self.lock:
                        self.current_word.clear()
                        self.current_line.append(delim)
                return user32.CallNextHookEx(None, nCode, wParam, p_kbd_ptr)

            # Печатные символы
            is_ru = w32.is_russian_layout()
            char = self._get_char_from_vk_safe(vk, is_ru)
            if char:
                with self.lock:
                    self.current_word.append(char)
                    self.current_line.append(char)

        except Exception:
            pass

        return user32.CallNextHookEx(None, nCode, wParam, p_kbd_ptr)
