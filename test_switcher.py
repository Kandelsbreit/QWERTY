# -*- coding: utf-8 -*-
"""
test_switcher.py
Комплексные модульные тесты для QWERTY Switcher:
- Проверка полноты и обратимости таблицы маппинга
- Проверка сохранения пунктуации (. , ! ? ; : " ')
- Защита коротких 1-2 буквенных английских слов (a, i, is, it, at, to, by, if, no, we, he, be)
- Проверка эвристического определения языка ввода (1.5M слов)
- Проверка сохранения регистра текста
- Проверка работы с буфером обмена
- Проверка надежности конфигурационного менеджера и реестра
"""

import os
import sys
import unittest
import layout_mapper as lm
from config import ConfigManager, get_default_config_path
import win32_helper as w32


class TestLayoutMapper(unittest.TestCase):
    def test_bidirectional(self):
        """Проверка взаимно-однозначного соответствия раскладок."""
        en_phrase = "Hello World! How are you?"
        ru_converted = lm.convert_to_ru(en_phrase)
        en_restored = lm.convert_to_en(ru_converted)
        self.assertEqual(en_phrase, en_restored)

    def test_punctuation_mapping(self):
        """Проверка трансляции пунктуации."""
        self.assertEqual(lm.convert_to_ru("[]"), "хъ")
        self.assertEqual(lm.convert_to_en("хъ"), "[]")

    def test_punctuation_preservation(self):
        """Проверка сохранения знаков препинания при замене слов."""
        self.assertEqual(lm.convert_preserving_punctuation("ghbdtn,", to_ru=True), "привет,")
        self.assertEqual(lm.convert_preserving_punctuation("ghbdtn.", to_ru=True), "привет.")
        self.assertEqual(lm.convert_preserving_punctuation("ghbdtn!", to_ru=True), "привет!")
        self.assertEqual(lm.convert_preserving_punctuation("ghbdtn?", to_ru=True), "привет?")
        self.assertEqual(lm.convert_preserving_punctuation("руддщ,", to_ru=False), "hello,")
        self.assertEqual(lm.convert_preserving_punctuation("руддщ.", to_ru=False), "hello.")

    def test_en_short_words_protection(self):
        """Защита от ложного переключения коротких английских слов."""
        en_words = [
            "a", "i", "is", "it", "at", "to", "by", "or", "an", "as",
            "if", "no", "so", "do", "go", "my", "up", "we", "he", "me",
            "be", "us", "in", "on", "of", "ok", "hi"
        ]
        for w in en_words:
            self.assertFalse(lm.should_convert_en_to_ru(w), f"English word '{w}' was falsely converted to RU!")

    def test_ru_short_words_detection(self):
        """Проверка корректного распознавания коротких русских слов в EN раскладке."""
        ru_words = [
            "yt", "yf", "gj", "pf", "bp", "jn", "lj", "nj", "jy", "vs", "ds", "ns", "lf", "yj"
        ]
        for w in ru_words:
            self.assertTrue(lm.should_convert_en_to_ru(w), f"Russian word '{w}' in EN layout was not detected!")

    def test_en_to_ru_detection(self):
        """Проверка детекции ошибочной английской раскладки."""
        self.assertTrue(lm.should_convert_en_to_ru("ghbdtn")) # привет
        self.assertTrue(lm.should_convert_en_to_ru("rfr"))    # как
        self.assertTrue(lm.should_convert_en_to_ru("ltkf"))   # дела
        self.assertTrue(lm.should_convert_en_to_ru("ltkftim")) # делаешь
        self.assertTrue(lm.should_convert_en_to_ru("cvjnhb")) # смотри
        self.assertTrue(lm.should_convert_en_to_ru("kexit"))  # лучше
        self.assertTrue(lm.should_convert_en_to_ru("pyf."))   # знаю
        self.assertTrue(lm.should_convert_en_to_ru("xnj-nj")) # что-то

        # Нормальный английский
        self.assertFalse(lm.should_convert_en_to_ru("hello"))
        self.assertFalse(lm.should_convert_en_to_ru("world"))
        self.assertFalse(lm.should_convert_en_to_ru("const"))
        self.assertFalse(lm.should_convert_en_to_ru("function"))

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
        self.assertFalse(lm.should_convert_ru_to_en("делаешь."))

    def test_russian_word_not_converted_to_ru(self):
        """Русские слова со знаками препинания не должны ошибочно определяться как EN->RU."""
        self.assertFalse(lm.should_convert_en_to_ru("делаешь."))
        self.assertFalse(lm.should_convert_en_to_ru("привет."))
        self.assertFalse(lm.should_convert_en_to_ru("как дела?"))

    def test_case_toggle(self):
        """Проверка циклической смены регистра."""
        self.assertEqual(lm.toggle_case("ПРИВЕТ"), "привет")
        self.assertEqual(lm.toggle_case("привет"), "Привет")
        self.assertEqual(lm.toggle_case("Привет"), "ПРИВЕТ")

    def test_user_example(self):
        """Проверка изначального текста из запроса пользователя."""
        raw_msg = (
            "ns vj;tim yfgbcfnm kture. ghjuhfvve c fdnjpfgecrjv "
            "rjnjhfz dctulf dbcbn d nhtt b gthtrk.xftn hfccrkflre "
            "c heccrjuj yf fyukbqcrbq b yfj,jhjn tckb hfcrkflrf "
            "ytghfdbkmyfz& yfghbvth rfr ctqxfc f[f[ff"
        )
        converted = lm.convert_to_ru(raw_msg)
        self.assertTrue("ты можешь написать" in converted)
        self.assertTrue("автозапуском" in converted)
        self.assertTrue("переключает" in converted)

    def test_custom_and_excluded_words(self):
        """Проверка кастомных и исключенных слов."""
        custom = {"mytest": "мой_тест"}
        excluded = {"ghbdtn"}

        self.assertTrue(lm.should_convert_en_to_ru("mytest", custom_words=custom))
        self.assertFalse(lm.should_convert_en_to_ru("ghbdtn", excluded_words=excluded))


class TestConfigAndWin32(unittest.TestCase):
    def test_config_operations(self):
        """Проверка записи и чтения конфига."""
        test_path = "test_config_temp.json"
        try:
            cfg = ConfigManager(test_path)
            cfg.set("test_key", 12345)
            self.assertEqual(cfg.get("test_key"), 12345)

            # Проверка сниппетов
            expanded = cfg.expand_snippet("Date: {date}, Time: {time}")
            self.assertNotIn("{date}", expanded)
            self.assertNotIn("{time}", expanded)
        finally:
            if os.path.exists(test_path):
                os.remove(test_path)

    def test_persistent_config_path(self):
        """Проверка получения надежного пути конфигурации."""
        p = get_default_config_path()
        self.assertTrue(p.endswith("config.json"))

    def test_clipboard_operations(self):
        """Проверка чтения и записи буфера обмена."""
        orig = w32.get_clipboard_text()
        test_val = "QWERTY_SWITCHER_UNIT_TEST_123"
        w32.set_clipboard_text(test_val)
        read_val = w32.get_clipboard_text()
        self.assertEqual(test_val, read_val)
        w32.set_clipboard_text(orig)

    def test_blacklist_logic(self):
        """Проверка логики фильтрации черного списка."""
        self.assertFalse(w32.is_process_blacklisted([]))

    def test_autostart_toggle(self):
        """Проверка включения и отключения флага автозапуска."""
        was_enabled = w32.is_autostart_enabled()
        w32.set_autostart(False)
        self.assertFalse(w32.is_autostart_enabled())
        if was_enabled:
            w32.set_autostart(True)


if __name__ == "__main__":
    unittest.main()
