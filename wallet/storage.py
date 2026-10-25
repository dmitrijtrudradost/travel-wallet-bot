import json
import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS trips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    origin_country TEXT NOT NULL,
    dest_country TEXT NOT NULL,
    home_currency TEXT NOT NULL,
    dest_currency TEXT NOT NULL,
    rate REAL NOT NULL,
    home_balance REAL NOT NULL,
    dest_balance REAL NOT NULL,
    initial_home REAL,
    title TEXT,
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    trip_id INTEGER NOT NULL,
    amount_dest REAL NOT NULL,
    amount_home REAL NOT NULL,
    expense_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    receipt_path TEXT
);
CREATE TABLE IF NOT EXISTS dialogs (
    user_id INTEGER PRIMARY KEY,
    step TEXT NOT NULL,
    payload TEXT NOT NULL
);
"""


class Storage:
    """Локальная база одного файла SQLite. У каждого user_id свои путешествия."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.executescript(SCHEMA)
            self._ensure_initial_home(con)
            self._ensure_title(con)
            self._ensure_receipt_path(con)

    def _ensure_initial_home(self, con: sqlite3.Connection) -> None:
        columns = {row["name"] for row in con.execute("PRAGMA table_info(trips)")}
        if "initial_home" not in columns:
            con.execute("ALTER TABLE trips ADD COLUMN initial_home REAL")
            con.execute(
                "UPDATE trips SET initial_home = home_balance WHERE initial_home IS NULL"
            )

    def _ensure_title(self, con: sqlite3.Connection) -> None:
        columns = {row["name"] for row in con.execute("PRAGMA table_info(trips)")}
        if "title" not in columns:
            con.execute("ALTER TABLE trips ADD COLUMN title TEXT")
        con.execute(
            """
            UPDATE trips
            SET title = origin_country || ' → ' || dest_country
            WHERE title IS NULL OR trim(title) = ''
            """
        )

    def _ensure_receipt_path(self, con: sqlite3.Connection) -> None:
        columns = {row["name"] for row in con.execute("PRAGMA table_info(expenses)")}
        if "receipt_path" not in columns:
            con.execute("ALTER TABLE expenses ADD COLUMN receipt_path TEXT")

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def get_dialog(self, user_id: int) -> tuple[str, dict]:
        with self._connect() as con:
            row = con.execute(
                "SELECT step, payload FROM dialogs WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return "idle", {}
        return row["step"], json.loads(row["payload"])

    def set_dialog(self, user_id: int, step: str, payload: dict | None = None) -> None:
        body = json.dumps(payload or {}, ensure_ascii=False)
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO dialogs (user_id, step, payload)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    step = excluded.step,
                    payload = excluded.payload
                """,
                (user_id, step, body),
            )

    def clear_dialog(self, user_id: int) -> None:
        self.set_dialog(user_id, "idle", {})

    def create_trip(self, **fields) -> int:
        with self._connect() as con:
            con.execute(
                "UPDATE trips SET is_active = 0 WHERE user_id = ?",
                (fields["user_id"],),
            )
            cursor = con.execute(
                """
                INSERT INTO trips (
                    user_id, origin_country, dest_country, home_currency,
                    dest_currency, rate, home_balance, dest_balance,
                    initial_home, title, is_active, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    fields["user_id"],
                    fields["origin_country"],
                    fields["dest_country"],
                    fields["home_currency"],
                    fields["dest_currency"],
                    fields["rate"],
                    fields["home_balance"],
                    fields["dest_balance"],
                    fields.get("initial_home", fields["home_balance"]),
                    fields.get("title")
                    or f"{fields['origin_country']} → {fields['dest_country']}",
                    fields["created_at"],
                ),
            )
            return int(cursor.lastrowid)

    def list_trips(self, user_id: int) -> list[dict]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT * FROM trips WHERE user_id = ? ORDER BY title COLLATE NOCASE, id",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_trip(self, user_id: int, trip_id: int) -> dict | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM trips WHERE user_id = ? AND id = ?",
                (user_id, trip_id),
            ).fetchone()
        return dict(row) if row else None

    def active_trip(self, user_id: int) -> dict | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM trips WHERE user_id = ? AND is_active = 1",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def set_active(self, user_id: int, trip_id: int) -> bool:
        with self._connect() as con:
            owned = con.execute(
                "SELECT id FROM trips WHERE user_id = ? AND id = ?",
                (user_id, trip_id),
            ).fetchone()
            if owned is None:
                return False
            con.execute("UPDATE trips SET is_active = 0 WHERE user_id = ?", (user_id,))
            con.execute(
                "UPDATE trips SET is_active = 1 WHERE user_id = ? AND id = ?",
                (user_id, trip_id),
            )
            return True

    def update_balances_and_rate(
        self,
        user_id: int,
        trip_id: int,
        rate: float,
        home_balance: float,
        dest_balance: float,
    ) -> None:
        with self._connect() as con:
            con.execute(
                """
                UPDATE trips
                SET rate = ?, home_balance = ?, dest_balance = ?
                WHERE user_id = ? AND id = ?
                """,
                (rate, home_balance, dest_balance, user_id, trip_id),
            )

    def apply_expense(
        self,
        user_id: int,
        trip_id: int,
        amount_dest: float,
        amount_home: float,
        expense_type: str,
        created_at: str,
        new_dest: float,
        new_home: float,
        receipt_path: str | None = None,
    ) -> bool:
        with self._connect() as con:
            owned = con.execute(
                "SELECT id FROM trips WHERE user_id = ? AND id = ?",
                (user_id, trip_id),
            ).fetchone()
            if owned is None:
                return False
            con.execute(
                """
                UPDATE trips
                SET dest_balance = ?, home_balance = ?
                WHERE user_id = ? AND id = ?
                """,
                (new_dest, new_home, user_id, trip_id),
            )
            con.execute(
                """
                INSERT INTO expenses (
                    user_id, trip_id, amount_dest, amount_home,
                    expense_type, created_at, receipt_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    trip_id,
                    amount_dest,
                    amount_home,
                    expense_type,
                    created_at,
                    receipt_path,
                ),
            )
            return True

    def name_choices(self, user_id: int) -> list[tuple[int, str]]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT MIN(id) AS id, title
                FROM trips
                WHERE user_id = ? AND title IS NOT NULL AND trim(title) != ''
                GROUP BY title COLLATE NOCASE
                ORDER BY title COLLATE NOCASE
                """,
                (user_id,),
            ).fetchall()
        return [(int(row["id"]), row["title"]) for row in rows]

    def expenses(self, user_id: int, title: str | None = None) -> list[dict]:
        query = """
                SELECT
                    e.amount_dest, e.amount_home, e.expense_type, e.created_at,
                    e.receipt_path,
                    t.origin_country, t.dest_country, t.home_currency, t.dest_currency,
                    t.title
                FROM expenses e
                JOIN trips t ON t.id = e.trip_id
                WHERE e.user_id = ?
                """
        params: list = [user_id]
        if title:
            query += " AND t.title = ? COLLATE NOCASE"
            params.append(title)
        query += " ORDER BY t.title COLLATE NOCASE, e.id DESC"
        with self._connect() as con:
            rows = con.execute(query, params).fetchall()
        return [dict(row) for row in rows]
