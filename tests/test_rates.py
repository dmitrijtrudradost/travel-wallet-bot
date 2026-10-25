from wallet.rates import LiveRateClient


def test_live_client_calls_current_api(monkeypatch):
    captured = {}

    def fake_get_current_rate(currencies):
        captured["currencies"] = currencies
        return {"quotes": {"USDEUR": 0.9}}

    monkeypatch.setattr("wallet.rates.get_current_rate", fake_get_current_rate)
    quotes = LiveRateClient().fetch_quotes(["EUR"])
    assert captured["currencies"] == ["EUR"]
    assert quotes["USDEUR"] == 0.9


def test_empty_currency_list_does_not_call_api(monkeypatch):
    def fail(currencies):
        raise AssertionError(currencies)

    monkeypatch.setattr("wallet.rates.get_current_rate", fail)
    assert LiveRateClient().fetch_quotes([]) == {}
