from dataclasses import dataclass, field

from wallet.countries import resolve_currency
from wallet.money import format_home_rate, format_money, parse_amount, parse_strict_number
from wallet.service import CurrencyError, WalletService, _short

REPLY_MENU = [
    ["🆕 Создать путешествие", "🧳 Мои путешествия"],
    ["💰 Баланс", "📊 История расходов"],
    ["💱 Изменить курс"],
]

MENU_ACTIONS = {
    "🆕 Создать путешествие": "newtrip",
    "🧳 Мои путешествия": "switch",
    "💰 Баланс": "balance",
    "📊 История расходов": "history",
    "💱 Изменить курс": "setrate",
}

YES_NO_RATE = [[("✅ Да", "rate:yes"), ("❌ Нет", "rate:no")]]
YES_NO_EXPENSE = [[("✅ Да", "expense:yes"), ("❌ Нет", "expense:no")]]
SKIP_RECEIPT = [[("Без чека", "receipt:skip")]]
RECEIPT_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".gif"}


@dataclass
class Reply:
    text: str
    buttons: list[list[tuple[str, str]]] = field(default_factory=list)
    file_path: str | None = None
    reply_keyboard: bool = False


class App:
    """Диалог бота. Основное меню — нижняя клавиатура, не кнопки под каждым сообщением."""

    def __init__(self, service: WalletService):
        self.service = service

    def on_start(self, user_id: int, name: str = "") -> Reply:
        self.service.clear_dialog(user_id)
        who = name.strip()
        hello = f"Привет, {who}! 👋" if who else "Привет! 👋"
        reply = self._text(
            f"{hello}\n\n"
            "Я твой персональный помощник для управления финансами в путешествиях! 🌍💵\n\n"
            "Что я умею:\n"
            "• Создавать кошельки для разных стран\n"
            "• Конвертировать валюты по актуальным курсам\n"
            "• Отслеживать твои расходы\n"
            "• Показывать остаток в двух валютах\n\n"
            "Выбери действие в меню у поля ввода, рядом со смайликом."
        )
        reply.reply_keyboard = True
        return reply

    def on_command(self, user_id: int, command: str) -> Reply:
        if command == "newtrip":
            return self._begin_trip(user_id)
        if command != "setrate":
            self.service.clear_dialog(user_id)
        if command == "switch":
            return self._trips(user_id)
        if command == "balance":
            return self._text(self.service.balance_text(user_id))
        if command == "history":
            return self._history(user_id)
        if command == "setrate":
            return self._begin_setrate(user_id)
        return self._text("Такой команды нет. Выбери пункт меню.")

    def on_callback(self, user_id: int, data: str) -> Reply:
        if data == "menu:new":
            return self._begin_trip(user_id)
        if data == "menu:trips":
            self.service.clear_dialog(user_id)
            return self._trips(user_id)
        if data == "menu:balance":
            self.service.clear_dialog(user_id)
            return self._text(self.service.balance_text(user_id))
        if data == "menu:history":
            self.service.clear_dialog(user_id)
            return self._history(user_id)
        if data == "menu:setrate":
            return self._begin_setrate(user_id)
        if data == "rate:yes":
            return self._accept_rate(user_id)
        if data == "rate:no":
            return self._ask_manual_rate(user_id)
        if data == "expense:yes":
            return self._ask_expense_type(user_id)
        if data == "expense:no":
            return self._text(self.service.cancel_expense(user_id))
        if data == "receipt:skip":
            return self._finish_expense(user_id)
        if data.startswith("pickname:"):
            return self._pick_trip_name(user_id, data)
        if data == "hist:all":
            return self._history(user_id)
        if data.startswith("hist:"):
            return self._history_by_trip(user_id, data)
        if data.startswith("switch:"):
            try:
                trip_id = int(data.split(":", 1)[1])
            except ValueError:
                return self._text("Не понял, какое путешествие открыть.")
            return self._text(self.service.switch(user_id, trip_id))
        return self._text("Не понял кнопку. Откройте меню ещё раз.")

    def on_text(self, user_id: int, text: str) -> Reply:
        action = MENU_ACTIONS.get(text.strip())
        if action:
            return self.on_command(user_id, action)
        step, payload = self.service.dialog(user_id)
        if step == "trip_title":
            return self._take_trip_title(user_id, text, payload)
        if step == "expense_type":
            return self._save_expense_type(user_id, text)
        if step == "expense_receipt":
            return Reply(
                "Пришли фото или PDF чека либо нажми «Без чека».",
                buttons=SKIP_RECEIPT,
            )
        if step == "origin_country":
            return self._take_place(user_id, text, payload, "origin")
        if step == "dest_country":
            return self._take_place(user_id, text, payload, "dest")
        if step == "origin_code":
            return self._take_code(user_id, text, payload, "origin")
        if step == "dest_code":
            return self._take_code(user_id, text, payload, "dest")
        if step == "manual_rate":
            return self._take_manual_rate(user_id, text, payload)
        if step == "initial_amount":
            return self._take_initial_amount(user_id, text, payload)
        if step == "change_rate":
            return self._take_new_rate(user_id, text)
        amount = parse_amount(text)
        if amount is None:
            return self._text(
                "Напиши сумму расхода числом, например 100, или выбери пункт меню."
            )
        return self._preview(user_id, amount)

    def _begin_trip(self, user_id: int) -> Reply:
        self.service.set_dialog(user_id, "origin_country", {})
        return self._text("🗺 Из какой страны выезжаешь?")

    def _begin_setrate(self, user_id: int) -> Reply:
        trip_text = self.service.balance_text(user_id)
        if trip_text.startswith("Нет активного"):
            self.service.clear_dialog(user_id)
            return self._text(trip_text)
        self.service.set_dialog(user_id, "change_rate", {})
        return self._text(
            "💱 Введи новый курс: сколько единиц домашней валюты дают за 1 единицу валюты пребывания."
        )

    def _take_place(self, user_id: int, text: str, payload: dict, field: str) -> Reply:
        code = resolve_currency(text)
        payload[f"{field}_country"] = text.strip()
        if code is None:
            self.service.set_dialog(user_id, f"{field}_code", payload)
            return self._text(
                "Не знаю валюту этой страны. Введите код из трёх букв, например EUR."
            )
        payload[field] = code
        return self._after_place(user_id, payload, field)

    def _take_code(self, user_id: int, text: str, payload: dict, field: str) -> Reply:
        code = resolve_currency(text)
        if code is None or len(code) != 3:
            return self._text("Нужен код валюты из трёх букв, например USD.")
        payload[field] = code
        return self._after_place(user_id, payload, field)

    def _after_place(self, user_id: int, payload: dict, field: str) -> Reply:
        if field == "origin":
            self.service.set_dialog(user_id, "dest_country", payload)
            return self._text("В какую страну едешь?")
        return self._ask_trip_name(user_id, payload)

    def _ask_trip_name(self, user_id: int, payload: dict) -> Reply:
        self.service.set_dialog(user_id, "trip_title", payload)
        choices = self.service.name_choices(user_id)
        buttons = [[(_short(name), f"pickname:{trip_id}")] for trip_id, name in choices]
        hint = "Напиши новое название"
        if choices:
            hint += " или выбери из уже существующих."
        else:
            hint += "."
        return Reply(f"🏷 Как назвать поездку?\n{hint}", buttons=buttons)

    def _take_trip_title(self, user_id: int, text: str, payload: dict) -> Reply:
        title = text.strip()
        if not title:
            return self._ask_trip_name(user_id, payload)
        payload["title"] = title
        return self._offer_rate(user_id, payload)

    def _pick_trip_name(self, user_id: int, data: str) -> Reply:
        step, payload = self.service.dialog(user_id)
        if step != "trip_title":
            return self._text("Сначала укажи страны поездки.")
        try:
            trip_id = int(data.split(":", 1)[1])
        except ValueError:
            return self._text("Не понял название.")
        title = self.service.title_of(user_id, trip_id)
        if not title:
            return self._text("Такого названия нет.")
        payload["title"] = title
        return self._offer_rate(user_id, payload)

    def _offer_rate(self, user_id: int, payload: dict) -> Reply:
        try:
            rate = self.service.quote(payload["origin"], payload["dest"])
        except CurrencyError as exc:
            self.service.clear_dialog(user_id)
            return self._text(str(exc))
        payload["rate"] = rate
        self.service.set_dialog(user_id, "confirm_rate", payload)
        home = payload["origin"]
        dest = payload["dest"]
        same = ""
        if home == dest:
            same = f"Обе страны в одном валютном пространстве {home}.\n"
        shown = format_home_rate(rate)
        return Reply(
            f"{same}📈 Курс: 1 {home} = {shown} {dest}\n\nПодходит этот курс?",
            buttons=YES_NO_RATE,
        )

    def _accept_rate(self, user_id: int) -> Reply:
        step, payload = self.service.dialog(user_id)
        if step != "confirm_rate" or "rate" not in payload:
            return self._text("Сначала выберите страны путешествия.")
        self.service.set_dialog(user_id, "initial_amount", payload)
        return self._text(
            f"💵 Сколько денег берёшь с собой в {payload['origin']}? Напиши число."
        )

    def _ask_manual_rate(self, user_id: int) -> Reply:
        step, payload = self.service.dialog(user_id)
        if step != "confirm_rate":
            return self._text("Сначала запросите курс для нового путешествия.")
        self.service.set_dialog(user_id, "manual_rate", payload)
        return self._text(
            f"💱 Введи курс обменника: сколько {payload['origin']} дают за 1 {payload['dest']}."
        )

    def _take_manual_rate(self, user_id: int, text: str, payload: dict) -> Reply:
        rate = parse_strict_number(text)
        if rate is None or rate <= 0:
            return self._text("Введите курс числом больше нуля, например 12.5.")
        payload["rate"] = rate
        self.service.set_dialog(user_id, "initial_amount", payload)
        return self._text(
            f"💵 Сколько денег берёшь с собой в {payload['origin']}? Напиши число."
        )

    def _take_initial_amount(self, user_id: int, text: str, payload: dict) -> Reply:
        amount = parse_strict_number(text)
        if amount is None or amount <= 0:
            return self._text("Введите сумму числом больше нуля, например 15000.")
        trip = self.service.create_trip(
            user_id=user_id,
            origin_country=payload["origin_country"],
            dest_country=payload["dest_country"],
            home=payload["origin"],
            dest=payload["dest"],
            rate=payload["rate"],
            home_amount=amount,
            title=payload.get("title"),
        )
        return self._text(
            "✅ Путешествие создано!\n\n"
            f"🏷 {trip.get('title') or ''}\n"
            f"🗺 {trip['origin_country']} → {trip['dest_country']}\n"
            f"📈 Курс: 1 {trip['home_currency']} = {format_home_rate(trip['rate'])} {trip['dest_currency']}\n"
            f"🏠 Домашняя валюта: {format_money(trip['home_balance'])} {trip['home_currency']}\n"
            f"🌍 Валюта назначения: {format_money(trip['dest_balance'])} {trip['dest_currency']}\n\n"
            "Дальше присылай сумму расхода числом — посчитаю её в валюте пребывания."
        )

    def _take_new_rate(self, user_id: int, text: str) -> Reply:
        rate = parse_strict_number(text)
        if rate is None or rate <= 0:
            return self._text("Введите курс числом больше нуля, например 13.")
        return self._text(self.service.change_rate(user_id, rate))

    def _ask_expense_type(self, user_id: int) -> Reply:
        step, payload = self.service.dialog(user_id)
        if step != "expense_confirm":
            return self._text("Нет расхода, который нужно подтвердить.")
        self.service.set_dialog(user_id, "expense_type", payload)
        return self._text(
            "🏷 Напиши тип расхода: еда, транспорт, жильё или свой вариант."
        )

    def _save_expense_type(self, user_id: int, text: str) -> Reply:
        expense_type = text.strip()
        if not expense_type:
            return self._text("Напиши тип расхода словами, например: еда.")
        _step, payload = self.service.dialog(user_id)
        payload["expense_type"] = expense_type
        self.service.set_dialog(user_id, "expense_receipt", payload)
        return Reply(
            "📎 Пришли фото или PDF чека. Если чека нет, нажми «Без чека».",
            buttons=SKIP_RECEIPT,
        )

    def on_receipt(self, user_id: int, content: bytes, suffix: str) -> Reply:
        step, payload = self.service.dialog(user_id)
        if step != "expense_receipt":
            return self._text("Сначала пришли сумму расхода числом, потом можно приложить чек.")
        suffix = suffix.lower()
        if suffix not in RECEIPT_SUFFIXES or not content:
            return self.on_bad_receipt(user_id)
        path = self.service.save_receipt(user_id, content, suffix)
        return self._finish_expense(user_id, str(path), payload)

    def on_bad_receipt(self, user_id: int) -> Reply:
        step, _payload = self.service.dialog(user_id)
        if step != "expense_receipt":
            return self._text("Файл чека можно прислать, когда записываешь расход.")
        return Reply(
            "Нужны фото или PDF. Пришли другой файл или нажми «Без чека».",
            buttons=SKIP_RECEIPT,
        )

    def _finish_expense(
        self,
        user_id: int,
        receipt_path: str | None = None,
        payload: dict | None = None,
    ) -> Reply:
        if payload is None:
            step, payload = self.service.dialog(user_id)
            if step != "expense_receipt":
                return self._text("Нет расхода, к которому можно приложить чек.")
        return self._text(
            self.service.confirm_expense(
                user_id,
                payload.get("expense_type", ""),
                receipt_path,
            )
        )

    def _preview(self, user_id: int, amount: float) -> Reply:
        text, pending = self.service.preview_expense(user_id, amount)
        if not pending:
            return self._text(text)
        return Reply(text, buttons=YES_NO_EXPENSE)

    def _trips(self, user_id: int) -> Reply:
        text, switches = self.service.trips_overview(user_id)
        buttons = [[item] for item in switches]
        return Reply(text, buttons=buttons)

    def _history(self, user_id: int, title: str | None = None) -> Reply:
        text, path, filters = self.service.history(user_id, title)
        buttons = [[(label, data)] for label, data in filters]
        return Reply(text, buttons=buttons, file_path=str(path) if path else None)

    def _history_by_trip(self, user_id: int, data: str) -> Reply:
        try:
            trip_id = int(data.split(":", 1)[1])
        except ValueError:
            return self._text("Не понял, какую поездку показать.")
        title = self.service.title_of(user_id, trip_id)
        if not title:
            return self._text("Такой поездки нет.")
        return self._history(user_id, title)

    def _text(self, text: str) -> Reply:
        return Reply(text)
