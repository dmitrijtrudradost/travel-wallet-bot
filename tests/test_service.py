from pathlib import Path

import pytest

from wallet.service import CurrencyError, WalletService
from wallet.storage import Storage


class FakeRates:
    def __init__(self, quotes):
        self.quotes = quotes
        self.calls = []

    def fetch_quotes(self, currencies):
        self.calls.append(list(currencies))
        missing = [code for code in currencies if f"USD{code}" not in self.quotes]
        if missing:
            raise RuntimeError({"type": "invalid_currency_codes", "info": "нет такой валюты"})
        return self.quotes


@pytest.fixture
def wallet(tmp_path: Path):
    rates = FakeRates({"USDRUB": 80, "USDCNY": 7.2, "USDEUR": 0.8})
    service = WalletService(Storage(tmp_path / "wallet.db"), rates, tmp_path)
    return service, rates


def test_quote_cny_in_rub_and_same_currency(wallet):
    service, rates = wallet
    rate = service.quote("RUB", "CNY")
    assert rate == pytest.approx(80 / 7.2)
    assert rates.calls == [["RUB", "CNY"]]

    rub = service.quote("RUB", "RUB")
    assert rub == 1
    assert rates.calls[-1] == ["RUB"]


def test_usd_is_not_requested_as_target(wallet):
    service, rates = wallet
    rate = service.quote("USD", "RUB")
    assert rate == pytest.approx(1 / 80)
    assert rates.calls == [["RUB"]]


def test_unknown_currency_is_friendly(wallet):
    service, _rates = wallet
    with pytest.raises(CurrencyError, match="Не удалось получить курс"):
        service.quote("RUB", "XXX")


def test_users_do_not_see_each_other(wallet):
    service, _rates = wallet
    service.quote("RUB", "RUB")
    service.create_trip(1, "Россия", "Россия", "RUB", "RUB", 1, 500)
    assert "Нет активного" in service.balance_text(2)
    assert service.switch(2, 1) == "Это путешествие не найдено."


def test_expense_uses_saved_rate_without_new_request(wallet):
    service, rates = wallet
    rate = service.quote("RUB", "CNY")
    calls_after_quote = len(rates.calls)
    trip = service.create_trip(1, "Россия", "Китай", "RUB", "CNY", rate, 8000)
    assert trip["dest_balance"] == pytest.approx(720)
    text, pending = service.preview_expense(1, 100)
    assert pending is not None
    assert "100.00 CNY = 1 111.11 RUB" in text
    saved = service.confirm_expense(1, "еда")
    assert "620.00 CNY" in saved
    assert "6 888.89 RUB" in saved
    assert len(rates.calls) == calls_after_quote

    history_text, path, _filters = service.history(1)
    assert path is not None
    assert "еда" in history_text
    assert Path(path).exists()


def test_change_rate_revalues_home_balance(wallet):
    service, _rates = wallet
    service.create_trip(1, "Россия", "Китай", "RUB", "CNY", 10, 1000)
    text = service.change_rate(1, 12)
    assert "Курс обновлён" in text
    assert "1 RUB = 0.0833 CNY" in text
    balance = service.balance_text(1)
    assert "100.00 CNY" in balance
    assert "1 200.00 RUB" in balance


def test_cancel_expense_keeps_balance(wallet):
    service, _rates = wallet
    service.create_trip(1, "Россия", "Россия", "RUB", "RUB", 1, 400)
    service.preview_expense(1, 50)
    assert service.cancel_expense(1) == "👌 Хорошо, расход не записал."
    assert "400.00 RUB" in service.balance_text(1)
