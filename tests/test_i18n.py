# -*- coding: utf-8 -*-
"""Тесты локализации."""

import pytest
from hvac import i18n


@pytest.fixture(autouse=True)
def reset_language():
    """Сбрасываем язык на RU после каждого теста."""
    yield
    i18n.set_language("ru")


class TestTranslations:
    def test_default_is_ru(self):
        i18n.set_language("ru")
        assert i18n.t("welcome.title") == "Добро пожаловать в HVAC Calculator"

    def test_switch_to_uz(self):
        i18n.set_language("uz")
        assert "xush kelibsiz" in i18n.t("welcome.title")

    def test_fallback_to_ru_if_uz_missing(self):
        # Добавим временный ключ только в RU
        i18n.TRANSLATIONS["ru"]["temp.only_ru"] = "Только русский"
        try:
            i18n.set_language("uz")
            assert i18n.t("temp.only_ru") == "Только русский"
        finally:
            del i18n.TRANSLATIONS["ru"]["temp.only_ru"]

    def test_unknown_key_returns_key(self):
        assert i18n.t("nonexistent.key") == "nonexistent.key"

    def test_unknown_key_returns_default(self):
        assert i18n.t("nonexistent.key", default="dflt") == "dflt"

    def test_set_invalid_language_falls_back(self):
        i18n.set_language("zh")
        assert i18n.get_language() == "ru"


class TestCompleteness:
    """Проверка, что все ключи RU есть и в UZ (и наоборот)."""

    def test_ru_uz_keys_match(self):
        ru_keys = set(i18n.TRANSLATIONS["ru"].keys())
        uz_keys = set(i18n.TRANSLATIONS["uz"].keys())
        only_ru = ru_keys - uz_keys
        only_uz = uz_keys - ru_keys
        assert not only_ru, f"Без UZ-перевода: {only_ru}"
        assert not only_uz, f"Лишние в UZ: {only_uz}"

    def test_no_empty_strings(self):
        for lang, mapping in i18n.TRANSLATIONS.items():
            for key, val in mapping.items():
                assert val, f"Пустой перевод {key} в {lang}"


class TestSupportedLanguages:
    def test_returns_dict(self):
        d = i18n.supported_languages_with_labels()
        assert "ru" in d
        assert "uz" in d


class TestKeyDomains:
    """Проверка, что ключевые домены покрыты."""

    @pytest.mark.parametrize("prefix", [
        "welcome.", "sidebar.", "topbar.", "menu.",
        "eng.", "btn.", "status.", "checklist.", "lang.",
    ])
    def test_domain_has_keys(self, prefix):
        keys = [k for k in i18n.TRANSLATIONS["ru"]
                if k.startswith(prefix)]
        assert keys, f"Домен {prefix} пуст"
