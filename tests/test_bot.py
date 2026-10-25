import telebot

from wallet.app import App
from wallet.bot import (
    _document_suffix,
    build_markup,
    build_reply_keyboard,
    register_handlers,
)


class DummyService:
    pass


def test_markup_uses_callback_data():
    markup = build_markup([[("Баланс", "menu:balance")]])
    button = markup.keyboard[0][0]
    assert button.text == "Баланс"
    assert button.callback_data == "menu:balance"


def test_reply_keyboard_is_the_bottom_menu():
    markup = build_reply_keyboard()
    assert markup.keyboard[0][0]["text"] == "🆕 Создать путешествие"
    assert markup.keyboard[1][0]["text"] == "💰 Баланс"
    assert "callback_data" not in markup.keyboard[0][0]
    bot = telebot.TeleBot("123456:TEST", threaded=False)
    register_handlers(bot, App(DummyService()))
    assert bot.message_handlers
    assert bot.callback_query_handlers
    kinds = []
    for handler in bot.message_handlers:
        filters = handler.get("filters") or {}
        kinds.extend(filters.get("content_types") or [])
    assert "photo" in kinds
    assert "document" in kinds


def test_document_suffix_accepts_photo_and_pdf():
    class File:
        def __init__(self, file_name, mime_type):
            self.file_name = file_name
            self.mime_type = mime_type

    assert _document_suffix(File("check.PDF", "application/octet-stream")) == ".pdf"
    assert _document_suffix(File("scan.png", "image/png")) == ".png"
    assert _document_suffix(File("notes.txt", "text/plain")) is None
