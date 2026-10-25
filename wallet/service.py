from datetime import datetime
from pathlib import Path

from current_api import convert_currency

from wallet.export_xlsx import write_history
from wallet.money import format_home_rate, format_money
from wallet.storage import Storage


class CurrencyError(Exception):
    """Валюта не нашлась или api.exchangerate.host ответил ошибкой."""


class WalletService:
    """Путешествия, балансы и расходы. Курс запрашивается один раз при создании."""

    def __init__(self, storage: Storage, rates, history_dir: Path):
        self.storage = storage
        self.rates = rates
        self.history_dir = Path(history_dir)

    def dialog(self, user_id: int) -> tuple[str, dict]:
        return self.storage.get_dialog(user_id)

    def set_dialog(self, user_id: int, step: str, payload: dict | None = None) -> None:
        self.storage.set_dialog(user_id, step, payload)

    def clear_dialog(self, user_id: int) -> None:
        self.storage.clear_dialog(user_id)

    def quote(self, home: str, dest: str) -> float:
        """Сколько единиц домашней валюты дают за 1 единицу валюты пребывания.

        Одинаковые валюты, в том числе RUB в RUB, дают курс 1.
        Доллары не запрашиваются отдельно: в ответе /live источник и так USD.
        """
        if home == dest:
            self._ensure_known(home)
            return 1.0
        codes = []
        for code in (home, dest):
            if code != "USD" and code not in codes:
                codes.append(code)
        try:
            quotes = self.rates.fetch_quotes(codes)
        except RuntimeError as exc:
            raise CurrencyError(_api_message(exc)) from exc
        try:
            return float(convert_currency(1, dest, home, quotes))
        except KeyError:
            raise CurrencyError(
                f"Валюта {home} или {dest} недоступна в api.exchangerate.host."
            ) from None

    def create_trip(
        self,
        user_id: int,
        origin_country: str,
        dest_country: str,
        home: str,
        dest: str,
        rate: float,
        home_amount: float,
        title: str | None = None,
    ) -> dict:
        dest_amount = round(home_amount / rate, 2)
        trip_title = (title or "").strip() or f"{origin_country} → {dest_country}"
        trip_id = self.storage.create_trip(
            user_id=user_id,
            origin_country=origin_country,
            dest_country=dest_country,
            home_currency=home,
            dest_currency=dest,
            rate=rate,
            home_balance=round(home_amount, 2),
            dest_balance=dest_amount,
            initial_home=round(home_amount, 2),
            title=trip_title,
            created_at=_now(),
        )
        self.clear_dialog(user_id)
        trip = self.storage.get_trip(user_id, trip_id)
        assert trip is not None
        return trip

    def name_choices(self, user_id: int) -> list[tuple[int, str]]:
        return self.storage.name_choices(user_id)

    def title_of(self, user_id: int, trip_id: int) -> str | None:
        trip = self.storage.get_trip(user_id, trip_id)
        if trip is None:
            return None
        return _title(trip)

    def trips_overview(self, user_id: int) -> tuple[str, list[tuple[str, str]]]:
        trips = self.storage.list_trips(user_id)
        if not trips:
            return "🧳 Путешествий пока нет. Создай первое.", []
        lines = ["🧳 Мои путешествия:\n"]
        buttons = []
        for trip in trips:
            mark = " ✅" if trip["is_active"] else ""
            lines.append(f"🏷 {_title(trip)}{mark}\n🗺 {_route(trip)}")
            buttons.append((f"🧳 {_short(_title(trip))}", f"switch:{trip['id']}"))
        return "\n".join(lines), buttons

    def switch(self, user_id: int, trip_id: int) -> str:
        if not self.storage.set_active(user_id, trip_id):
            return "Это путешествие не найдено."
        self.clear_dialog(user_id)
        trip = self.storage.get_trip(user_id, trip_id)
        assert trip is not None
        return f"✅ Выбрано путешествие.\n\n{_balance_card(trip)}"

    def balance_text(self, user_id: int) -> str:
        trip = self.storage.active_trip(user_id)
        if trip is None:
            return "Нет активного путешествия. Создай его или выбери в «Мои путешествия»."
        return _balance_card(trip)

    def preview_expense(self, user_id: int, amount: float) -> tuple[str, dict | None]:
        if amount <= 0:
            return "Сумма должна быть больше нуля.", None
        trip = self.storage.active_trip(user_id)
        if trip is None:
            return "Сначала создай путешествие или выбери его в «Мои путешествия».", None
        amount_dest = round(amount, 2)
        amount_home = round(amount_dest * trip["rate"], 2)
        self.set_dialog(
            user_id,
            "expense_confirm",
            {
                "trip_id": trip["id"],
                "amount_dest": amount_dest,
                "amount_home": amount_home,
            },
        )
        text = (
            f"💸 {format_money(amount_dest)} {trip['dest_currency']} = "
            f"{format_money(amount_home)} {trip['home_currency']}\n\n"
            "Учесть как расход?"
        )
        return text, {"trip_id": trip["id"]}

    def save_receipt(self, user_id: int, content: bytes, suffix: str) -> Path:
        folder = self.history_dir / "receipts" / str(user_id)
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = folder / f"{stamp}{suffix}"
        number = 1
        while path.exists():
            path = folder / f"{stamp}_{number}{suffix}"
            number += 1
        path.write_bytes(content)
        return path.resolve()

    def confirm_expense(
        self,
        user_id: int,
        expense_type: str,
        receipt_path: str | None = None,
    ) -> str:
        step, payload = self.dialog(user_id)
        if step not in ("expense_confirm", "expense_type", "expense_receipt"):
            return "Нет расхода, который нужно подтвердить."
        expense_type = expense_type.strip()
        if not expense_type:
            return "Напиши тип расхода."
        trip = self.storage.get_trip(user_id, int(payload["trip_id"]))
        if trip is None:
            self.clear_dialog(user_id)
            return "Путешествие не найдено."
        new_dest = round(trip["dest_balance"] - payload["amount_dest"], 2)
        new_home = round(trip["home_balance"] - payload["amount_home"], 2)
        saved = self.storage.apply_expense(
            user_id=user_id,
            trip_id=trip["id"],
            amount_dest=payload["amount_dest"],
            amount_home=payload["amount_home"],
            expense_type=expense_type,
            created_at=_now(),
            new_dest=new_dest,
            new_home=new_home,
            receipt_path=receipt_path,
        )
        self.clear_dialog(user_id)
        if not saved:
            return "Не удалось записать расход."
        updated = self.storage.get_trip(user_id, trip["id"])
        assert updated is not None
        self._write_history(user_id)
        note = "\n\n⚠️ Баланс ушёл в минус." if new_dest < 0 or new_home < 0 else ""
        attached = "\n📎 Чек сохранён." if receipt_path else ""
        return f"✅ Расход записан: {expense_type}.{attached}\n\n{_balance_card(updated)}{note}"

    def cancel_expense(self, user_id: int) -> str:
        self.clear_dialog(user_id)
        return "👌 Хорошо, расход не записал."

    def change_rate(self, user_id: int, rate: float) -> str:
        if rate <= 0:
            return "Курс должен быть больше нуля."
        trip = self.storage.active_trip(user_id)
        if trip is None:
            return "Нет активного путешествия."
        # Наличные в валюте пребывания не меняются, пересчитывается домашний эквивалент.
        home_balance = round(trip["dest_balance"] * rate, 2)
        self.storage.update_balances_and_rate(
            user_id, trip["id"], rate, home_balance, trip["dest_balance"]
        )
        self.clear_dialog(user_id)
        updated = self.storage.get_trip(user_id, trip["id"])
        assert updated is not None
        return (
            "✅ Курс обновлён!\n\n"
            f"🗺 {_title(updated)} · {_route(updated)}\n"
            f"📈 Новый курс: {_rate_line(updated)}"
        )

    def history(self, user_id: int, title: str | None = None) -> tuple[str, Path | None, list[tuple[str, str]]]:
        rows = self.storage.expenses(user_id, title)
        filters = [("Все поездки", "hist:all")]
        filters.extend(
            (_short(name), f"hist:{trip_id}") for trip_id, name in self.storage.name_choices(user_id)
        )
        if not rows:
            empty = "📊 Расходов пока нет." if not title else f"📊 По поездке «{title}» расходов нет."
            return empty, None, filters if len(filters) > 1 else []
        path = self._write_history(user_id, title)
        lines = []
        for row in rows[:10]:
            moment = datetime.fromisoformat(row["created_at"])
            lines.append(
                f"{moment.strftime('%d.%m.%Y')} {moment.strftime('%H:%M')} · "
                f"🏷 {_title(row)} · "
                f"{row['expense_type']} · "
                f"{format_money(row['amount_dest'])} {row['dest_currency']} = "
                f"{format_money(row['amount_home'])} {row['home_currency']}"
            )
        header = "📊 Последние расходы"
        if title:
            header += f" · {title}"
        text = header + ":\n" + "\n".join(lines) + "\n\nФайл истории прикреплён."
        return text, path, filters if len(filters) > 1 else []

    def _write_history(self, user_id: int, title: str | None = None) -> Path:
        rows = []
        selected = self.storage.expenses(user_id, title)
        selected.sort(key=lambda row: (_title(row).casefold(), row["created_at"]))
        for row in selected:
            moment = datetime.fromisoformat(row["created_at"])
            rows.append(
                [
                    moment.strftime("%d.%m.%Y"),
                    moment.strftime("%H:%M"),
                    row["expense_type"],
                    _title(row),
                    _route(row),
                    row["amount_dest"],
                    row["dest_currency"],
                    row["amount_home"],
                    row["home_currency"],
                    row.get("receipt_path") or "",
                ]
            )
        return write_history(self.history_dir / f"history_{user_id}.xlsx", rows)

    def _ensure_known(self, code: str) -> None:
        if code == "USD":
            return
        try:
            quotes = self.rates.fetch_quotes([code])
        except RuntimeError as exc:
            raise CurrencyError(_api_message(exc)) from exc
        if f"USD{code}" not in quotes:
            raise CurrencyError(f"Валюта {code} недоступна в api.exchangerate.host.")


def _route(trip: dict) -> str:
    return f"{trip['origin_country']} → {trip['dest_country']}"


def _title(trip: dict) -> str:
    name = (trip.get("title") or "").strip()
    return name or _route(trip)


def _short(text: str, limit: int = 32) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _rate_line(trip: dict) -> str:
    return (
        f"1 {trip['home_currency']} = {format_home_rate(trip['rate'])} {trip['dest_currency']}"
    )


def _balance_card(trip: dict) -> str:
    initial = trip.get("initial_home")
    if initial is None:
        initial = trip["home_balance"]
    return (
        f"💰 Баланс путешествия: {_title(trip)}\n"
        f"🗺 {_route(trip)}\n\n"
        f"🏠 Домашняя валюта: {format_money(trip['home_balance'])} {trip['home_currency']}\n"
        f"🌍 Валюта назначения: {format_money(trip['dest_balance'])} {trip['dest_currency']}\n\n"
        f"📈 Курс: {_rate_line(trip)}\n"
        f"💵 Начальная сумма: {format_money(initial)} {trip['home_currency']}"
    )


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _api_message(exc: RuntimeError) -> str:
    detail = exc.args[0] if exc.args else "ошибка запроса"
    if isinstance(detail, dict):
        detail = detail.get("info") or detail.get("type") or "ошибка запроса"
    return f"Не удалось получить курс: {detail}"
