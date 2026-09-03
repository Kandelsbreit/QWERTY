# -*- coding: utf-8 -*-
"""
layout_mapper.py
Модуль трансляции символов между русской и английской раскладками,
эвристического определения языка ввода и преобразования регистра.
"""

import re

# Таблицы соответствия символов QWERTY <-> ЙЦУКЕН
EN_CHARS = "qwertyuiop[]asdfghjkl;'zxcvbnm,./`QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>?~@#$^&"
RU_CHARS = "йцукенгшщзхъфывапролджэячсмитьбю.ёЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,Ё\"№;:?"

EN_TO_RU_TABLE = str.maketrans(EN_CHARS, RU_CHARS)
RU_TO_EN_TABLE = str.maketrans(RU_CHARS, EN_CHARS)

RU_ALPHABET = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ")
EN_ALPHABET = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")

# Невозможные в русском языке начала слов
RU_INVALID_STARTS = ("ъ", "ь", "ы", "щк", "цщ", "жк", "йф", "кф", "нщ", "зщ", "гз", "дщ")

# Невозможные в русском языке сочетания букв
RU_IMPOSSIBLE_CLUSTERS = (
    "цщ", "щк", "ддщ", "пщщ", "тщ", "кщ", "зщ", "йй", "ьь", "ъъ", "ыы", "ыь", "ьы",
    "ъь", "ьъ", "щщк", "ццщ"
)

# Характерные начала русских слов в английской раскладке (невозможные в английском)
RU_STARTS_IN_EN = (
    "lt", "rt", "dl", "dn", "dm", "db", "dp", "dg", "tk", "tb", "vj", "vm", "vs", "vb", "vl",
    "bd", "bg", "bk", "fp", "fd", "fb", "jh", "jl", "jm", "jn", "jb", "jr", "js", "yf", "yg",
    "yk", "ym", "yn", "yr", "ys", "yt", "nj", "crf", "ctq", "dht", "vys", "xnj", "rfr", "rnj",
    "ult", "rulf", "gth", "ghj", "ghb", "gjl", "pf", "bp", "cg", "cb", "cj", "cv", "cn", "cl",
    "c;", "cy", "kex", "[j", "[e", "[f", "[b", "[h", "[k", "[v", "[y", "pyf", "cvj", "gjp",
    "ghf", "plj", "rhf", "rkf", "gjb", "gjl", "gjv", "gjr", "gjc", "gjt", "gjh"
)

# Характерные русские окончания в английской раскладке
RU_ENDS_IN_EN = (
    "tim", "bim", "nm", "nmcz", "ncz", "kb", "sq", "bq", "jq", "juj", "tuj", "jve", "tve",
    "s[", "b[", "jcnm", "tcnm", "cndj", "ybr", "xbr", "obr", "kf", "kj", "kb", "fnm", "znm",
    "bnm", "etn", "bnt", "trs", "bv", "tv"
)

# Невозможные в английском языке сочетания (n-grams)
EN_IMPOSSIBLE_NGRAMS = (
    "ghj", "yfg", "hcc", "dbc", "gth", "tck", "ytg", "vj;", "f[f", "ctq", "bcf",
    "rfk", "bcr", "xft", "yfj", "nht", "kfl", "rkf", "ghb", "gjh", "ytn",
    "djn", "rfr", "xtv", "xtuj", "rjulf", "njulf", "gjxtve", "pfxtv", "xnj",
    "dct", "e;t", "bkb", "ds", "vs", "jyb", "jyf", "jyb", "k/l", "pyf"
)

# Частые русские приставки
RU_PREFIXES = (
    "авто", "пере", "про", "на", "не", "рас", "раз", "под", "при", "пред",
    "от", "по", "за", "вы", "до", "со", "об", "из", "без", "над"
)

# Топ частых коротких русских слов в EN раскладке
COMMON_RU_WORDS_IN_EN = {
    "ns": "ты", "b": "и", "c": "с", "d": "в", "yf": "на", "yt": "не", "rfr": "как",
    "xnj": "что", "gj": "по", "pf": "за", "bp": "из", "jn": "от", "rjulf": "когда",
    "tckb": "если", "ghbdtn": "привет", "gjrf": "пока", "cgfcb,j": "спасибо",
    "lf": "да", "ytn": "нет", "jy": "он", "jyf": "она", "jyb": "они", "vs": "мы",
    "ds": "вы", "rnj": "кто", "ult": "где", "nfr": "так", "e;t": "уже", "djn": "вот",
    "xtv": "чем", "bkb": "или", "dct": "все", "vtyz": "меня", "nt,z": "тебя",
    "tuj": "его", "tt": "ее", "b[": "их", "yfvb": "нами", "dfvb": "вами",
    "ctqxfc": "сейчас", "ntgthm": "теперь", "nj;t": "тоже", "nfr;t": "также",
    "ghjcnj": "просто", "vj;yj": "можно", "yflj": "надо", "ye;yj": "нужно",
    "kturj": "легко", "kture": "легкую", "kture.": "легкую",
    "ghjuhfvve": "программу", "ghjuhfvvf": "программа",
    "fdnjpfgecr": "автозапуск", "fdnjpfgecrjv": "автозапуском", "rjnjhfz": "которая",
    "dctulf": "всегда", "dbcbn": "висит", "nhtt": "трее", "gthtrk.xftn": "переключает",
    "hfccrkflre": "раскладку", "hfcrkflrf": "раскладка", "heccrjuj": "русского",
    "fyukbqcrbq": "английский", "yfj,jhjn": "наоборот", "ytghfdbkmyfz": "неправильная",
    "yfghbvth": "например", "f[f[ff": "ахахаа", "f[f[f": "ахаха", "f[f": "аха",
    "vj;tim": "можешь", "yfgbcfnm": "написать", "ltkf": "дела", "ltkftim": "делаешь",
    "ltkfk": "делал", "ltkfnm": "делать", "crfpfnm": "сказать", "crfpfk": "сказал",
    "pyf/": "знаю", "pyftim": "знаешь", "cvjnhb": "смотри", "kexit": "лучше",
    "rjhjxt": "короче", "pljhjdj": "здорово", "rhfcbdj": "красиво", "ghbrjk": "прикол"
}

# Топ частых английских слов в RU раскладке
COMMON_EN_WORDS_IN_RU = {
    "руддщ": "hello", "цщкдв": "world", "пщщпду": "google", "нщгегиу": "youtube",
    "пшеакь": "github", "еуые": "test", "гыук": "user", "зфыыцщкв": "password",
    "ыудусе": "select", "гзивфеу": "update", "вудуеу": "delete", "акщь": "from",
    "црукь": "where", "шьзщке": "import", "узищке": "export", "агтсешщт": "function",
    "сщтые": "const", "дуе": "let", "мфк": "var", "сдфыы": "class", "куегкт": "return",
    "екгу": "true", "афдыу": "false", "тгдд": "null", "гтвуаштув": "undefined",
    "ершы": "this", "еру": "the", "фтв": "and", "ащк": "for", "фку": "are",
    "иге": "but", "тще": "not", "нщг": "you", "фдд": "all", "фтн": "any",
    "сфт": "can", "рфв": "had", "рук": "her", "цфы": "was", "щту": "one",
    "щгк": "our", "щге": "out", "вфн": "day", "пуе": "get", "рфы": "has",
    "ршь": "him", "ршы": "his", "рщц": "how", "ьфт": "man", "туц": "new",
    "тщц": "now", "щдв": "old", "ыеу": "see", "ецщ": "two", "цфн": "way",
    "црщ": "who", "ищн": "boy", "вшв": "did", "шеы": "its",
    "згс": "put", "ыфн": "say", "ырк": "she", "ещщ": "too", "гыу": "use",
    "ящщь": "zoom", "срфе": "chat", "ьфшд": "mail", "дштл": "link", "ышеу": "site",
    "зщые": "post", "туцы": "news", "рщьу": "home", "ашду": "file", "мшуц": "view",
    "щзут": "open", "ыфму": "save", "удщыу": "close", "уякше": "exit", "рудз": "help"
}


def convert_to_ru(text: str) -> str:
    """Конвертирует текст из английской раскладки в русскую."""
    return text.translate(EN_TO_RU_TABLE)


def convert_to_en(text: str) -> str:
    """Конвертирует текст из русской раскладки в английскую."""
    return text.translate(RU_TO_EN_TABLE)


def convert_auto(text: str) -> str:
    """
    Автоматически определяет исходный язык строки и конвертирует в противоположный.
    """
    ru_count = sum(1 for ch in text if ch in RU_ALPHABET)
    en_count = sum(1 for ch in text if ch in EN_ALPHABET)

    if ru_count > en_count:
        return convert_to_en(text)
    else:
        return convert_to_ru(text)


def toggle_case(text: str) -> str:
    """
    Циклически переключает регистр текста:
    ВСЕ ЗАГЛАВНЫЕ -> все строчные -> Как В Заголовке -> ВСЕ ЗАГЛАВНЫЕ
    """
    if not text:
        return text

    if text.isupper():
        return text.lower()
    elif text.islower():
        return text.title()
    elif text.istitle():
        return text.upper()
    else:
        return text.swapcase()


def is_url_or_code(text: str) -> bool:
    """Проверяет, не является ли текст URL, кодом, путем к файлу или тегом."""
    lower = text.lower()
    if lower.startswith(("http://", "https://", "www.", "ftp://", "file://", "c:\\", "d:\\")):
        return True
    if re.search(r"(\.com|\.ru|\.net|\.org|\.io|\.dev|\.html|\.js|\.py)$", lower):
        return True
    if re.search(r"[<>{}\$#\\/\|\^~=`]", text) and not any(ch in "[];',." for ch in text):
        return True
    return False


def should_convert_en_to_ru(word: str, custom_words=None, excluded_words=None) -> bool:
    """
    Определяет, было ли слово ошибочно набрано в английской раскладке вместо русской.
    """
    clean_word = word.strip().rstrip(".,!?;:\"'")
    if not clean_word or len(clean_word) < 1:
        return False

    lower = clean_word.lower()

    if excluded_words and lower in excluded_words:
        return False

    if custom_words and lower in custom_words:
        return True

    if is_url_or_code(clean_word):
        return False

    # Прямой словарный хит
    if lower in COMMON_RU_WORDS_IN_EN:
        return True

    # 1. Наличие русских пунктуационных букв в английской раскладке: [ ] ; ' ,
    if any(ch in "[];'" for ch in lower):
        if any(ch in EN_ALPHABET for ch in lower):
            return True

    # 2. Невозможные в английском сочетания согласных/букв
    for ngram in EN_IMPOSSIBLE_NGRAMS:
        if ngram in lower:
            return True

    # 3. Характерные начала и окончания русских слов
    if lower.startswith(RU_STARTS_IN_EN):
        return True

    if lower.endswith(RU_ENDS_IN_EN):
        return True

    # 4. Проверка транслированного слова на соответствие русским паттернам
    ru_candidate = convert_to_ru(lower)

    if ru_candidate.startswith(RU_INVALID_STARTS):
        return False

    if len(ru_candidate) >= 4:
        for prefix in RU_PREFIXES:
            if ru_candidate.startswith(prefix):
                return True

    if len(ru_candidate) >= 4:
        if ru_candidate.endswith((
            "ать", "ять", "ить", "еть", "уть", "овать", "евать",
            "ться", "тся", "ный", "ная", "ное", "ные", "ского",
            "скому", "ском", "ских", "ский", "ская", "ское"
        )):
            return True

    return False


def should_convert_ru_to_en(word: str, custom_words=None, excluded_words=None) -> bool:
    """
    Определяет, было ли слово ошибочно набрано в русской раскладке вместо английской.
    """
    clean_word = word.strip().rstrip(".,!?;:\"'")
    if not clean_word or len(clean_word) < 1:
        return False

    lower = clean_word.lower()

    if excluded_words and lower in excluded_words:
        return False

    if custom_words and lower in custom_words:
        return True

    if lower in COMMON_EN_WORDS_IN_RU:
        return True

    # 1. Невозможные русские начала слов (ъ, ь, ы, щк, цщ...)
    if lower.startswith(RU_INVALID_STARTS):
        return True

    # 2. Невозможные в русском сочетания букв
    for cluster in RU_IMPOSSIBLE_CLUSTERS:
        if cluster in lower:
            return True

    # 3. 5 или более согласных подряд в русском
    vowels = set("аеёиоуыэюя")
    consonant_count = 0
    for ch in lower:
        if ch in RU_ALPHABET:
            if ch not in vowels:
                consonant_count += 1
                if consonant_count >= 5:
                    return True
            else:
                consonant_count = 0

    return False
