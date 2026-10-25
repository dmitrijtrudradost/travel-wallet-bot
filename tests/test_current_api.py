import current_api


def test_convert_same_currency_without_quotes():
    assert current_api.convert_currency(100, "RUB", "RUB", {}) == 100


def test_convert_through_usd_quotes():
    quotes = {"USDRUB": 80, "USDCNY": 8}
    assert current_api.convert_currency(100, "CNY", "RUB", quotes) == 1000


def test_get_current_rate_uses_access_key_and_not_source(monkeypatch):
    monkeypatch.setattr(current_api, "API_KEY", "test-key")
    captured = {}

    class Response:
        def json(self):
            return {"success": True, "quotes": {"USDEUR": 0.9}}

    def fake_get(url, params, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(current_api.requests, "get", fake_get)
    data = current_api.get_current_rate(["EUR"])
    assert data["success"] is True
    assert captured["url"] == "https://api.exchangerate.host/live"
    assert captured["params"] == {"access_key": "test-key", "currencies": "EUR"}
    assert "source" not in captured["params"]


def test_get_current_rate_raises_on_api_error(monkeypatch):
    class Response:
        def json(self):
            return {"success": False, "error": {"type": "missing_access_key", "info": "нет ключа"}}

    monkeypatch.setattr(current_api.requests, "get", lambda *args, **kwargs: Response())
    try:
        current_api.get_current_rate(["EUR"])
    except RuntimeError as exc:
        assert exc.args[0]["type"] == "missing_access_key"
    else:
        raise AssertionError("ошибка API должна прерывать запрос")
