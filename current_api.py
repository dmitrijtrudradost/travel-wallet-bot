# os нужен, чтобы прочитать ключ из переменных окружения, а не хранить его в коде.
import os

# requests отправляет HTTP-запрос к API и возвращает ответ.
import requests

# load_dotenv подхватывает пары «имя=значение» из файла .env в окружение процесса.
from dotenv import load_dotenv

# Без этого вызова os.getenv не увидит переменные из .env.
load_dotenv()

# Ключ лежит в .env под именем API_KEY_EXCHANGE.
# В запрос он попадёт как query-параметр access_key. Если ключа нет, API_KEY будет None,
# и сервер ответит success: false с ошибкой missing_access_key или invalid_access_key.
API_KEY = os.getenv("API_KEY_EXCHANGE")


def get_current_rate(currencies: list[str] | None = None):
    if currencies is None:
        currencies = ["EUR", "GBP", "RUB"]

    # /live отдаёт последний доступный курс. На этом тарифе он обновляется раз в сутки.
    url = "https://api.exchangerate.host/live"

    # access_key обязателен на каждом запросе.
    # currencies API ждёт одной строкой через запятую, поэтому список склеивается.
    # source, spread, format и callback намеренно не передаются.
    params = {
        "access_key": API_KEY,
        "currencies": ",".join(currencies),
    }

    # timeout не даёт запросу висеть бесконечно, если сервер не отвечает.
    # params requests сам допишет к URL как ?access_key=...&currencies=EUR,GBP,RUB
    response = requests.get(url, params=params, timeout=30)

    # Тело ответа — JSON. При ошибке API часто всё равно отдаёт HTTP 200,
    # но без quotes: success равен false, текст лежит в error.
    data = response.json()
    if not data.get("success"):
        raise RuntimeError(data.get("error"))
    return data


def convert_currency(amount, from_currency, to_currency, quotes):
    """Считает сумму по курсам из quotes, без запроса к /convert: его нет в тарифе.

    quotes — словарь пар к доллару: USDEUR, USDRUB и так далее.
    Значение — сколько единиц валюты дают за 1 USD.
    Сумма в целевой валюте = amount * (USD→цель) / (USD→источник).
    Для самого доллара курс равен 1. Одинаковые валюты (RUB в RUB) не требуют quotes.
    """
    if from_currency == to_currency:
        return float(amount)

    def per_usd(code):
        if code == "USD":
            return 1
        key = f"USD{code}"
        if key not in quotes:
            raise KeyError(f"В quotes нет пары {key}. Добавьте {code} в currencies.")
        return quotes[key]

    return amount * per_usd(to_currency) / per_usd(from_currency)


# Этот блок выполняется только при прямом запуске файла: python current_api.py.
# При импорте функции из другого модуля запрос сам не уйдёт.
# Один запрос: второй подряд вызов /live на этом тарифе часто упирается в лимит.
if __name__ == "__main__":
    data = get_current_rate(currencies=["EUR", "GBP", "CNY", "RUB"])
    quotes = data["quotes"]
    # USDRUB — сколько рублей дают за 1 доллар. Остальные курсы к рублю
    # считаются через доллар: рубли за доллар разделить на валюту за доллар.
    rub_per_usd = quotes["USDRUB"]

    print(
        "Курсы к RUB на сегодня:\n"
        f"  USD: {rub_per_usd}\n"
        f"  EUR: {rub_per_usd / quotes['USDEUR']}\n"
        f"  GBP: {rub_per_usd / quotes['USDGBP']}\n"
        f"  CNY: {rub_per_usd / quotes['USDCNY']}"
    )

    result = convert_currency(1000, "USD", "RUB", quotes)
    print(f"Конвертация 1000 USD в RUB:\n  {result}")