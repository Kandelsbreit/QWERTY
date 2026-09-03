# -*- coding: utf-8 -*-
"""
win32_helper.py
Функции взаимодействия с Windows API:
- Получение и переключение раскладки активного окна
- Атомарная замена текста через SendInput (полная 40-байтная структура для x64 Windows)
- Работа с буфером обмена
- Определение процесса активного окна и проверка черного списка
- Управление автозапуском в реестре Windows
"""

import sys
import os
import time
import ctypes
from ctypes import wintypes
import winreg

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Константы Windows API
WM_INPUTLANGCHANGEREQUEST = 0x0050
HKL_NEXT = 1
HKL_PREV = 2
KLF_ACTIVATE = 1

LANG_RU = 0x0419
LANG_EN = 0x0409

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK_BACK = 0x08
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_C = 0x43
VK_V = 0x56

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# Полная спецификация структур Windows SDK для SendInput (ровно 40 байт на x64)
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong)
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong)
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD)
    ]

class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [
            ("mi", MOUSEINPUT),
            ("ki", KEYBDINPUT),
            ("hi", HARDWAREINPUT)
        ]
    _anonymous_ = ("_input",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("_input", _INPUT)
    ]


# Строгая типизация ВСЕХ функций Win32 API для 64-битной Windows
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND

user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

user32.GetKeyboardLayout.argtypes = [wintypes.DWORD]
user32.GetKeyboardLayout.restype = ctypes.c_void_p

user32.LoadKeyboardLayoutW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint]
user32.LoadKeyboardLayoutW.restype = ctypes.c_void_p

user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL

user32.GetKeyState.argtypes = [ctypes.c_int]
user32.GetKeyState.restype = ctypes.c_short

user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = ctypes.c_uint

kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


def get_foreground_window():
    """Возвращает HWND активного окна."""
    try:
        return user32.GetForegroundWindow()
    except Exception:
        return None


def get_window_layout(hwnd=None):
    """
    Возвращает HKL (идентификатор раскладки) активного окна как целое число.
    """
    try:
        if not hwnd:
            hwnd = get_foreground_window()
        if not hwnd:
            return 0
        tid = user32.GetWindowThreadProcessId(hwnd, None)
        hkl_ptr = user32.GetKeyboardLayout(tid)
        if hkl_ptr is None:
            return 0
        return int(hkl_ptr)
    except Exception:
        return 0


def get_active_process_name() -> str:
    """
    Возвращает имя исполняемого файла (.exe) активного окна.
    """
    try:
        hwnd = get_foreground_window()
        if not hwnd:
            return ""

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""

        h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not h_proc:
            return ""

        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value).lower()
        finally:
            kernel32.CloseHandle(h_proc)
    except Exception:
        pass
    return ""


def is_process_blacklisted(blacklist: list) -> bool:
    """Проверяет, входит ли текущее активное приложение в черный список."""
    if not blacklist:
        return False
    proc = get_active_process_name()
    if not proc:
        return False
    return proc in [p.lower() for p in blacklist]


def is_russian_layout(hwnd=None):
    """Проверяет, включена ли русская раскладка в активном окне."""
    hkl = get_window_layout(hwnd)
    if hkl:
        return (hkl & 0xFFFF) == LANG_RU
    return False


def is_english_layout(hwnd=None):
    """Проверяет, включена ли английская раскладка в активном окне."""
    hkl = get_window_layout(hwnd)
    if hkl:
        return (hkl & 0xFFFF) == LANG_EN
    return False


def switch_layout_to(target_lang: str, hwnd=None):
    """
    Переключает раскладку активного окна на 'ru' или 'en'.
    """
    try:
        if not hwnd:
            hwnd = get_foreground_window()
        if not hwnd:
            return

        if target_lang.lower() == "ru":
            hkl = user32.LoadKeyboardLayoutW("00000419", KLF_ACTIVATE)
        else:
            hkl = user32.LoadKeyboardLayoutW("00000409", KLF_ACTIVATE)

        user32.PostMessageW(hwnd, WM_INPUTLANGCHANGEREQUEST, 0, int(hkl) if hkl else 0)
    except Exception:
        pass


def toggle_layout(hwnd=None):
    """Переключает раскладку активного окна на противоположную."""
    try:
        if not hwnd:
            hwnd = get_foreground_window()
        if not hwnd:
            return
        user32.PostMessageW(hwnd, WM_INPUTLANGCHANGEREQUEST, 2, 0)
    except Exception:
        pass


def atomic_replace_text(backspaces: int, new_text: str, target_lang: str = None):
    """
    Атомарно удаляет backspaces символов и вводит new_text в ОДНОМ вызове SendInput.
    Гарантирует отсутствие гонок и задержек между удалением и вводом.
    """
    if target_lang:
        switch_layout_to(target_lang)

    total_events = (backspaces * 2) + (len(new_text) * 2)
    if total_events == 0:
        return 0

    inputs = (INPUT * total_events)()
    idx = 0

    # 1. Backspaces
    for _ in range(backspaces):
        inputs[idx].type = INPUT_KEYBOARD
        inputs[idx].ki.wVk = VK_BACK
        inputs[idx].ki.wScan = 0
        inputs[idx].ki.dwFlags = 0
        inputs[idx].ki.time = 0
        inputs[idx].ki.dwExtraInfo = 0
        idx += 1

        inputs[idx].type = INPUT_KEYBOARD
        inputs[idx].ki.wVk = VK_BACK
        inputs[idx].ki.wScan = 0
        inputs[idx].ki.dwFlags = KEYEVENTF_KEYUP
        inputs[idx].ki.time = 0
        inputs[idx].ki.dwExtraInfo = 0
        idx += 1

    # 2. Unicode символы нового текста (включая пробел или перенос строки)
    for ch in new_text:
        code = ord(ch)
        inputs[idx].type = INPUT_KEYBOARD
        inputs[idx].ki.wVk = 0
        inputs[idx].ki.wScan = code
        inputs[idx].ki.dwFlags = KEYEVENTF_UNICODE
        inputs[idx].ki.time = 0
        inputs[idx].ki.dwExtraInfo = 0
        idx += 1

        inputs[idx].type = INPUT_KEYBOARD
        inputs[idx].ki.wVk = 0
        inputs[idx].ki.wScan = code
        inputs[idx].ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
        inputs[idx].ki.time = 0
        inputs[idx].ki.dwExtraInfo = 0
        idx += 1

    return user32.SendInput(total_events, inputs, ctypes.sizeof(INPUT))


def send_backspaces(count: int):
    """Эмулирует нажатие клавиши Backspace указанное количество раз."""
    if count <= 0:
        return
    atomic_replace_text(backspaces=count, new_text="")


def send_unicode_text(text: str):
    """Эмулирует ввод строки в виде Unicode-символов."""
    if not text:
        return
    atomic_replace_text(backspaces=0, new_text=text)


# --- Работа с буфером обмена Windows ---
OpenClipboard = user32.OpenClipboard
OpenClipboard.argtypes = [wintypes.HWND]
OpenClipboard.restype = wintypes.BOOL

CloseClipboard = user32.CloseClipboard
CloseClipboard.argtypes = []
CloseClipboard.restype = wintypes.BOOL

EmptyClipboard = user32.EmptyClipboard
EmptyClipboard.argtypes = []
EmptyClipboard.restype = wintypes.BOOL

GetClipboardData = user32.GetClipboardData
GetClipboardData.argtypes = [ctypes.c_uint]
GetClipboardData.restype = ctypes.c_void_p

SetClipboardData = user32.SetClipboardData
SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
SetClipboardData.restype = ctypes.c_void_p

GlobalAlloc = kernel32.GlobalAlloc
GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
GlobalAlloc.restype = ctypes.c_void_p

GlobalLock = kernel32.GlobalLock
GlobalLock.argtypes = [ctypes.c_void_p]
GlobalLock.restype = ctypes.c_void_p

GlobalUnlock = kernel32.GlobalUnlock
GlobalUnlock.argtypes = [ctypes.c_void_p]
GlobalUnlock.restype = wintypes.BOOL

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def get_clipboard_text() -> str:
    """Считывает текстовое содержимое буфера обмена."""
    text = ""
    for _ in range(5):
        if OpenClipboard(None):
            try:
                handle = GetClipboardData(CF_UNICODETEXT)
                if handle:
                    ptr = GlobalLock(handle)
                    if ptr:
                        try:
                            text = ctypes.c_wchar_p(ptr).value or ""
                        finally:
                            GlobalUnlock(handle)
                break
            finally:
                CloseClipboard()
        time.sleep(0.02)
    return text


def set_clipboard_text(text: str):
    """Помещает строку в буфер обмена."""
    for _ in range(5):
        if OpenClipboard(None):
            try:
                EmptyClipboard()
                encoded = text.encode("utf-16-le") + b"\x00\x00"
                h_mem = GlobalAlloc(GMEM_MOVEABLE, len(encoded))
                if h_mem:
                    ptr = GlobalLock(h_mem)
                    if ptr:
                        ctypes.memmove(ptr, encoded, len(encoded))
                        GlobalUnlock(h_mem)
                        SetClipboardData(CF_UNICODETEXT, h_mem)
                break
            finally:
                CloseClipboard()
        time.sleep(0.02)


def copy_selection() -> str:
    """Эмулирует нажатие Ctrl+C и возвращает скопированный текст."""
    old_clipboard = get_clipboard_text()
    set_clipboard_text("")

    inputs = (INPUT * 4)()
    inputs[0].type = INPUT_KEYBOARD
    inputs[0].ki.wVk = VK_CONTROL
    inputs[1].type = INPUT_KEYBOARD
    inputs[1].ki.wVk = VK_C
    inputs[2].type = INPUT_KEYBOARD
    inputs[2].ki.wVk = VK_C
    inputs[2].ki.dwFlags = KEYEVENTF_KEYUP
    inputs[3].type = INPUT_KEYBOARD
    inputs[3].ki.wVk = VK_CONTROL
    inputs[3].ki.dwFlags = KEYEVENTF_KEYUP

    user32.SendInput(4, inputs, ctypes.sizeof(INPUT))
    time.sleep(0.06)

    copied = get_clipboard_text()
    if not copied:
        set_clipboard_text(old_clipboard)
        return ""
    return copied


def paste_text(text: str):
    """Помещает текст в буфер и эмулирует нажатие Ctrl+V."""
    set_clipboard_text(text)
    time.sleep(0.02)

    inputs = (INPUT * 4)()
    inputs[0].type = INPUT_KEYBOARD
    inputs[0].ki.wVk = VK_CONTROL
    inputs[1].type = INPUT_KEYBOARD
    inputs[1].ki.wVk = VK_V
    inputs[2].type = INPUT_KEYBOARD
    inputs[2].ki.wVk = VK_V
    inputs[2].ki.dwFlags = KEYEVENTF_KEYUP
    inputs[3].type = INPUT_KEYBOARD
    inputs[3].ki.wVk = VK_CONTROL
    inputs[3].ki.dwFlags = KEYEVENTF_KEYUP

    user32.SendInput(4, inputs, ctypes.sizeof(INPUT))


# --- Управление автозапуском через Windows Registry ---
REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_APP_NAME = "QWERTY_Switcher"


def is_autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, REG_APP_NAME)
            return True
    except (FileNotFoundError, OSError):
        return False


def set_autostart(enable: bool, command_path: str = None) -> bool:
    try:
        if enable:
            if not command_path:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                exe_path = os.path.join(base_dir, "dist", "QWERTY_Switcher.exe")
                vbs_path = os.path.join(base_dir, "run.vbs")

                if os.path.exists(exe_path):
                    command_path = f'"{exe_path}"'
                elif os.path.exists(vbs_path):
                    command_path = f'wscript.exe "{vbs_path}"'
                else:
                    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
                    if not os.path.exists(pythonw):
                        pythonw = sys.executable
                    main_py = os.path.join(base_dir, "main.py")
                    command_path = f'"{pythonw}" "{main_py}"'

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, REG_APP_NAME, 0, winreg.REG_SZ, command_path)
            return True
        else:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                try:
                    winreg.DeleteValue(key, REG_APP_NAME)
                except FileNotFoundError:
                    pass
            return True
    except Exception as e:
        print(f"Ошибка изменения автозапуска: {e}")
        return False
