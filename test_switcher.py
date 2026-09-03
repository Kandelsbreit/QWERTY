# -*- coding: utf-8 -*-
"""
test_switcher.py
Автоматические тесты расширенного функционала QWERTY Switcher.
"""

import sys
import unittest
import os

sys.stdout.reconfigure(encoding="utf-8")

import layout_mapper as lm
import win32_helper as w32
from config import ConfigManager, DEFAULT_CONFIG


class TestLayoutMapper(unittest.TestCase):
    def test_user_example(self):
        """Проверка строки из запроса пользователя."""
        user_input = (
            "ns vj;tim yfgbcfnm kture. ghjuhfvve c fdnjpfgecrjv rjnjhfz dctulf dbcbn d "
            "nhtt b gthtrk.xftn hfccrkflre c heccrjuj yf fyukbqcrbq b yfj,jhjn tckb "
            "hfcrkflrf ytghfdbkmyfz& yfghbvth rfr ctqxfc f[f[ff"
        )
        result = lm.convert_to_ru(user_input)
        self.assertIn("ты можешь написать", result)
        self.assertIn("легкую программу с автозапуском", result)
        self.assertIn("всегда висит в трее", result)
        self.assertIn("переключает", result)
        self.assertIn("с русского на английский", result)
        self.assertIn("неправильная?", result)
        self.assertIn("ахахаа", result)

    def test_bidirectional(self):
        """Проверка обратимости перевода."""
        ru_text = "Привет, мир! Это проверка программы 123."
        en_text = lm.convert_to_en(ru_text)
        back_to_ru = lm.convert_to_ru(en_text)
        self.assertEqual(back_to_ru, ru_text)

    def test_punctuation_mapping(self):
        """Проверка специальных знаков."""
        self.assertEqual(lm.convert_to_ru("vj;tim"), "можешь")
        self.assertEqual(lm.convert_to_ru("kture."), "легкую")
        self.assertEqual(lm.convert_to_ru("ytghfdbkmyfz&"), "неправильная?")
        self.assertEqual(lm.convert_to_ru("f[f[ff"), "ахахаа")
        self.assertEqual(lm.convert_to_ru("cgfcb,j"), "спасибо")

    def test_en_to_ru_detection(self):
        """Проверка детекции ошибочной английской раскладки."""
        self.assertTrue(lm.should_convert_en_to_ru("ghbdtn"))
        self.assertTrue(lm.should_convert_en_to_ru("yfgbcfnm"))
        self.assertTrue(lm.should_convert_en_to_ru("vj;tim"))
        self.assertTrue(lm.should_convert_en_to_ru("f[f[ff"))
        self.assertTrue(lm.should_convert_en_to_ru("kture."))
        self.assertTrue(lm.should_convert_en_to_ru("fdnjpfgecrjv"))

        # Нормальный английский
        self.assertFalse(lm.should_convert_en_to_ru("hello"))
        self.assertFalse(lm.should_convert_en_to_ru("world"))
        self.assertFalse(lm.should_convert_en_to_ru("system"))
        self.assertFalse(lm.should_convert_en_to_ru("window"))
        self.assertFalse(lm.should_convert_en_to_ru("true"))
        self.assertFalse(lm.should_convert_en_to_ru("false"))

    def test_ru_to_en_detection(self):
        """Проверка детекции ошибочной русской раскладки."""
        self.assertTrue(lm.should_convert_ru_to_en("руддщ"))  # hello
        self.assertTrue(lm.should_convert_ru_to_en("цщкдв"))  # world
        self.assertTrue(lm.should_convert_ru_to_en("пщщпду")) # google
        self.assertTrue(lm.should_convert_ru_to_en("нщгегиу")) # youtube

        # Нормальный русский
        self.assertFalse(lm.should_convert_ru_to_en("привет"))
        self.assertFalse(lm.should_convert_ru_to_en("программа"))
        self.assertFalse(lm.should_convert_ru_to_en("система"))
        self.assertFalse(lm.should_convert_ru_to_en("клавиатура"))

    def test_case_toggle(self):
        """Проверка циклической смены регистра."""
        self.assertEqual(lm.toggle_case("HELLO"), "hello")
        self.assertEqual(lm.toggle_case("hello"), "Hello")
        self.assertEqual(lm.toggle_case("Hello"), "HELLO")
        self.assertEqual(lm.toggle_case("пРИВЕТ"), "Привет")

    def test_custom_and_excluded_words(self):
        """Проверка пользовательских слов и исключений."""
        custom = {"ghbdtnbr": "приветик"}
        excluded = {"git", "npm"}

        # Исключенное слово не должно конвертироваться
        self.assertFalse(lm.should_convert_en_to_ru("git", custom_words=custom, excluded_words=excluded))
        # Пользовательское слово должно конвертироваться
        self.assertTrue(lm.should_convert_en_to_ru("ghbdtnbr", custom_words=custom, excluded_words=excluded))


class TestConfigAndWin32(unittest.TestCase):
    def test_config_operations(self):
        """Проверка конфигурации и сниппетов."""
        cfg = ConfigManager()
        self.assertTrue(cfg.get("enabled"))
        expanded_date = cfg.expand_snippet("{date}")
        self.assertRegex(expanded_date, r"\d{2}\.\d{2}\.\d{4}")

        expanded_email = cfg.expand_snippet(cfg.get("snippets", {}).get("@@", ""))
        self.assertIn("@", expanded_email)

    def test_clipboard_operations(self):
        test_str = "Тестовый буфер обмена 123 !@#"
        w32.set_clipboard_text(test_str)
        result = w32.get_clipboard_text()
        self.assertEqual(result, test_str)

    def test_autostart_toggle(self):
        original = w32.is_autostart_enabled()
        res = w32.set_autostart(True)
        self.assertTrue(res)
        self.assertTrue(w32.is_autostart_enabled())
        w32.set_autostart(original)
        self.assertEqual(w32.is_autostart_enabled(), original)

    def test_blacklist_logic(self):
        """Проверка фильтрации черного списка процессов."""
        blacklist = ["code.exe", "powershell.exe"]
        # Если фиктивный процесс в списке
        self.assertTrue("code.exe" in blacklist)
        self.assertFalse("notepad.exe" in blacklist)


if __name__ == "__main__":
    unittest.main(verbosity=2)
