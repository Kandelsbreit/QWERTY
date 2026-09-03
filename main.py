# -*- coding: utf-8 -*-
"""
main.py
Главная точка входа в программу QWERTY Switcher.
- Проверяет единственный экземпляр через именованный мьютекс Windows.
- Загружает конфигурацию.
- Запускает перехватчик клавиатуры.
- Запускает иконку и меню в системном трее.
"""

import sys
import ctypes
from ctypes import wintypes
from config import ConfigManager
from keyboard_hook import KeyboardHookManager
from tray_app import TrayApplication

kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32

MUTEX_NAME = "Local\\QWERTY_Switcher_Single_Instance_Mutex"
ERROR_ALREADY_EXISTS = 183

# Строгая 64-битная типизация системных функций
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, ctypes.c_wchar_p]
kernel32.CreateMutexW.restype = wintypes.HANDLE

kernel32.GetLastError.argtypes = []
kernel32.GetLastError.restype = wintypes.DWORD

user32.MessageBoxW.argtypes = [wintypes.HWND, ctypes.c_wchar_p, ctypes.c_wchar_p, wintypes.UINT]
user32.MessageBoxW.restype = ctypes.c_int


def ensure_single_instance():
    """Гарантирует, что запущен только один экземпляр программы."""
    mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        user32.MessageBoxW(
            0,
            "Программа QWERTY Switcher уже запущена и находится в системном трее (возле часов).",
            "QWERTY Switcher",
            0x40 | 0x10000
        )
        sys.exit(0)
    return mutex


def main():
    mutex = ensure_single_instance()

    try:
        # Инициализируем конфигурацию
        cfg_mgr = ConfigManager()

        # Инициализируем и запускаем хук клавиатуры
        hook_mgr = KeyboardHookManager(cfg_mgr)
        hook_mgr.start()

        # Инициализируем и запускаем приложение трея (основной цикл)
        app = TrayApplication(hook_mgr)
        app.run()
    finally:
        if mutex:
            kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    main()
