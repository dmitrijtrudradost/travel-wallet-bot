from wallet.countries import resolve_currency


def test_country_names_and_codes():
    assert resolve_currency("Китай") == "CNY"
    assert resolve_currency("Россия") == "RUB"
    assert resolve_currency("США") == "USD"
    assert resolve_currency("eur") == "EUR"
    assert resolve_currency("Атлантида") is None


def test_yo_and_extra_spaces():
    assert resolve_currency("  Южная  Корея ") == "KRW"
