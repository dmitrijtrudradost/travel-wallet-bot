from current_api import get_current_rate


class LiveRateClient:
    """Единственный источник курсов: api.exchangerate.host через current_api.

    Запрос идёт на GET /live. Параметр source не передаётся: на тарифе базовая
    валюта всегда USD. Конвертацию /convert клиент не вызывает.
    """

    def fetch_quotes(self, currencies: list[str]) -> dict:
        if not currencies:
            return {}
        data = get_current_rate(currencies)
        return data["quotes"]
