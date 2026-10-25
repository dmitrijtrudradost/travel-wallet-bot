from wallet.money import format_money, parse_amount, parse_strict_number


def test_format_money_groups_thousands():
    assert format_money(30720) == "30 720.00"
    assert format_money(1280) == "1 280.00"
    assert format_money(12.5) == "12.50"
    assert format_money(-100) == "-100.00"


def test_parse_amount_finds_number_in_text():
    assert parse_amount("100") == 100
    assert parse_amount("1 000,5 юаней") == 1000.5
    assert parse_amount("привет") is None


def test_parse_strict_number_rejects_words():
    assert parse_strict_number("12,5") == 12.5
    assert parse_strict_number("100 юаней") is None
