"""SQLite storage for the Salary Calculator.

Pure standard library. The whole database lives in a single file (salary.db)
next to this module, so it can be copied, backed up or dropped into git.
"""
from __future__ import annotations

import datetime
import json
import os
import sqlite3
from typing import Any

import auth

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("SALARYCALC_DB", os.path.join(BASE_DIR, "salary.db"))
SEED_PATH = os.path.join(BASE_DIR, "seed", "masters_india.json")

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS countries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    currency_code   TEXT NOT NULL DEFAULT 'INR',
    currency_symbol TEXT NOT NULL DEFAULT '₹',
    locale          TEXT DEFAULT 'en-IN'
);

CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    country_id  INTEGER NOT NULL REFERENCES countries(id) ON DELETE CASCADE,
    code        TEXT NOT NULL,
    name        TEXT NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (country_id, code)
);

CREATE TABLE IF NOT EXISTS states (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    country_id  INTEGER NOT NULL REFERENCES countries(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    UNIQUE (country_id, name)
);

CREATE TABLE IF NOT EXISTS cities (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    state_id    INTEGER NOT NULL REFERENCES states(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    rank        INTEGER,
    UNIQUE (state_id, name)
);

CREATE TABLE IF NOT EXISTS min_wages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    country_id      INTEGER NOT NULL REFERENCES countries(id) ON DELETE CASCADE,
    state_id        INTEGER REFERENCES states(id) ON DELETE CASCADE,
    city_id         INTEGER REFERENCES cities(id) ON DELETE CASCADE,
    category_id     INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    amount          REAL NOT NULL DEFAULT 0,
    effective_from  TEXT,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    country_id  INTEGER NOT NULL REFERENCES countries(id) ON DELETE CASCADE,
    key         TEXT NOT NULL,
    value       TEXT,
    UNIQUE (country_id, key)
);

CREATE TABLE IF NOT EXISTS companies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    country_id  INTEGER REFERENCES countries(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    code        TEXT,
    is_active   INTEGER NOT NULL DEFAULT 1,
    UNIQUE (country_id, name)
);

CREATE TABLE IF NOT EXISTS app_meta (
    key     TEXT PRIMARY KEY,
    value   TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    email                TEXT NOT NULL UNIQUE,
    username             TEXT NOT NULL UNIQUE,
    display_name         TEXT,
    role                 TEXT NOT NULL DEFAULT 'user',
    password_hash        TEXT NOT NULL,
    is_active            INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    failed_attempts      INTEGER NOT NULL DEFAULT 0,
    locked_until         TEXT,
    last_login_at        TEXT,
    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen   TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS employees (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    country_id  INTEGER REFERENCES countries(id) ON DELETE SET NULL,
    state_id    INTEGER REFERENCES states(id) ON DELETE SET NULL,
    city_id     INTEGER REFERENCES cities(id) ON DELETE SET NULL,
    company_id  INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    designation TEXT,
    experience  TEXT,
    age         INTEGER,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS breakups (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id     INTEGER REFERENCES employees(id) ON DELETE CASCADE,
    label           TEXT,
    inputs_json     TEXT NOT NULL,
    result_json     TEXT NOT NULL,
    created_by      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cities_state ON cities(state_id);
CREATE INDEX IF NOT EXISTS idx_min_wages_city ON min_wages(city_id);
CREATE INDEX IF NOT EXISTS idx_min_wages_state ON min_wages(state_id);
CREATE INDEX IF NOT EXISTS idx_breakups_employee ON breakups(employee_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
"""

DEFAULT_SETTINGS: dict[str, Any] = {
    "basic_pct": 50,
    "hra_pct": 50,
    "pf_employee_pct": 12,
    "pf_employer_pct": 12,
    "pf_cap_amount": 3000,
    "esic_employee_pct": 0.75,
    "esic_employer_pct": 3.25,
    "esic_gross_ceiling": 21000,
    "gratuity_pct": 4.81,
    "pt_default": 200,
    "asset_allowance": 1499,
    "pay_frequency": 12,
}

DEFAULT_COMPANIES = ["Posiflex", "Quinta", "Portwell", "Mustek"]

MASTER_TABLES = {
    "countries": ["code", "name", "currency_code", "currency_symbol", "locale"],
    "categories": ["country_id", "code", "name", "sort_order"],
    "states": ["country_id", "name"],
    "cities": ["state_id", "name", "rank"],
    "min_wages": ["country_id", "state_id", "city_id", "category_id", "amount", "effective_from", "notes"],
    "companies": ["country_id", "name", "code", "is_active"],
}

# columns added after the first release (applied to pre-existing databases)
MIGRATIONS = {
    "employees": {"company_id": "INTEGER REFERENCES companies(id) ON DELETE SET NULL"},
    "breakups": {
        "created_by": "INTEGER REFERENCES users(id) ON DELETE SET NULL",
        "updated_at": "TEXT",
    },
}


def connect(path: str | None = None) -> sqlite3.Connection:
    """One connection per request. WAL + a busy timeout keep concurrent users happy."""
    conn = sqlite3.connect(path or DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 8000")
    return conn


def init_db(conn: sqlite3.Connection, seed_path: str = SEED_PATH) -> None:
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    _migrate(conn)
    if conn.execute("SELECT COUNT(*) AS n FROM countries").fetchone()["n"] == 0:
        if os.path.exists(seed_path):
            with open(seed_path, encoding="utf-8") as fh:
                seed_masters(conn, json.load(fh))
        else:
            seed_masters(conn, {"countries": [{
                "code": "IN", "name": "India",
                "currency_code": "INR", "currency_symbol": "₹", "locale": "en-IN",
            }]})
    if conn.execute("SELECT COUNT(*) AS n FROM settings").fetchone()["n"] == 0:
        for country in conn.execute("SELECT id FROM countries").fetchall():
            _write_settings(conn, country["id"], DEFAULT_SETTINGS)
    if conn.execute("SELECT COUNT(*) AS n FROM companies").fetchone()["n"] == 0:
        country_id = conn.execute("SELECT id FROM countries ORDER BY id LIMIT 1").fetchone()
        if country_id:
            for name in DEFAULT_COMPANIES:
                conn.execute("INSERT OR IGNORE INTO companies (country_id, name) VALUES (?,?)",
                             (country_id["id"], name))
    conn.execute("UPDATE breakups SET updated_at=created_at WHERE updated_at IS NULL")
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    for table, columns in MIGRATIONS.items():
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, ddl in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
    conn.commit()


def _write_settings(conn: sqlite3.Connection, country_id: int, values: dict[str, Any]) -> None:
    for key, value in values.items():
        conn.execute(
            "INSERT INTO settings (country_id, key, value) VALUES (?,?,?) "
            "ON CONFLICT(country_id, key) DO UPDATE SET value=excluded.value",
            (country_id, key, json.dumps(value)),
        )


def _id_of(conn: sqlite3.Connection, sql: str, params: tuple):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def seed_masters(conn: sqlite3.Connection, seed: dict[str, Any]) -> None:
    """Insert countries/categories/states/cities/companies/min-wages from a seed dict.

    Idempotent: an existing country/state/category with the same name is reused
    instead of duplicated, which is what makes importing a masters file safe.
    """
    country_ids: dict[str, int] = {}
    for c in seed.get("countries", []):
        conn.execute(
            "INSERT OR IGNORE INTO countries (code, name, currency_code, currency_symbol, locale) VALUES (?,?,?,?,?)",
            (c["code"], c["name"], c.get("currency_code", "INR"),
             c.get("currency_symbol", "₹"), c.get("locale", "en-IN")))
        cid = _id_of(conn, "SELECT id FROM countries WHERE code=?", (c["code"],))
        if cid:
            country_ids[c["code"]] = cid

    default_country = next(iter(country_ids.values()), None)
    if default_country is None:
        return

    cat_ids: dict[str, int] = {}
    for cat in seed.get("categories", []):
        conn.execute(
            "INSERT OR IGNORE INTO categories (country_id, code, name, sort_order) VALUES (?,?,?,?)",
            (default_country, cat["code"], cat.get("name", cat["code"]), cat.get("sort_order", 0)))
        cid = _id_of(conn, "SELECT id FROM categories WHERE country_id=? AND code=?",
                     (default_country, cat["code"]))
        if cid:
            cat_ids[cat["code"]] = cid

    state_ids: dict[str, int] = {}
    for st in seed.get("states", []):
        conn.execute("INSERT OR IGNORE INTO states (country_id, name) VALUES (?,?)",
                     (default_country, st["name"]))
        sid = _id_of(conn, "SELECT id FROM states WHERE country_id=? AND name=?",
                     (default_country, st["name"]))
        if sid:
            state_ids[st["name"]] = sid

    city_ids: dict[tuple[str, str], int] = {}
    for city in seed.get("cities", []):
        sid = state_ids.get(city["state"])
        if sid is None:
            continue
        conn.execute("INSERT OR IGNORE INTO cities (state_id, name, rank) VALUES (?,?,?)",
                     (sid, city["city"], city.get("rank")))
        cid = _id_of(conn, "SELECT id FROM cities WHERE state_id=? AND name=?",
                     (sid, city["city"]))
        if cid:
            city_ids[(city["state"], city["city"])] = cid

    for mw in seed.get("min_wages", []):
        city_id = city_ids.get((mw.get("state"), mw.get("city")))
        state_id = state_ids.get(mw.get("state"))
        category_id = cat_ids.get(mw.get("category")) if mw.get("category") else None
        existing = conn.execute(
            """SELECT id FROM min_wages
               WHERE country_id=? AND IFNULL(city_id,0)=IFNULL(?,0)
                 AND IFNULL(state_id,0)=IFNULL(?,0) AND IFNULL(category_id,0)=IFNULL(?,0)""",
            (default_country, city_id, state_id, category_id)).fetchone()
        if existing:
            conn.execute("UPDATE min_wages SET amount=?, effective_from=?, notes=? WHERE id=?",
                         (mw.get("amount", 0), mw.get("effective_from"), mw.get("notes"),
                          existing["id"]))
        else:
            conn.execute(
                "INSERT INTO min_wages (country_id, state_id, city_id, category_id, amount, effective_from, notes) "
                "VALUES (?,?,?,?,?,?,?)",
                (default_country, state_id, city_id, category_id, mw.get("amount", 0),
                 mw.get("effective_from"), mw.get("notes")))

    for company in seed.get("companies", []):
        name = company.get("name") if isinstance(company, dict) else company
        if name:
            conn.execute("INSERT OR IGNORE INTO companies (country_id, name) VALUES (?,?)",
                         (default_country, name))
    conn.commit()


# ---------------------------------------------------------------- generic CRUD

def list_rows(conn: sqlite3.Connection, table: str) -> list[dict]:
    _check_table(table)
    rows = conn.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def _check_table(table: str) -> None:
    if table not in MASTER_TABLES:
        raise ValueError(f"unknown table: {table}")


def create_row(conn: sqlite3.Connection, table: str, data: dict) -> dict:
    _check_table(table)
    cols = [c for c in MASTER_TABLES[table] if c in data]
    if not cols:
        raise ValueError("no valid columns supplied")
    placeholders = ",".join("?" for _ in cols)
    cur = conn.execute(
        f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})",
        [data[c] for c in cols],
    )
    conn.commit()
    return dict(conn.execute(f"SELECT * FROM {table} WHERE id=?", (cur.lastrowid,)).fetchone())


def update_row(conn: sqlite3.Connection, table: str, row_id: int, data: dict) -> dict | None:
    _check_table(table)
    cols = [c for c in MASTER_TABLES[table] if c in data]
    if not cols:
        raise ValueError("no valid columns supplied")
    assigns = ",".join(f"{c}=?" for c in cols)
    conn.execute(f"UPDATE {table} SET {assigns} WHERE id=?", [data[c] for c in cols] + [row_id])
    conn.commit()
    row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone()
    return dict(row) if row else None


def delete_row(conn: sqlite3.Connection, table: str, row_id: int) -> bool:
    _check_table(table)
    cur = conn.execute(f"DELETE FROM {table} WHERE id=?", (row_id,))
    conn.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------- app metadata

def meta_get(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = conn.execute("SELECT value FROM app_meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def meta_set(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO app_meta (key, value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value)),
    )
    conn.commit()


# ---------------------------------------------------------------- settings

def get_settings(conn: sqlite3.Connection, country_id: int) -> dict[str, Any]:
    out = dict(DEFAULT_SETTINGS)
    for row in conn.execute("SELECT key, value FROM settings WHERE country_id=?", (country_id,)):
        try:
            out[row["key"]] = json.loads(row["value"])
        except (TypeError, ValueError):
            out[row["key"]] = row["value"]
    return out


def save_settings(conn: sqlite3.Connection, country_id: int, values: dict[str, Any]) -> dict[str, Any]:
    _write_settings(conn, country_id, values)
    conn.commit()
    return get_settings(conn, country_id)


# ---------------------------------------------------------------- users

PUBLIC_USER = ("id", "email", "username", "display_name", "role", "is_active",
               "must_change_password", "last_login_at", "created_at")


def public_user(user: dict) -> dict:
    return {k: user.get(k) for k in PUBLIC_USER}


def has_users(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] > 0


def get_user(conn: sqlite3.Connection, user_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_user_by_login(conn: sqlite3.Connection, identifier: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM users WHERE lower(email)=lower(?) OR lower(username)=lower(?)",
        (identifier or "", identifier or ""),
    ).fetchone()
    return dict(row) if row else None


def list_users(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    return [public_user(dict(r)) for r in rows]


def count_admins(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM users WHERE role='admin' AND is_active=1").fetchone()["n"]


def create_user(conn: sqlite3.Connection, *, email: str, username: str, display_name: str,
                password: str, role: str = "user", must_change_password: int = 0) -> dict:
    cur = conn.execute(
        """INSERT INTO users (email, username, display_name, role, password_hash, must_change_password)
           VALUES (?,?,?,?,?,?)""",
        (email.strip().lower(), username.strip(), (display_name or username).strip(),
         role, auth.hash_password(password), 1 if must_change_password else 0),
    )
    conn.commit()
    return get_user(conn, cur.lastrowid)


def update_user(conn: sqlite3.Connection, user_id: int, data: dict) -> dict | None:
    allowed = ["email", "username", "display_name", "role", "is_active"]
    cols = [c for c in allowed if c in data]
    if cols:
        assigns = ",".join(f"{c}=?" for c in cols)
        params = [data[c] for c in cols]
        if "email" in data and data["email"]:
            params[cols.index("email")] = str(data["email"]).strip().lower()
        conn.execute(f"UPDATE users SET {assigns}, updated_at=datetime('now') WHERE id=?", params + [user_id])
        conn.commit()
    return get_user(conn, user_id)


def set_password(conn: sqlite3.Connection, user_id: int, password: str,
                 must_change: bool = False) -> None:
    conn.execute(
        """UPDATE users SET password_hash=?, must_change_password=?, failed_attempts=0,
                  locked_until=NULL, updated_at=datetime('now') WHERE id=?""",
        (auth.hash_password(password), 1 if must_change else 0, user_id),
    )
    conn.commit()


def delete_user(conn: sqlite3.Connection, user_id: int) -> bool:
    cur = conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    return cur.rowcount > 0


def register_failed_login(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute("UPDATE users SET failed_attempts=failed_attempts+1 WHERE id=?", (user_id,))
    row = conn.execute("SELECT failed_attempts FROM users WHERE id=?", (user_id,)).fetchone()
    if row and row["failed_attempts"] >= auth.MAX_FAILED_ATTEMPTS:
        until = auth.iso(auth.now() + datetime.timedelta(minutes=auth.LOCK_MINUTES))
        conn.execute("UPDATE users SET locked_until=? WHERE id=?", (until, user_id))
    conn.commit()


def register_successful_login(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute(
        """UPDATE users SET failed_attempts=0, locked_until=NULL,
                  last_login_at=datetime('now') WHERE id=?""", (user_id,))
    conn.commit()


def is_locked(user: dict) -> bool:
    until = user.get("locked_until")
    if not until:
        return False
    try:
        return datetime.datetime.strptime(until, "%Y-%m-%d %H:%M:%S") > auth.now()
    except ValueError:
        return False


# ---------------------------------------------------------------- sessions

def create_session(conn: sqlite3.Connection, user_id: int, token: str) -> None:
    conn.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?,?,?)",
                 (auth.token_digest(token), user_id, auth.expiry()))
    conn.commit()


def session_user(conn: sqlite3.Connection, token: str) -> dict | None:
    if not token:
        return None
    row = conn.execute(
        """SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id
           WHERE s.token_hash=? AND s.expires_at > datetime('now') AND u.is_active=1""",
        (auth.token_digest(token),),
    ).fetchone()
    if not row:
        return None
    conn.execute("UPDATE sessions SET last_seen=datetime('now') WHERE token_hash=?",
                 (auth.token_digest(token),))
    conn.commit()
    return dict(row)


def delete_session(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token_hash=?", (auth.token_digest(token),))
    conn.commit()


def delete_user_sessions(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    conn.commit()


def purge_sessions(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM sessions WHERE expires_at <= datetime('now')")
    conn.commit()


# ---------------------------------------------------------------- employees / breakups

EMPLOYEE_COLS = ["name", "country_id", "state_id", "city_id", "company_id",
                 "designation", "experience", "age"]


def list_employees(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT e.*, c.name AS country_name, s.name AS state_name, ct.name AS city_name,
                  co.name AS company_name
           FROM employees e
           LEFT JOIN countries c ON c.id = e.country_id
           LEFT JOIN states s ON s.id = e.state_id
           LEFT JOIN cities ct ON ct.id = e.city_id
           LEFT JOIN companies co ON co.id = e.company_id
           ORDER BY e.id DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


def upsert_employee(conn: sqlite3.Connection, data: dict, row_id: int | None = None) -> dict:
    cols = [c for c in EMPLOYEE_COLS if c in data]
    if row_id is None:
        placeholders = ",".join("?" for _ in cols)
        cur = conn.execute(
            f"INSERT INTO employees ({','.join(cols)}) VALUES ({placeholders})",
            [data[c] for c in cols],
        )
        row_id = cur.lastrowid
    else:
        assigns = ",".join(f"{c}=?" for c in cols)
        conn.execute(
            f"UPDATE employees SET {assigns}, updated_at=datetime('now') WHERE id=?",
            [data[c] for c in cols] + [row_id],
        )
    conn.commit()
    row = conn.execute("SELECT * FROM employees WHERE id=?", (row_id,)).fetchone()
    return dict(row) if row else {}


def find_employee_by_name(conn: sqlite3.Connection, name: str) -> dict | None:
    row = conn.execute("SELECT * FROM employees WHERE lower(name)=lower(?)", (name or "",)).fetchone()
    return dict(row) if row else None


def delete_employee(conn: sqlite3.Connection, row_id: int) -> bool:
    cur = conn.execute("DELETE FROM employees WHERE id=?", (row_id,))
    conn.commit()
    return cur.rowcount > 0


def list_breakups(conn: sqlite3.Connection, employee_id: int | None = None) -> list[dict]:
    sql = """SELECT b.id, b.employee_id, b.label, b.inputs_json, b.result_json,
                    b.created_at, b.updated_at, b.created_by,
                    e.name AS employee_name, co.name AS company_name, u.display_name AS created_by_name
             FROM breakups b
             LEFT JOIN employees e ON e.id = b.employee_id
             LEFT JOIN companies co ON co.id = e.company_id
             LEFT JOIN users u ON u.id = b.created_by"""
    params: list[Any] = []
    if employee_id is not None:
        sql += " WHERE b.employee_id=?"
        params.append(employee_id)
    sql += " ORDER BY b.id DESC"
    out = []
    for r in conn.execute(sql, params):
        d = dict(r)
        inputs = json.loads(d.pop("inputs_json"))
        result = json.loads(d.pop("result_json"))
        d["inputs"] = inputs
        d["summary"] = {
            "proposed_ctc": result.get("proposed_ctc"),
            "basic": result.get("basic"),
            "take_home": result.get("take_home"),
            "min_wage": result.get("min_wage"),
            "feasible": result.get("feasible"),
            "company": d.get("company_name") or inputs.get("company_name"),
            "city": inputs.get("city_name"),
        }
        d["result"] = result
        out.append(d)
    return out


def save_breakup(conn: sqlite3.Connection, employee_id: int | None, label: str,
                 inputs: dict, result: dict, created_by: int | None = None,
                 breakup_id: int | None = None) -> dict:
    if breakup_id:
        conn.execute(
            """UPDATE breakups SET employee_id=?, label=?, inputs_json=?, result_json=?,
                      updated_at=datetime('now') WHERE id=?""",
            (employee_id, label, json.dumps(inputs), json.dumps(result), breakup_id),
        )
        row_id = breakup_id
    else:
        cur = conn.execute(
            """INSERT INTO breakups (employee_id, label, inputs_json, result_json, created_by)
               VALUES (?,?,?,?,?)""",
            (employee_id, label, json.dumps(inputs), json.dumps(result), created_by),
        )
        row_id = cur.lastrowid
    conn.commit()
    return dict(conn.execute("SELECT * FROM breakups WHERE id=?", (row_id,)).fetchone())


def delete_breakup(conn: sqlite3.Connection, row_id: int) -> bool:
    cur = conn.execute("DELETE FROM breakups WHERE id=?", (row_id,))
    conn.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------- reset & validation

def _clear_masters(conn: sqlite3.Connection) -> None:
    """Remove every master table. Users, sessions and metadata are preserved."""
    for table in ("breakups", "employees", "min_wages", "cities", "states",
                  "categories", "settings", "companies", "countries"):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()


def reset_to_seed(conn: sqlite3.Connection, seed_path: str = SEED_PATH) -> None:
    """Reset master data only. Users, sessions and app metadata are preserved."""
    _clear_masters(conn)
    with open(seed_path, encoding="utf-8") as fh:
        seed_masters(conn, json.load(fh))
    country = conn.execute("SELECT id FROM countries ORDER BY id LIMIT 1").fetchone()
    if country:
        for name in DEFAULT_COMPANIES:
            conn.execute("INSERT OR IGNORE INTO companies (country_id, name) VALUES (?,?)",
                         (country["id"], name))
    conn.commit()


def export_masters(conn: sqlite3.Connection) -> dict:
    """A portable, name-based snapshot of the master data (backup or sharing)."""
    countries = [{"code": r["code"], "name": r["name"], "currency_code": r["currency_code"],
                  "currency_symbol": r["currency_symbol"], "locale": r["locale"]}
                 for r in conn.execute("SELECT * FROM countries ORDER BY id")]
    categories = [{"code": r["code"], "name": r["name"], "sort_order": r["sort_order"]}
                  for r in conn.execute("SELECT * FROM categories ORDER BY sort_order, id")]
    states = [{"name": r["name"]} for r in conn.execute("SELECT * FROM states ORDER BY name")]
    cities = [{"city": r["city"], "state": r["state"], "rank": r["rank"]}
              for r in conn.execute(
                  """SELECT ci.name city, ci.rank, s.name state FROM cities ci
                     JOIN states s ON s.id = ci.state_id ORDER BY s.name, ci.name""")]
    companies = [{"name": r["name"], "code": r["code"]}
                 for r in conn.execute("SELECT * FROM companies ORDER BY name")]
    min_wages = [{"city": r["city"], "state": r["state"], "category": r["category"],
                  "amount": r["amount"], "effective_from": r["effective_from"], "notes": r["notes"]}
                 for r in conn.execute(
                     """SELECT m.amount, m.effective_from, m.notes, ci.name city, s.name state,
                               cat.code category
                        FROM min_wages m
                        LEFT JOIN cities ci ON ci.id = m.city_id
                        LEFT JOIN states s ON s.id = COALESCE(m.state_id, ci.state_id)
                        LEFT JOIN categories cat ON cat.id = m.category_id
                        ORDER BY state, city""")]
    return {"schema": 1, "countries": countries, "categories": categories,
            "states": states, "cities": cities, "companies": companies,
            "min_wages": min_wages}


def replace_masters(conn: sqlite3.Connection, data: dict) -> None:
    """Replace all master data with an imported snapshot."""
    _clear_masters(conn)
    seed_masters(conn, data)


def validate_data(conn: sqlite3.Connection) -> dict:
    """Return data-integrity issues across the master tables."""
    errors: list[dict] = []
    warnings: list[dict] = []

    def add(bucket, message, table, row_id=None):
        bucket.append({"message": message, "table": table, "id": row_id})

    for r in conn.execute("""SELECT c.id, c.name FROM cities c
                             LEFT JOIN states s ON s.id = c.state_id WHERE s.id IS NULL"""):
        add(errors, f"City “{r['name']}” is not linked to a valid state.", "cities", r["id"])

    for r in conn.execute("SELECT id FROM min_wages WHERE amount IS NULL OR amount <= 0"):
        add(errors, "Minimum wage has no amount (or is zero).", "min_wages", r["id"])

    for r in conn.execute("""SELECT m.id FROM min_wages m
                             LEFT JOIN cities c ON c.id = m.city_id
                             WHERE m.city_id IS NOT NULL AND c.id IS NULL"""):
        add(errors, "Minimum wage points to a city that no longer exists.", "min_wages", r["id"])

    for r in conn.execute("SELECT id FROM min_wages WHERE city_id IS NULL AND state_id IS NULL"):
        add(warnings, "Minimum wage is not tied to a city or a state.", "min_wages", r["id"])

    for r in conn.execute("""SELECT s.id, s.name FROM states s
                             WHERE NOT EXISTS (SELECT 1 FROM cities c WHERE c.state_id = s.id)"""):
        add(warnings, f"State “{r['name']}” has no cities.", "states", r["id"])

    for r in conn.execute("""SELECT c.id, c.name FROM countries c
                             WHERE c.currency_symbol IS NULL OR c.currency_symbol=''"""):
        add(warnings, f"Country “{r['name']}” has no currency symbol.", "countries", r["id"])

    for r in conn.execute("""SELECT e.id, e.name FROM employees e
                             WHERE (e.city_id IS NOT NULL AND
                                    NOT EXISTS (SELECT 1 FROM cities c WHERE c.id = e.city_id))"""):
        add(errors, f"Record “{r['name']}” points to a missing city.", "employees", r["id"])

    total_cities = conn.execute("SELECT COUNT(*) AS n FROM cities").fetchone()["n"]
    rows = conn.execute(
        """SELECT c.id, c.name FROM cities c
           WHERE NOT EXISTS (SELECT 1 FROM min_wages m
                             WHERE m.amount > 0 AND (m.city_id = c.id OR (m.city_id IS NULL AND m.state_id = c.state_id)))
           ORDER BY c.name"""
    ).fetchall()
    missing = [{"id": r["id"], "name": r["name"]} for r in rows]

    min_wages = conn.execute("SELECT COUNT(*) AS n FROM min_wages WHERE amount > 0").fetchone()["n"]
    return {
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "countries": conn.execute("SELECT COUNT(*) AS n FROM countries").fetchone()["n"],
            "states": conn.execute("SELECT COUNT(*) AS n FROM states").fetchone()["n"],
            "cities": total_cities,
            "cities_with_min_wage": total_cities - len(missing),
            "cities_without_min_wage": len(missing),
            "min_wage_rules": min_wages,
            "companies": conn.execute("SELECT COUNT(*) AS n FROM companies").fetchone()["n"],
            "users": conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"],
            "records": conn.execute("SELECT COUNT(*) AS n FROM breakups").fetchone()["n"],
        },
        "cities_without_min_wage": missing,
    }
