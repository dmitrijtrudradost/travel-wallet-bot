import logging
import os
from pathlib import Path

import telebot
from dotenv import load_dotenv
from telebot import types

from wallet.app import REPLY_MENU, App, Reply
from wallet.rates import LiveRateClient
from wallet.service import WalletService
from wallet.storage import Storage

ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger("wallet.bot")


def notify(text: str) -> None:
    """Короткая строка в консоль: запуск, остановка или тип ошибки."""
    print(text, flush=True)


def build_markup(buttons: list[list[tuple[str, str]]]) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    for row in buttons:
        markup.row(
            *[types.InlineKeyboardButton(text, callback_data=data) for text, data in row]
        )
    return markup


def build_reply_keyboard() -> types.ReplyKeyboardMarkup:
    """Нижнее меню. Скрывается кнопкой клавиатуры рядом со смайликом."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for row in REPLY_MENU:
        markup.row(*row)
    return markup


def deliver(bot: telebot.TeleBot, chat_id: int, reply: Reply) -> None:
    if reply.buttons:
        markup = build_markup(reply.buttons)
    elif reply.reply_keyboard:
        markup = build_reply_keyboard()
    else:
        markup = None
    bot.send_message(chat_id, reply.text, reply_markup=markup)
    if reply.file_path:
        with open(reply.file_path, "rb") as history_file:
            bot.send_document(chat_id, history_file)


def register_handlers(bot: telebot.TeleBot, app: App) -> None:
    @bot.message_handler(commands=["start"])
    def start(message):
        _safe(
            bot,
            message.chat.id,
            lambda: app.on_start(message.from_user.id, message.from_user.first_name or ""),
        )

    @bot.message_handler(commands=["newtrip", "switch", "balance", "history", "setrate"])
    def command(message):
        name = message.text.split()[0].split("@")[0][1:]
        _safe(bot, message.chat.id, lambda: app.on_command(message.from_user.id, name))

    @bot.message_handler(content_types=["text"])
    def text(message):
        _safe(bot, message.chat.id, lambda: app.on_text(message.from_user.id, message.text))

    @bot.message_handler(content_types=["photo"])
    def photo(message):
        file_id = message.photo[-1].file_id

        def action():
            content = _download(bot, file_id)
            return app.on_receipt(message.from_user.id, content, ".jpg")

        _safe(bot, message.chat.id, action)

    @bot.message_handler(content_types=["document"])
    def document(message):
        suffix = _document_suffix(message.document)

        def action():
            if suffix is None:
                return app.on_bad_receipt(message.from_user.id)
            content = _download(bot, message.document.file_id)
            return app.on_receipt(message.from_user.id, content, suffix)

        _safe(bot, message.chat.id, action)

    @bot.callback_query_handler(func=lambda call: True)
    def callback(call):
        bot.answer_callback_query(call.id)
        _safe(bot, call.message.chat.id, lambda: app.on_callback(call.from_user.id, call.data))


def _download(bot: telebot.TeleBot, file_id: str) -> bytes:
    info = bot.get_file(file_id)
    return bot.download_file(info.file_path)


def _document_suffix(document) -> str | None:
    name = (getattr(document, "file_name", None) or "").lower()
    suffix = Path(name).suffix
    mime = (getattr(document, "mime_type", None) or "").lower()
    if mime == "application/pdf" or suffix == ".pdf":
        return ".pdf"
    if mime.startswith("image/") or suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return suffix if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"} else ".jpg"
    return None


def _safe(bot: telebot.TeleBot, chat_id: int, action) -> None:
    try:
        deliver(bot, chat_id, action())
    except Exception as exc:
        notify(f"Ошибка {type(exc).__name__}: {exc}")
        logger.exception("Ошибка при обработке сообщения")
        try:
            bot.send_message(chat_id, "Что-то пошло не так. Попробуйте ещё раз или откройте меню.")
        except Exception as send_exc:
            notify(f"Ошибка {type(send_exc).__name__}: не удалось отправить ответ — {send_exc}")


def build_app(db_path: Path | None = None, history_dir: Path | None = None) -> App:
    data_dir = ROOT / "data"
    storage = Storage(db_path or data_dir / "wallet.db")
    service = WalletService(storage, LiveRateClient(), history_dir or data_dir)
    return App(service)


def main() -> None:
    load_dotenv(ROOT / ".env")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        notify("Ошибка: нет TELEGRAM_TOKEN в .env")
        raise SystemExit("Добавьте TELEGRAM_TOKEN в файл .env рядом с API_KEY_EXCHANGE.")
    bot = telebot.TeleBot(token)
    register_handlers(bot, build_app())
    started = False
    try:
        notify("Бот запущен. Ожидаю сообщения. Остановка: Ctrl+C")
        started = True
        bot.infinity_polling()
    except KeyboardInterrupt:
        notify("Ошибка KeyboardInterrupt: остановка с клавиатуры")
    except Exception as exc:
        notify(f"Ошибка {type(exc).__name__}: {exc}")
        raise
    finally:
        if started:
            notify("Бот остановлен")


if __name__ == "__main__":
    main()
