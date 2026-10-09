#!/usr/bin/env python3
"""Salary Calculator – offline server.

Standard library only. Serves the single-page UI and a JSON API backed by the
SQLite file ``salary.db`` next to this script.

    python3 app.py                 # this computer only (default)
    python3 app.py --network       # share on the local network over HTTPS
    python3 app.py --host 0.0.0.0  # same, explicit
    python3 app.py --port 9000
    python3 app.py --reset-admin   # recover a lost admin password (local only)

Network mode binds to the LAN and serves HTTPS using a self-signed certificate
that is generated locally on first use (no OpenSSL, no dependencies).
"""
from __future__ import annotations

import argparse
import datetime
import json
import mimetypes
import os
import re
import socket
import ssl
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import auth
import calc
import certgen
import db
import report

APP_NAME = "Salary Calculator"
REPO_SLUG = "debaranjan-pegu/salarycalculator"


def _read_version() -> str:
    """The version comes from the VERSION file, so an upgrade carries it along."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "VERSION"), encoding="utf-8") as fh:
            value = fh.read().strip()
            if value:
                return value
    except OSError:
        pass
    return "1.3.0"


APP_VERSION = _read_version()
COOKIE = "sc_session"
COOKIE_MAX_AGE = auth.SESSION_DAYS * 24 * 3600
LOGIN_WINDOW = 300          # seconds
LOGIN_MAX_ATTEMPTS = 25     # per IP, per window

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
CERT_DIR = os.path.join(BASE_DIR, "certs")
CERT_FILE = os.path.join(CERT_DIR, "salarycalc-cert.pem")
KEY_FILE = os.path.join(CERT_DIR, "salarycalc-key.pem")

PUBLIC_PATHS = {
    ("GET", "/api/auth/status"),
    ("POST", "/api/auth/setup"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/recover"),
}

_login_fails: dict[str, list[float]] = {}


# --------------------------------------------------------------------- helpers

def _int_or_none(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _client_ip(handler) -> str:
    return handler.client_address[0] if handler.client_address else "?"


def _throttled(ip: str) -> bool:
    now = time.time()
    hits = [t for t in _login_fails.get(ip, []) if now - t < LOGIN_WINDOW]
    _login_fails[ip] = hits
    return len(hits) >= LOGIN_MAX_ATTEMPTS


def _note_failure(ip: str) -> None:
    _login_fails.setdefault(ip, []).append(time.time())


def _min_wage_for(conn, country_id: int, city_id, state_id, category_id) -> float:
    row = conn.execute(
        """SELECT amount FROM min_wages
           WHERE country_id = ?
             AND (city_id = ? OR city_id IS NULL)
             AND (state_id = ? OR state_id IS NULL)
             AND (category_id = ? OR category_id IS NULL)
           ORDER BY (city_id IS NOT NULL) DESC,
                    (state_id IS NOT NULL) DESC,
                    (category_id IS NOT NULL) DESC
           LIMIT 1""",
        (country_id, city_id, state_id, category_id),
    ).fetchone()
    return float(row["amount"]) if row else 0.0


def _credentials_problem(email: str, username: str, password: str) -> str | None:
    for label, checker, value in (("Email", auth.email_problems, email),
                                  ("Username", auth.username_problems, username),
                                  ("Password", auth.password_problems, password)):
        problems = checker(value)
        if problems:
            if label == "Password":
                return "Password must contain " + ", ".join(problems) + "."
            return f"{label} must be {problems[0]}."
    return None


# --------------------------------------------------------------------- routing

class Handler(BaseHTTPRequestHandler):
    server_version = "SalaryCalc/" + APP_VERSION
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    # ---- plumbing ---------------------------------------------------------
    def _cookie(self, name):
        raw = self.headers.get("Cookie") or ""
        for part in raw.split(";"):
            key, _, value = part.strip().partition("=")
            if key == name:
                return value
        return None

    def _secure_flag(self) -> str:
        return "; Secure" if getattr(self.server, "tls", False) else ""

    def _login_cookie(self, token):
        return (f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict"
                f"; Max-Age={COOKIE_MAX_AGE}{self._secure_flag()}")

    def _logout_cookie(self):
        return f"{COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0{self._secure_flag()}"

    def _origin_ok(self) -> bool:
        """Cheap CSRF guard: a state-changing request must come from our own host."""
        origin = self.headers.get("Origin")
        if not origin:
            return True                     # curl / same-origin tools
        return urlparse(origin).netloc == (self.headers.get("Host") or "")

    def _send_json(self, payload, status=200, cookies=None):
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for value in cookies or []:
            self.send_header("Set-Cookie", value)
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, payload, content_type, filename):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return {}

    def _serve_static(self, rel_path):
        rel_path = rel_path.lstrip("/") or "index.html"
        full = os.path.normpath(os.path.join(STATIC_DIR, rel_path))
        if not full.startswith(STATIC_DIR) or not os.path.isfile(full):
            self.send_error(404, "Not found")
            return
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _dispatch(self, method):
        path = self.path.split("?", 1)[0]
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        params = {}
        for pair in query.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                params[k] = v
        try:
            if method != "GET" and not self._origin_ok():
                return self._send_json({"error": "Cross-origin request refused."}, status=403)
            if path in ("/", "/index.html"):
                return self._serve_static("index.html")
            if path.startswith("/static/"):
                return self._serve_static(path[len("/static/"):])
            if path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if path.startswith("/api/"):
                return self._api(method, path, params)
            self.send_error(404, "Not found")
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    # ---- auth helpers -----------------------------------------------------
    def _current_user(self, conn):
        return db.session_user(conn, self._cookie(COOKIE))

    def _require_admin(self, user):
        if user.get("role") != "admin":
            self._send_json({"error": "Administrator access required."}, status=403)
            return False
        return True

    # ---- API --------------------------------------------------------------
    def _api(self, method, path, params):
        conn = db.connect()
        try:
            if (method, path) in PUBLIC_PATHS:
                return self._api_public(conn, method, path)
            user = self._current_user(conn)
            if not user:
                return self._send_json({"error": "Please sign in."}, status=401)
            return self._api_secure(conn, method, path, params, user)
        finally:
            conn.close()

    # ---- public endpoints -------------------------------------------------
    def _api_public(self, conn, method, path):
        if method == "GET" and path == "/api/auth/status":
            user = self._current_user(conn)
            return self._send_json({
                "app": APP_NAME,
                "version": APP_VERSION,
                "initialized": db.has_users(conn),
                "authenticated": bool(user),
                "user": db.public_user(user) if user else None,
                "network": bool(getattr(self.server, "network", False)),
                "tls": bool(getattr(self.server, "tls", False)),
            })

        if method == "POST" and path == "/api/auth/setup":
            if db.has_users(conn):
                return self._send_json({"error": "This app is already set up."}, status=400)
            body = self._read_json()
            email = (body.get("email") or "").strip()
            username = (body.get("username") or "").strip()
            password = body.get("password") or ""
            problem = _credentials_problem(email, username, password)
            if problem:
                return self._send_json({"error": problem}, status=400)
            # Normally unreachable (setup only exists while there are no accounts),
            # but a race must give a clear message instead of a database error.
            if db.get_user_by_login(conn, email):
                return self._send_json({"error": "That email is already registered.",
                                        "field": "email"}, status=400)
            if db.get_user_by_login(conn, username):
                return self._send_json({"error": "That username is already taken.",
                                        "field": "username"}, status=400)
            recovery = auth.new_recovery_code()
            user = db.create_user(conn, email=email, username=username,
                                  display_name=body.get("display_name") or username,
                                  password=password, role="admin")
            db.meta_set(conn, "recovery_code_hash", auth.hash_password(recovery))
            db.meta_set(conn, "initialized_at", datetime.datetime.utcnow().isoformat(timespec="seconds"))
            db.meta_set(conn, "schema_version", APP_VERSION)
            token = auth.new_token()
            db.create_session(conn, user["id"], token)
            return self._send_json(
                {"user": db.public_user(user), "recovery_code": recovery, "version": APP_VERSION},
                cookies=[self._login_cookie(token)])

        if method == "POST" and path == "/api/auth/login":
            ip = _client_ip(self)
            if _throttled(ip):
                return self._send_json({"error": "Too many sign-in attempts. Please wait a few minutes."}, status=429)
            body = self._read_json()
            identifier = (body.get("identifier") or "").strip()
            password = body.get("password") or ""
            user = db.get_user_by_login(conn, identifier)
            if not user or not user["is_active"]:
                _note_failure(ip)
                time.sleep(0.4)
                return self._send_json({"error": "Invalid email/username or password."}, status=401)
            if db.is_locked(user):
                return self._send_json({"error": "Too many attempts. Try again in a few minutes."}, status=423)
            if not auth.verify_password(password, user["password_hash"]):
                db.register_failed_login(conn, user["id"])
                _note_failure(ip)
                time.sleep(0.4)
                return self._send_json({"error": "Invalid email/username or password."}, status=401)
            db.register_successful_login(conn, user["id"])
            db.purge_sessions(conn)
            token = auth.new_token()
            db.create_session(conn, user["id"], token)
            return self._send_json({"user": db.public_user(db.get_user(conn, user["id"]))},
                                   cookies=[self._login_cookie(token)])

        if method == "POST" and path == "/api/auth/recover":
            body = self._read_json()
            email = (body.get("email") or "").strip()
            code = (body.get("recovery_code") or "").strip()
            new_password = body.get("new_password") or ""
            stored = db.meta_get(conn, "recovery_code_hash")
            if not stored or not code or not auth.verify_password(code, json.loads(stored)):
                _note_failure(_client_ip(self))
                time.sleep(0.5)
                return self._send_json({"error": "That recovery code is not valid."}, status=401)
            user = db.get_user_by_login(conn, email)
            if not user or user["role"] != "admin":
                return self._send_json({"error": "No administrator matches that email."}, status=400)
            problems = auth.password_problems(new_password)
            if problems:
                return self._send_json({"error": "Password must contain " + ", ".join(problems)}, status=400)
            db.set_password(conn, user["id"], new_password)
            db.delete_user_sessions(conn, user["id"])
            replacement = auth.new_recovery_code()
            db.meta_set(conn, "recovery_code_hash", auth.hash_password(replacement))
            return self._send_json({"ok": True, "recovery_code": replacement})

        self.send_error(404, "Unknown endpoint")

    # ---- authenticated endpoints -----------------------------------------
    def _api_secure(self, conn, method, path, params, user):
        if method == "POST" and path == "/api/auth/logout":
            db.delete_session(conn, self._cookie(COOKIE))
            return self._send_json({"ok": True}, cookies=[self._logout_cookie()])

        if method == "GET" and path == "/api/auth/me":
            return self._send_json({"user": db.public_user(user)})

        if method == "POST" and path == "/api/auth/change-password":
            body = self._read_json()
            if not auth.verify_password(body.get("current_password") or "", user["password_hash"]):
                time.sleep(0.4)
                return self._send_json({"error": "Current password is incorrect."}, status=400)
            problems = auth.password_problems(body.get("new_password") or "")
            if problems:
                return self._send_json({"error": "Password must contain " + ", ".join(problems)}, status=400)
            db.set_password(conn, user["id"], body["new_password"])
            return self._send_json({"ok": True})

        # ---- master data export / import (admin) --------------------------
        if method == "GET" and path == "/api/masters/export":
            if not self._require_admin(user):
                return
            payload = db.export_masters(conn)
            payload["exported_at"] = datetime.datetime.utcnow().isoformat(timespec="seconds")
            payload["app_version"] = APP_VERSION
            body = json.dumps(payload, indent=1, ensure_ascii=False).encode("utf-8")
            return self._send_bytes(body, "application/json",
                                    f"salarycalc-masters-{datetime.date.today():%Y%m%d}.json")

        if method == "POST" and path == "/api/masters/import":
            if not self._require_admin(user):
                return
            data = self._read_json()
            if not isinstance(data, dict) or not data.get("countries"):
                return self._send_json({"error": "That file does not look like a masters export."}, status=400)
            db.replace_masters(conn, data)
            return self._send_json(self._bootstrap(conn, user))

        # ---- minimum-wage CSV (template + validated import) ----------------
        if method == "GET" and path == "/api/min-wages/template":
            body = db.min_wage_template(conn).encode("utf-8")
            return self._send_bytes(body, "text/csv; charset=utf-8", "minimum-wages-template.csv")

        if method == "POST" and path == "/api/min-wages/import":
            if not self._require_admin(user):
                return
            payload = self._read_json()
            text = payload.get("csv") or ""
            if not text.strip():
                return self._send_json({"error": "No CSV content received."}, status=400)
            return self._send_json(db.min_wage_import(conn, text, bool(payload.get("apply"))))

        # ---- user administration (admin only) -----------------------------
        if path == "/api/users" or path.startswith("/api/users/"):
            if not self._require_admin(user):
                return
            return self._users(conn, method, path, user)

        if method == "GET" and path == "/api/update/check":
            latest, error = None, None
            try:
                url = f"https://raw.githubusercontent.com/{REPO_SLUG}/main/VERSION"
                with urllib.request.urlopen(url, timeout=6) as resp:
                    latest = resp.read().decode("utf-8", "ignore").strip()
            except Exception as exc:
                error = f"Could not reach GitHub ({exc.__class__.__name__})."
            return self._send_json({
                "current": APP_VERSION,
                "latest": latest,
                "update_available": bool(latest and latest != APP_VERSION),
                "page": f"https://github.com/{REPO_SLUG}",
                "error": error,
            })

        if method == "GET" and path == "/api/validate":
            return self._send_json(db.validate_data(conn))

        if method == "GET" and path == "/api/bootstrap":
            return self._send_json(self._bootstrap(conn, user))

        if method == "POST" and path == "/api/calc":
            return self._send_json(self._calc(conn, self._read_json()))

        if method == "POST" and path == "/api/solve":
            body = self._read_json()
            country_id, settings, min_wage, symbol = self._resolve(conn, body)
            try:
                target = float(body.get("target_take_home") or 0)
            except (TypeError, ValueError):
                target = 0.0
            solved = calc.solve_ctc_for_take_home(dict(body), settings, min_wage, target)
            result = solved["result"]
            result["currency_symbol"] = symbol
            return self._send_json({"ctc": solved["ctc"], "achieved": solved["achieved"],
                                    "target_take_home": target,
                                    "below_minimum": solved.get("below_minimum", False),
                                    "floor_take_home": solved.get("floor_take_home"),
                                    "result": result})
        if method == "POST" and path == "/api/export":
            return self._export(conn, self._read_json())

        if method == "POST" and path == "/api/reset":
            if not self._require_admin(user):
                return
            db.reset_to_seed(conn)
            return self._send_json(self._bootstrap(conn, user))

        if method == "GET" and path == "/api/employees":
            return self._send_json({"employees": db.list_employees(conn)})
        if method == "POST" and path == "/api/employees":
            body = self._read_json()
            row_id = _int_or_none(body.get("id"))
            if row_id is None and body.get("name"):
                existing = db.find_employee_by_name(conn, body["name"])
                row_id = existing["id"] if existing else None
            return self._send_json(db.upsert_employee(conn, body, row_id))
        m = re.fullmatch(r"/api/employees/(\d+)", path)
        if m and method == "PUT":
            return self._send_json(db.upsert_employee(conn, self._read_json(), int(m.group(1))))
        if m and method == "DELETE":
            return self._send_json({"deleted": db.delete_employee(conn, int(m.group(1)))})

        if method == "GET" and path == "/api/breakups":
            emp = _int_or_none(params.get("employee_id"))
            return self._send_json({"breakups": db.list_breakups(conn, emp)})
        if method == "POST" and path == "/api/breakups":
            body = self._read_json()
            saved = db.save_breakup(
                conn, _int_or_none(body.get("employee_id")), body.get("label", ""),
                body.get("inputs", {}), body.get("result", {}),
                created_by=user["id"], breakup_id=_int_or_none(body.get("breakup_id")))
            return self._send_json(saved)
        m = re.fullmatch(r"/api/breakups/(\d+)", path)
        if m and method == "DELETE":
            return self._send_json({"deleted": db.delete_breakup(conn, int(m.group(1)))})

        if method == "POST" and path == "/api/settings":
            if not self._require_admin(user):
                return
            body = self._read_json()
            country_id = _int_or_none(body.get("country_id")) or 1
            return self._send_json({"settings": db.save_settings(conn, country_id, body.get("values", {}))})

        m = re.fullmatch(r"/api/(\w+)", path)
        if m and m.group(1) in db.MASTER_TABLES:
            table = m.group(1)
            if method == "GET":
                return self._send_json({table: db.list_rows(conn, table)})
            if method == "POST":
                return self._send_json(db.create_row(conn, table, self._read_json()))
        m = re.fullmatch(r"/api/(\w+)/(\d+)", path)
        if m and m.group(1) in db.MASTER_TABLES:
            table, row_id = m.group(1), int(m.group(2))
            if method == "PUT":
                row = db.update_row(conn, table, row_id, self._read_json())
                if row is None:
                    return self._send_json({"error": "not found"}, status=404)
                return self._send_json(row)
            if method == "DELETE":
                return self._send_json({"deleted": db.delete_row(conn, table, row_id)})

        self.send_error(404, "Unknown endpoint")

    # ---- users ------------------------------------------------------------
    def _users(self, conn, method, path, current):
        if method == "GET" and path == "/api/users":
            return self._send_json({"users": db.list_users(conn)})

        if method == "POST" and path == "/api/users":
            body = self._read_json()
            email = (body.get("email") or "").strip()
            username = (body.get("username") or "").strip()
            role = body.get("role") if body.get("role") in ("admin", "user") else "user"
            for field, checker, value in (("Email", auth.email_problems, email),
                                          ("Username", auth.username_problems, username)):
                if checker(value):
                    return self._send_json({"error": f"{field} must be {checker(value)[0]}."}, status=400)
            if db.get_user_by_login(conn, email) or db.get_user_by_login(conn, username):
                return self._send_json({"error": "That email or username already exists."}, status=400)
            generated = None
            password = body.get("password") or ""
            if not password:
                password = auth.generate_password()
                generated = password
            else:
                problems = auth.password_problems(password)
                if problems:
                    return self._send_json({"error": "Password must contain " + ", ".join(problems)}, status=400)
            user = db.create_user(conn, email=email, username=username,
                                  display_name=body.get("display_name") or username,
                                  password=password, role=role,
                                  must_change_password=bool(generated))
            return self._send_json({"user": db.public_user(user), "generated_password": generated})

        m = re.fullmatch(r"/api/users/(\d+)", path)
        if m and method == "PUT":
            body = self._read_json()
            target_id = int(m.group(1))
            target = db.get_user(conn, target_id)
            if not target:
                return self._send_json({"error": "User not found."}, status=404)
            if body.get("role") and body["role"] not in ("admin", "user"):
                body.pop("role")
            if target["role"] == "admin" and body.get("role") == "user" and db.count_admins(conn) <= 1:
                return self._send_json({"error": "There must always be at least one administrator."}, status=400)
            if target_id == current["id"] and body.get("is_active") == 0:
                return self._send_json({"error": "You cannot deactivate your own account."}, status=400)
            for field, checker in (("email", auth.email_problems), ("username", auth.username_problems)):
                if body.get(field) and checker(str(body[field])):
                    return self._send_json({"error": f"{field.title()} must be {checker(str(body[field]))[0]}."}, status=400)
            return self._send_json({"user": db.public_user(db.update_user(conn, target_id, body) or {})})

        if m and method == "DELETE":
            target = db.get_user(conn, int(m.group(1)))
            if not target:
                return self._send_json({"error": "User not found."}, status=404)
            if target["id"] == current["id"]:
                return self._send_json({"error": "You cannot delete your own account."}, status=400)
            if target["role"] == "admin" and db.count_admins(conn) <= 1:
                return self._send_json({"error": "There must always be at least one administrator."}, status=400)
            return self._send_json({"deleted": db.delete_user(conn, target["id"])})

        m = re.fullmatch(r"/api/users/(\d+)/reset-password", path)
        if m and method == "POST":
            target = db.get_user(conn, int(m.group(1)))
            if not target:
                return self._send_json({"error": "User not found."}, status=404)
            body = self._read_json()
            password = body.get("password") or ""
            generated = None
            if not password:
                password = auth.generate_password()
                generated = password
            db.set_password(conn, target["id"], password, must_change=True)
            db.delete_user_sessions(conn, target["id"])
            return self._send_json({"ok": True, "generated_password": generated})

        self.send_error(404, "Unknown endpoint")

    # ---- payload builders -------------------------------------------------
    def _bootstrap(self, conn, user):
        countries = db.list_rows(conn, "countries")
        payload = {
            "app": APP_NAME,
            "version": APP_VERSION,
            "user": db.public_user(user),
            "is_admin": user.get("role") == "admin",
            "network": bool(getattr(self.server, "network", False)),
            "tls": bool(getattr(self.server, "tls", False)),
            "urls": list(getattr(self.server, "urls", [])),
            "countries": countries,
            "categories": db.list_rows(conn, "categories"),
            "states": db.list_rows(conn, "states"),
            "cities": db.list_rows(conn, "cities"),
            "companies": db.list_rows(conn, "companies"),
            "grades": db.list_rows(conn, "grades"),
            "min_wages": db.list_rows(conn, "min_wages"),
            "employees": db.list_employees(conn),
            "breakups": db.list_breakups(conn),
            "users": db.list_users(conn) if user.get("role") == "admin" else [],
            "settings_by_country": {},
        }
        for c in countries:
            payload["settings_by_country"][str(c["id"])] = db.get_settings(conn, c["id"])
        return payload

    def _resolve(self, conn, body):
        country_id = _int_or_none(body.get("country_id"))
        if country_id is None:
            row = conn.execute("SELECT id FROM countries ORDER BY id LIMIT 1").fetchone()
            country_id = row["id"] if row else 1
        settings = db.get_settings(conn, country_id)
        if body.get("min_wage") in (None, ""):
            min_wage = _min_wage_for(
                conn, country_id,
                _int_or_none(body.get("city_id")),
                _int_or_none(body.get("state_id")),
                _int_or_none(body.get("category_id")),
            )
        else:
            min_wage = float(body["min_wage"])
        symbol = next((c["currency_symbol"] for c in db.list_rows(conn, "countries")
                       if c["id"] == country_id), "₹")
        return country_id, settings, min_wage, symbol

    def _calc(self, conn, body):
        country_id, settings, min_wage, symbol = self._resolve(conn, body)
        result = calc.compute(dict(body), settings, min_wage)
        result["country_id"] = country_id
        result["city_id"] = _int_or_none(body.get("city_id"))
        result["state_id"] = _int_or_none(body.get("state_id"))
        result["category_id"] = _int_or_none(body.get("category_id"))
        result["currency_symbol"] = symbol
        level, band = db.grade_for(conn, country_id, result.get("proposed_ctc") or 0)
        result["level"] = level["name"] if level else ""
        result["band"] = band["name"] if band else ""
        result["insurance"] = level["insurance"] if level else 0
        return result

    def _export(self, conn, body):
        country_id, settings, min_wage, symbol = self._resolve(conn, body)

        proposed = calc.compute(dict(body), settings, min_wage)
        proposed["currency_symbol"] = symbol

        previous_ctc = proposed.get("previous_ctc") or 0
        current = calc.compute(dict(body, proposed_ctc=previous_ctc, increment_pct=0, vp_pct=0),
                               settings, 0.0)

        country = next((c for c in db.list_rows(conn, "countries") if c["id"] == country_id), {})
        city = next((c for c in db.list_rows(conn, "cities")
                     if c["id"] == _int_or_none(body.get("city_id"))), None)
        state = next((s for s in db.list_rows(conn, "states")
                      if s["id"] == _int_or_none(body.get("state_id"))), None)
        category = next((c for c in db.list_rows(conn, "categories")
                         if c["id"] == _int_or_none(body.get("category_id"))), None)
        company = next((c for c in db.list_rows(conn, "companies")
                        if c["id"] == _int_or_none(body.get("company_id"))), None)

        level, band = db.grade_for(conn, country_id, proposed.get("proposed_ctc") or 0)
        location = {
            "name": body.get("name") or body.get("label") or "—",
            "company": (company or {}).get("name"),
            "experience": body.get("experience"),
            "age": body.get("age"),
            "designation": body.get("designation"),
            "level": level["name"] if level else None,
            "band": band["name"] if band else None,
            "insurance": level["insurance"] if level else 0,
            "country": country.get("name"),
            "state": state["name"] if state else None,
            "city": city["name"] if city else None,
            "category": category["name"] if category else None,
        }

        stamp = f"{datetime.date.today():%d %b %Y}  ·  Salary Calculator v{APP_VERSION}"
        data = report.build(location, current, proposed, min_wage, stamp)
        safe = re.sub(r"[^\w\-]+", "_", (body.get("name") or "salary").strip()).strip("_") or "salary"
        return self._send_bytes(
            data,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"{safe}_breakup.xlsx",
        )


def already_running(port: int) -> bool:
    """True when our own server already answers on this port (avoids a second copy)."""
    for scheme, context in (("https", ssl._create_unverified_context()), ("http", None)):
        try:
            with urllib.request.urlopen(f"{scheme}://127.0.0.1:{port}/api/auth/status",
                                        timeout=1.2, context=context) as resp:
                if json.loads(resp.read() or b"{}").get("app") == APP_NAME:
                    return True
        except Exception:
            continue
    return False


def find_port(host: str, preferred: int, attempts: int = 25) -> int:
    for port in range(preferred, preferred + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
                return port
            except OSError:
                continue
    raise SystemExit(f"No free port found on {host}.")


def reset_admin_password() -> int:
    """Offline recovery: run this on the machine that hosts the app."""
    conn = db.connect()
    db.init_db(conn)
    admins = [u for u in db.list_users(conn) if u["role"] == "admin"]
    if not admins:
        print("No administrator account exists. Start the app and create one.")
        return 1
    new_password = auth.generate_password(14)
    for admin in admins:
        db.set_password(conn, admin["id"], new_password, must_change=True)
        db.delete_user_sessions(conn, admin["id"])
        print(f"Password reset for {admin['username']} <{admin['email']}>")
    print(f"\nTemporary password: {new_password}")
    print("Sign in and change it immediately (all sessions were signed out).")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline salary breakup calculator")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1",
                        help="127.0.0.1 = this computer only (default); 0.0.0.0 = local network")
    parser.add_argument("--network", action="store_true",
                        help="share on the local network (same as --host 0.0.0.0)")
    parser.add_argument("--no-tls", action="store_true",
                        help="serve plain HTTP even in network mode (not recommended)")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--reset-admin", action="store_true",
                        help="reset the administrator password and exit")
    args = parser.parse_args()

    if args.reset_admin:
        sys.exit(reset_admin_password())

    if already_running(args.port):
        url = f"http://127.0.0.1:{args.port}/"
        print(f"{APP_NAME} is already running at {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return

    host = "0.0.0.0" if args.network else args.host
    network = host not in ("127.0.0.1", "localhost", "::1")
    tls = network and not args.no_tls

    conn = db.connect()
    db.init_db(conn)
    db.purge_sessions(conn)
    conn.close()

    port = find_port("0.0.0.0" if network else "127.0.0.1", args.port)
    server = ThreadingHTTPServer(("0.0.0.0" if network else "127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.network = network
    server.tls = tls

    local_url = f"{'https' if tls else 'http'}://127.0.0.1:{port}/"
    urls = []
    if network:
        cert, key = certgen.ensure_certificate(CERT_FILE, KEY_FILE)
        if tls:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(cert, key)
            server.socket = context.wrap_socket(server.socket, server_side=True)
        scheme = "https" if tls else "http"
        urls = [f"{scheme}://{ip}:{port}/" for ip in certgen.local_ips()
                if not ip.startswith("127.")]
    server.urls = urls

    print(f"{APP_NAME} {APP_VERSION}")
    print(f"  This computer : {local_url}")
    if network:
        print("  Share with your team:")
        for url in urls:
            print(f"     {url}")
        print(f"  Certificate   : {CERT_FILE}")
        print("  (Each person sees a one-time certificate warning — see README to silence it.)")
    else:
        print("  This computer only. To let your team in, run share.command / share.bat.")
    print("  Database:", db.DB_PATH)
    print("  Press Ctrl+C to stop.")

    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(local_url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.shutdown()


if __name__ == "__main__":
    sys.exit(main())
