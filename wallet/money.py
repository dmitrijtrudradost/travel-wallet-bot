import re


def format_money(value: float) -> str:
    """Деньги с пробелом между тысячами и двумя знаками: 200 000.00."""
    rounded = round(float(value), 2)
    sign = "-" if rounded < 0 else ""
    whole, frac = f"{abs(rounded):.2f}".split(".")
    groups = []
    while whole:
        groups.append(whole[-3:])
        whole = whole[:-3]
    body = " ".join(reversed(groups)) or "0"
    return f"{sign}{body}.{frac}"


def format_home_rate(home_per_dest: float) -> str:
    """Сколько валюты назначения дают за 1 единицу домашней, четыре знака: 0.0104."""
    if not home_per_dest:
        return "0.0000"
    return f"{1 / float(home_per_dest):.4f}"


def parse_amount(text: str) -> float | None:
    """Первое число в сообщении. «1 000,5 юаней» читается как 1000.5."""
    compact = re.sub(r"(?<=\d)\s+(?=\d)", "", text.strip())
    match = re.search(r"\d+(?:[.,]\d+)?", compact)
    if match is None:
        return None
    return float(match.group(0).replace(",", "."))


def parse_strict_number(text: str) -> float | None:
    """Сообщение целиком является числом. Так вводятся сумма и ручной курс."""
    compact = text.strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
    if not re.fullmatch(r"\d+(?:\.\d+)?", compact):
        return None
    return float(compact)
