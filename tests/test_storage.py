from wallet.storage import Storage


def test_active_trip_switches_only_for_owner(tmp_path):
    storage = Storage(tmp_path / "wallet.db")
    first = storage.create_trip(
        user_id=1,
        origin_country="Россия",
        dest_country="Китай",
        home_currency="RUB",
        dest_currency="CNY",
        rate=12,
        home_balance=1200,
        dest_balance=100,
        created_at="2026-10-25T16:00:00",
    )
    second = storage.create_trip(
        user_id=1,
        origin_country="Россия",
        dest_country="Россия",
        home_currency="RUB",
        dest_currency="RUB",
        rate=1,
        home_balance=50,
        dest_balance=50,
        created_at="2026-10-25T16:01:00",
    )
    assert storage.active_trip(1)["id"] == second
    assert storage.set_active(1, first) is True
    assert storage.active_trip(1)["id"] == first
    assert storage.set_active(2, first) is False
    assert storage.get_trip(2, first) is None

    saved = storage.apply_expense(
        user_id=1,
        trip_id=first,
        amount_dest=10,
        amount_home=120,
        expense_type="расход",
        created_at="2026-10-25T16:05:00",
        new_dest=90,
        new_home=1080,
    )
    assert saved is True
    assert storage.expenses(1)[0]["expense_type"] == "расход"
    assert storage.expenses(2) == []


def test_trips_sorted_and_expenses_filtered_by_title(tmp_path):
    storage = Storage(tmp_path / "wallet.db")
    storage.create_trip(
        user_id=1,
        origin_country="Россия",
        dest_country="Япония",
        home_currency="RUB",
        dest_currency="JPY",
        rate=1,
        home_balance=100,
        dest_balance=100,
        title="Япония",
        created_at="2026-10-25T16:00:00",
    )
    later = storage.create_trip(
        user_id=1,
        origin_country="Россия",
        dest_country="Австрия",
        home_currency="RUB",
        dest_currency="EUR",
        rate=1,
        home_balance=100,
        dest_balance=100,
        title="Альфа",
        created_at="2026-10-25T16:01:00",
    )
    assert [row["title"] for row in storage.list_trips(1)] == ["Альфа", "Япония"]
    storage.apply_expense(
        user_id=1,
        trip_id=later,
        amount_dest=10,
        amount_home=10,
        expense_type="еда",
        created_at="2026-10-25T16:05:00",
        new_dest=90,
        new_home=90,
    )
    assert storage.expenses(1, "Альфа")[0]["title"] == "Альфа"
    assert storage.expenses(1, "Япония") == []
