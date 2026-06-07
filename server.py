#!/usr/bin/env python3
"""
CardVault Pro: production-oriented collectible-card marketplace backend.
No third-party dependencies required for local launch.

Run:
  python3 server.py
Open:
  http://localhost:8000
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import smtplib
import sqlite3
import ssl
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from http import cookies
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, unquote, parse_qs

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"
DB_PATH = Path(os.getenv("CARDVAULT_DB", DATA_DIR / "cardvault.sqlite3"))
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
APP_URL = os.getenv("APP_URL", f"http://localhost:{PORT}").rstrip("/")
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-in-production-cardvault")
SESSION_DAYS = int(os.getenv("SESSION_DAYS", "30"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"
DEV_SHOW_TOKENS = os.getenv("DEV_SHOW_TOKENS", "1") == "1"
INITIAL_ADMIN_EMAIL = os.getenv("INITIAL_ADMIN_EMAIL", "admin@cardvault.local")
INITIAL_ADMIN_PASSWORD = os.getenv("INITIAL_ADMIN_PASSWORD", "CardVaultAdmin2026!")
MAX_JSON_BYTES = int(os.getenv("MAX_JSON_BYTES", str(8 * 1024 * 1024)))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "manual").lower()  # manual | stripe
PAYMENT_CURRENCY = os.getenv("PAYMENT_CURRENCY", "rub").lower()
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

RATE_BUCKET: dict[str, list[float]] = {}
RATE_RULES = {
    "auth": (8, 60),
    "write": (120, 60),
    "upload": (24, 60),
    "default": (300, 60),
}

SEED_PRODUCTS = [
    {
        "id": "aurora",
        "title": "2023 Aurora Football Elite Prospects #17",
        "category": "Футбол",
        "grade": "GEM MT 10",
        "price": 125000,
        "stock": 3,
        "seller_name": "Vault Sports Gallery",
        "seller_rating": 4.9,
        "description": "Редкая спортивная карта в защитном слабе CardVault. Проверена экспертами, доступна застрахованная доставка.",
        "status": "active",
        "featured": 1,
    },
    {
        "id": "dragon",
        "title": "2021 Chronicles of Eternia Draconic Sovereign #DS-07",
        "category": "Фэнтези",
        "grade": "GEM MT 10",
        "price": 98500,
        "stock": 5,
        "seller_name": "Eternia Collectors",
        "seller_rating": 4.8,
        "description": "Премиальная фэнтези-карта с глубоким глянцевым изображением и подтвержденной оценкой состояния.",
        "status": "active",
        "featured": 1,
    },
    {
        "id": "frontier",
        "title": "2022 Galactic Archives Frontier Pilot #FP-03",
        "category": "Научная фантастика",
        "grade": "GEM MT 10",
        "price": 76900,
        "stock": 4,
        "seller_name": "Archive One",
        "seller_rating": 4.9,
        "description": "Коллекционная карта в sci-fi тематике: чистые углы, яркая печать и полная аутентификация.",
        "status": "active",
        "featured": 1,
    },
    {
        "id": "flora",
        "title": "1929 Flora Universalis Monarchia No. 4",
        "category": "Винтаж",
        "grade": "EX-MT 6",
        "price": 210000,
        "stock": 1,
        "seller_name": "Old Paper House",
        "seller_rating": 5.0,
        "description": "Винтажная карта с ботанической иллюстрацией, редкое состояние для своего года выпуска.",
        "status": "active",
        "featured": 1,
    },
    {
        "id": "rookie",
        "title": "2020 Court Kings Rookie Portraits #RP-12",
        "category": "Баскетбол",
        "grade": "GEM MT 10",
        "price": 64300,
        "stock": 7,
        "seller_name": "Hoops Vault",
        "seller_rating": 4.7,
        "description": "Спортивная rookie card с чистой поверхностью, аккуратными краями и высокой оценкой.",
        "status": "active",
        "featured": 1,
    },
]

SEED_REVIEWS = [
    ("Алексей С.", "Москва", 5, "Потрясающий сервис! Карта пришла идеально упакованной и полностью соответствует описанию. Уровень доверия к CardVault на высоте."),
    ("Марина К.", "Санкт‑Петербург", 5, "Покупка прошла спокойно: проверка, оплата, трекинг и упаковка — всё выглядит как премиальный сервис."),
    ("Дмитрий П.", "Казань", 5, "Нравится, что цены, рейтинг продавца и состояние карты показаны прозрачно. Вернусь за следующими лотами."),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def future(days: int = 0, minutes: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days, minutes=minutes)).isoformat(timespec="seconds")


def json_dumps(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def hash_token(token: str) -> str:
    return hashlib.sha256((SECRET_KEY + ":" + token).encode("utf-8")).hexdigest()


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 260_000)
    return salt, digest.hex()


def verify_password(password: str, salt: str, stored_hash: str) -> bool:
    _, digest = hash_password(password, salt)
    return hmac.compare_digest(digest, stored_hash)


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def valid_email(email: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email or ""))


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip())
    return value.strip("-").lower() or secrets.token_hex(4)


def parse_cookie(header: str) -> dict[str, str]:
    jar = cookies.SimpleCookie()
    try:
        jar.load(header or "")
    except cookies.CookieError:
        return {}
    return {k: v.value for k, v in jar.items()}


def cookie_header(name: str, value: str, max_age: int | None = None, http_only: bool = True) -> str:
    c = cookies.SimpleCookie()
    c[name] = value
    c[name]["path"] = "/"
    c[name]["samesite"] = "Lax"
    if http_only:
        c[name]["httponly"] = True
    if COOKIE_SECURE:
        c[name]["secure"] = True
    if max_age is not None:
        c[name]["max-age"] = str(max_age)
    return c.output(header="").strip()


def send_email(to_email: str, subject: str, body: str) -> bool:
    host = os.getenv("SMTP_HOST", "")
    if not host:
        print(f"[mail disabled] To: {to_email}\nSubject: {subject}\n{body}\n")
        return False
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM", username or "noreply@cardvault.local")
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(host, port, timeout=15) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        if username:
            smtp.login(username, password)
        smtp.send_message(msg)
    return True


def create_schema() -> None:
    conn = connect()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'customer',
            email_verified INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS one_time_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            purpose TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            grade TEXT NOT NULL,
            price INTEGER NOT NULL CHECK(price >= 0),
            stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0),
            description TEXT NOT NULL,
            seller_name TEXT NOT NULL DEFAULT 'CardVault',
            seller_rating REAL NOT NULL DEFAULT 4.9,
            status TEXT NOT NULL DEFAULT 'active',
            featured INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS product_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            url TEXT NOT NULL,
            alt TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cart_items (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            qty INTEGER NOT NULL CHECK(qty > 0),
            updated_at TEXT NOT NULL,
            PRIMARY KEY(user_id, product_id)
        );
        CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            PRIMARY KEY(user_id, product_id)
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            total INTEGER NOT NULL,
            subtotal INTEGER NOT NULL DEFAULT 0,
            insurance INTEGER NOT NULL DEFAULT 0,
            shipping_fee INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            payment_status TEXT NOT NULL,
            payment_provider TEXT NOT NULL DEFAULT 'manual',
            payment_session_id TEXT,
            payment_url TEXT,
            tracking_number TEXT,
            shipping_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            product_id TEXT NOT NULL REFERENCES products(id),
            title TEXT NOT NULL,
            qty INTEGER NOT NULL,
            price INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS shipment_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            url TEXT NOT NULL,
            mime TEXT NOT NULL,
            size INTEGER NOT NULL,
            purpose TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sell_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            card TEXT NOT NULL,
            category TEXT NOT NULL,
            grade TEXT,
            price TEXT NOT NULL,
            message TEXT,
            photos_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'new',
            admin_note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS verification_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            card TEXT NOT NULL,
            email TEXT NOT NULL,
            photos_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'new',
            admin_note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            city TEXT,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            text TEXT NOT NULL,
            is_public INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            action TEXT NOT NULL,
            entity TEXT,
            entity_id TEXT,
            payload_json TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    # Safe column additions for upgrading older DBs.
    def columns(table: str) -> set[str]:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    product_cols = columns("products")
    for col, ddl in {
        "seller_name": "ALTER TABLE products ADD COLUMN seller_name TEXT NOT NULL DEFAULT 'CardVault'",
        "seller_rating": "ALTER TABLE products ADD COLUMN seller_rating REAL NOT NULL DEFAULT 4.9",
        "status": "ALTER TABLE products ADD COLUMN status TEXT NOT NULL DEFAULT 'active'",
        "featured": "ALTER TABLE products ADD COLUMN featured INTEGER NOT NULL DEFAULT 0",
        "updated_at": "ALTER TABLE products ADD COLUMN updated_at TEXT NOT NULL DEFAULT '2026-01-01T00:00:00+00:00'",
    }.items():
        if col not in product_cols:
            cur.execute(ddl)
    user_cols = columns("users")
    for col, ddl in {
        "email_verified": "ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0",
        "updated_at": "ALTER TABLE users ADD COLUMN updated_at TEXT NOT NULL DEFAULT '2026-01-01T00:00:00+00:00'",
    }.items():
        if col not in user_cols:
            cur.execute(ddl)
    order_cols = columns("orders")
    for col, ddl in {
        "subtotal": "ALTER TABLE orders ADD COLUMN subtotal INTEGER NOT NULL DEFAULT 0",
        "insurance": "ALTER TABLE orders ADD COLUMN insurance INTEGER NOT NULL DEFAULT 0",
        "shipping_fee": "ALTER TABLE orders ADD COLUMN shipping_fee INTEGER NOT NULL DEFAULT 0",
        "payment_provider": "ALTER TABLE orders ADD COLUMN payment_provider TEXT NOT NULL DEFAULT 'manual'",
        "payment_session_id": "ALTER TABLE orders ADD COLUMN payment_session_id TEXT",
        "payment_url": "ALTER TABLE orders ADD COLUMN payment_url TEXT",
        "tracking_number": "ALTER TABLE orders ADD COLUMN tracking_number TEXT",
        "updated_at": "ALTER TABLE orders ADD COLUMN updated_at TEXT NOT NULL DEFAULT '2026-01-01T00:00:00+00:00'",
    }.items():
        if col not in order_cols:
            cur.execute(ddl)
    sell_cols = columns("sell_requests")
    for col, ddl in {
        "photos_json": "ALTER TABLE sell_requests ADD COLUMN photos_json TEXT NOT NULL DEFAULT '[]'",
        "admin_note": "ALTER TABLE sell_requests ADD COLUMN admin_note TEXT",
        "updated_at": "ALTER TABLE sell_requests ADD COLUMN updated_at TEXT NOT NULL DEFAULT '2026-01-01T00:00:00+00:00'",
    }.items():
        if col not in sell_cols:
            cur.execute(ddl)
    conn.commit()
    conn.close()


def seed_data() -> None:
    conn = connect()
    cur = conn.cursor()
    for p in SEED_PRODUCTS:
        cur.execute(
            """
            INSERT INTO products(id,title,category,grade,price,stock,description,seller_name,seller_rating,status,featured,created_at,updated_at)
            VALUES(:id,:title,:category,:grade,:price,:stock,:description,:seller_name,:seller_rating,:status,:featured,:created_at,:updated_at)
            ON CONFLICT(id) DO UPDATE SET
              title=excluded.title, category=excluded.category, grade=excluded.grade,
              price=excluded.price, description=excluded.description, seller_name=excluded.seller_name,
              seller_rating=excluded.seller_rating, status=excluded.status, featured=excluded.featured,
              updated_at=excluded.updated_at
            """,
            {**p, "created_at": utc_now(), "updated_at": utc_now()},
        )
    if cur.execute("SELECT COUNT(*) AS c FROM reviews").fetchone()["c"] == 0:
        for author, city, rating, text in SEED_REVIEWS:
            cur.execute("INSERT INTO reviews(author,city,rating,text,created_at) VALUES(?,?,?,?,?)", (author, city, rating, text, utc_now()))
    if not cur.execute("SELECT id FROM users WHERE email=?", (INITIAL_ADMIN_EMAIL,)).fetchone():
        salt, digest = hash_password(INITIAL_ADMIN_PASSWORD)
        cur.execute(
            "INSERT INTO users(name,email,password_salt,password_hash,role,email_verified,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            ("CardVault Admin", INITIAL_ADMIN_EMAIL, salt, digest, "admin", 1, utc_now(), utc_now()),
        )
    conn.commit()
    conn.close()


def public_product(row: sqlite3.Row, conn: sqlite3.Connection | None = None) -> dict:
    d = dict(row)
    d["price"] = int(d["price"])
    d["stock"] = int(d["stock"])
    d["featured"] = bool(d.get("featured", 0))
    d["seller_rating"] = float(d.get("seller_rating", 4.9))
    own = False
    if conn is None:
        conn = connect()
        own = True
    imgs = conn.execute("SELECT url,alt FROM product_images WHERE product_id=? ORDER BY sort_order,id", (d["id"],)).fetchall()
    d["images"] = [dict(r) for r in imgs]
    if own:
        conn.close()
    return d



def parse_content_disposition(value: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in value.split(';'):
        part = part.strip()
        if '=' in part:
            k, v = part.split('=', 1)
            out[k.strip().lower()] = v.strip().strip('"')
        elif part:
            out['type'] = part.lower()
    return out

def parse_multipart(body: bytes, content_type: str) -> dict[str, list[dict[str, Any]]]:
    m = re.search(r'boundary=(?:"([^"]+)"|([^;]+))', content_type or '')
    if not m:
        raise ApiError(400, 'Не найден multipart boundary')
    boundary = (m.group(1) or m.group(2)).encode('utf-8')
    marker = b'--' + boundary
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw_part in body.split(marker):
        raw_part = raw_part.strip()
        if not raw_part or raw_part == b'--':
            continue
        if raw_part.endswith(b'--'):
            raw_part = raw_part[:-2].rstrip()
        header_blob, sep, part_body = raw_part.partition(b'\r\n\r\n')
        if not sep:
            header_blob, sep, part_body = raw_part.partition(b'\n\n')
        headers: dict[str, str] = {}
        for line in header_blob.decode('utf-8', errors='replace').splitlines():
            if ':' in line:
                k, v = line.split(':', 1)
                headers[k.lower().strip()] = v.strip()
        disp = parse_content_disposition(headers.get('content-disposition', ''))
        name = disp.get('name')
        if not name:
            continue
        # strip trailing CRLF added before boundary
        part_body = part_body.rstrip(b'\r\n')
        result[name].append({
            'filename': disp.get('filename', ''),
            'content_type': headers.get('content-type', ''),
            'body': part_body,
            'text': part_body.decode('utf-8', errors='replace'),
        })
    return result

class ApiError(Exception):
    def __init__(self, status: int, message: str, code: str = "ERROR"):
        self.status = status
        self.message = message
        self.code = code
        super().__init__(message)


class CardVaultHandler(BaseHTTPRequestHandler):
    server_version = "CardVaultPro/2.0"

    def log_message(self, fmt, *args):
        print(f"[{utc_now()}] {self.client_address[0]} {fmt % args}")

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self' https://api.stripe.com; frame-ancestors 'self'; base-uri 'self'; form-action 'self' https://checkout.stripe.com")
        super().end_headers()

    def _client_ip(self) -> str:
        forwarded = self.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        return forwarded or self.client_address[0]

    def rate_limit(self, bucket: str):
        limit, window = RATE_RULES.get(bucket, RATE_RULES["default"])
        key = f"{self._client_ip()}:{bucket}"
        now = time.time()
        hits = [t for t in RATE_BUCKET.get(key, []) if now - t < window]
        if len(hits) >= limit:
            raise ApiError(429, "Слишком много запросов. Попробуйте чуть позже.", "RATE_LIMIT")
        hits.append(now)
        RATE_BUCKET[key] = hits

    def send_json(self, data: Any, status: int = 200, extra_headers: list[tuple[str, str]] | None = None):
        payload = json_dumps(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        for name, value in extra_headers or []:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)

    def send_error_json(self, status: int, message: str, code: str = "ERROR"):
        return self.send_json({"ok": False, "error": message, "code": code}, status)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_JSON_BYTES:
            raise ApiError(413, "Слишком большой запрос", "PAYLOAD_TOO_LARGE")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            raise ApiError(400, "Некорректный JSON", "BAD_JSON")
        if not isinstance(data, dict):
            raise ApiError(400, "Ожидался JSON-объект", "BAD_JSON")
        return data

    def cookies(self) -> dict[str, str]:
        return parse_cookie(self.headers.get("Cookie", ""))

    def ensure_csrf(self, path: str):
        if self.command in ("GET", "HEAD", "OPTIONS"):
            return
        # Stripe webhooks use their own signature.
        if path == "/api/payments/stripe/webhook":
            return
        cookie_token = self.cookies().get("cv_csrf", "")
        header_token = self.headers.get("X-CSRF-Token", "")
        if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
            raise ApiError(403, "Защитный токен устарел. Обновите страницу.", "CSRF")

    def current_user(self, required: bool = True, admin: bool = False) -> dict | None:
        token = ""
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth.split(" ", 1)[1].strip()
        if not token:
            token = self.cookies().get("cv_session", "")
        if not token:
            if required:
                raise ApiError(401, "Нужно войти в аккаунт", "AUTH_REQUIRED")
            return None
        conn = connect()
        row = conn.execute(
            """
            SELECT u.id,u.name,u.email,u.role,u.email_verified,s.expires_at
            FROM sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=?
            """,
            (hash_token(token),),
        ).fetchone()
        conn.close()
        if not row:
            if required:
                raise ApiError(401, "Сессия не найдена", "AUTH_REQUIRED")
            return None
        if row["expires_at"] < utc_now():
            if required:
                raise ApiError(401, "Сессия истекла", "AUTH_EXPIRED")
            return None
        user = dict(row)
        user["email_verified"] = bool(user["email_verified"])
        if admin and user["role"] != "admin":
            raise ApiError(403, "Нет прав администратора", "FORBIDDEN")
        return user

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def do_PATCH(self):
        self.handle_request()

    def do_DELETE(self):
        self.handle_request()

    def handle_request(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            self.ensure_csrf(path)
            if path.startswith("/api/"):
                return self.handle_api(self.command, path, parse_qs(parsed.query))
            if path.startswith("/uploads/"):
                return self.serve_upload(path)
            if self.command != "GET":
                return self.send_error_json(405, "Метод не поддерживается", "METHOD")
            return self.serve_static(path)
        except ApiError as exc:
            return self.send_error_json(exc.status, exc.message, exc.code)
        except BrokenPipeError:
            return None
        except Exception as exc:
            print("Internal error:", repr(exc))
            return self.send_error_json(500, "Внутренняя ошибка сервера", "INTERNAL")

    def serve_static(self, path: str):
        if path in ("", "/"):
            path = "/index.html"
        safe_path = unquote(path).lstrip("/")
        if ".." in Path(safe_path).parts:
            raise ApiError(403, "Доступ запрещён", "FORBIDDEN")
        file_path = PUBLIC_DIR / safe_path
        if not file_path.exists() or not file_path.is_file():
            file_path = PUBLIC_DIR / "index.html"
        content = file_path.read_bytes()
        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        if file_path.suffix == ".html":
            content_type = "text/html; charset=utf-8"
        elif file_path.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif file_path.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache" if file_path.suffix == ".html" else "public, max-age=86400")
        self.end_headers()
        self.wfile.write(content)

    def serve_upload(self, path: str):
        safe_path = unquote(path).lstrip("/")
        if ".." in Path(safe_path).parts:
            raise ApiError(403, "Доступ запрещён", "FORBIDDEN")
        file_path = BASE_DIR / safe_path
        if not file_path.exists() or not file_path.is_file() or not file_path.resolve().is_relative_to(UPLOAD_DIR.resolve()):
            raise ApiError(404, "Файл не найден", "NOT_FOUND")
        content = file_path.read_bytes()
        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "public, max-age=604800")
        self.end_headers()
        self.wfile.write(content)

    def handle_api(self, method: str, path: str, query: dict[str, list[str]]):
        bucket = "default"
        if path.startswith("/api/auth") or path.startswith("/api/password"):
            bucket = "auth"
        elif method in ("POST", "PATCH", "DELETE"):
            bucket = "write"
        if path == "/api/uploads":
            bucket = "upload"
        self.rate_limit(bucket)

        if method == "GET" and path == "/api/health":
            return self.send_json({"ok": True, "service": "CardVault Pro", "time": utc_now()})
        if method == "GET" and path == "/api/csrf":
            return self.get_csrf()
        if method == "GET" and path == "/api/products":
            return self.get_products(query)
        if method == "GET" and re.fullmatch(r"/api/products/[\w-]+", path):
            return self.get_product(path.rsplit("/", 1)[1])
        if method == "POST" and path == "/api/auth/register":
            return self.register()
        if method == "POST" and path == "/api/auth/login":
            return self.login()
        if method == "POST" and path == "/api/auth/logout":
            return self.logout()
        if method == "GET" and path == "/api/me":
            return self.send_json({"ok": True, "user": self.current_user(required=False)})
        if method == "POST" and path == "/api/auth/resend-verification":
            return self.resend_verification()
        if method == "POST" and path == "/api/auth/verify-email":
            return self.verify_email()
        if method == "POST" and path == "/api/password-reset/request":
            return self.password_reset_request()
        if method == "POST" and path == "/api/password-reset/confirm":
            return self.password_reset_confirm()
        if method == "POST" and path == "/api/uploads":
            return self.upload_files()
        if method == "GET" and path == "/api/cart":
            return self.get_cart()
        if method == "POST" and path == "/api/cart/items":
            return self.add_cart_item()
        if method == "PATCH" and re.fullmatch(r"/api/cart/items/[\w-]+", path):
            return self.update_cart_item(path.rsplit("/", 1)[1])
        if method == "DELETE" and re.fullmatch(r"/api/cart/items/[\w-]+", path):
            return self.delete_cart_item(path.rsplit("/", 1)[1])
        if method == "GET" and path == "/api/favorites":
            return self.get_favorites()
        if method == "POST" and re.fullmatch(r"/api/favorites/[\w-]+", path):
            return self.add_favorite(path.rsplit("/", 1)[1])
        if method == "DELETE" and re.fullmatch(r"/api/favorites/[\w-]+", path):
            return self.delete_favorite(path.rsplit("/", 1)[1])
        if method == "POST" and path == "/api/orders/checkout":
            return self.checkout()
        if method == "GET" and path == "/api/orders":
            return self.get_orders()
        if method == "POST" and path == "/api/sell-requests":
            return self.create_sell_request()
        if method == "POST" and path == "/api/verification-requests":
            return self.create_verification_request()
        if method == "GET" and path == "/api/stats":
            return self.get_stats()
        if method == "GET" and path == "/api/reviews":
            return self.get_reviews()
        if method == "POST" and path == "/api/payments/stripe/webhook":
            return self.stripe_webhook()

        if method == "GET" and path == "/api/admin/dashboard":
            return self.admin_dashboard()
        if method == "GET" and path == "/api/admin/products":
            return self.admin_products()
        if method == "POST" and path == "/api/admin/products":
            return self.admin_create_product()
        if method == "PATCH" and re.fullmatch(r"/api/admin/products/[\w-]+", path):
            return self.admin_update_product(path.rsplit("/", 1)[1])
        if method == "DELETE" and re.fullmatch(r"/api/admin/products/[\w-]+", path):
            return self.admin_delete_product(path.rsplit("/", 1)[1])
        if method == "GET" and path == "/api/admin/orders":
            return self.admin_orders()
        if method == "PATCH" and re.fullmatch(r"/api/admin/orders/\d+", path):
            return self.admin_update_order(int(path.rsplit("/", 1)[1]))
        if method == "GET" and path == "/api/admin/sell-requests":
            return self.admin_sell_requests()
        if method == "PATCH" and re.fullmatch(r"/api/admin/sell-requests/\d+", path):
            return self.admin_update_sell_request(int(path.rsplit("/", 1)[1]))
        if method == "GET" and path == "/api/admin/verification-requests":
            return self.admin_verification_requests()
        if method == "PATCH" and re.fullmatch(r"/api/admin/verification-requests/\d+", path):
            return self.admin_update_verification_request(int(path.rsplit("/", 1)[1]))
        return self.send_error_json(404, "API-метод не найден", "NOT_FOUND")

    def audit(self, conn: sqlite3.Connection, actor_id: int | None, action: str, entity: str = "", entity_id: str = "", payload: dict | None = None):
        conn.execute(
            "INSERT INTO audit_logs(actor_id,action,entity,entity_id,payload_json,created_at) VALUES(?,?,?,?,?,?)",
            (actor_id, action, entity, entity_id, json.dumps(payload or {}, ensure_ascii=False), utc_now()),
        )

    def get_csrf(self):
        token = self.cookies().get("cv_csrf") or secrets.token_urlsafe(32)
        return self.send_json({"ok": True, "csrf_token": token}, 200, [("Set-Cookie", cookie_header("cv_csrf", token, max_age=60 * 60 * 24 * 30, http_only=False))])

    def create_session(self, conn: sqlite3.Connection, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        conn.execute("INSERT INTO sessions(user_id,token_hash,expires_at,created_at) VALUES(?,?,?,?)", (user_id, hash_token(token), future(days=SESSION_DAYS), utc_now()))
        return token

    def public_user(self, row: sqlite3.Row | dict) -> dict:
        return {"id": row["id"], "name": row["name"], "email": row["email"], "role": row["role"], "email_verified": bool(row["email_verified"])}

    def create_one_time_token(self, conn: sqlite3.Connection, user_id: int, purpose: str, minutes: int = 60 * 24) -> str:
        token = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO one_time_tokens(user_id,purpose,token_hash,expires_at,created_at) VALUES(?,?,?,?,?)",
            (user_id, purpose, hash_token(token), future(minutes=minutes), utc_now()),
        )
        return token

    def register(self):
        data = self.read_json()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        name = (data.get("name") or email.split("@")[0] or "Покупатель").strip()[:80]
        if not valid_email(email):
            raise ApiError(400, "Введите корректный email", "VALIDATION")
        if len(password) < 8:
            raise ApiError(400, "Пароль должен быть не короче 8 символов", "VALIDATION")
        salt, digest = hash_password(password)
        conn = connect()
        try:
            cur = conn.execute(
                "INSERT INTO users(name,email,password_salt,password_hash,role,email_verified,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (name, email, salt, digest, "customer", 0, utc_now(), utc_now()),
            )
            user_id = cur.lastrowid
            token = self.create_session(conn, user_id)
            verify_token = self.create_one_time_token(conn, user_id, "email_verify", minutes=60 * 24 * 3)
            user = conn.execute("SELECT id,name,email,role,email_verified FROM users WHERE id=?", (user_id,)).fetchone()
            self.audit(conn, user_id, "register", "user", str(user_id))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            raise ApiError(409, "Аккаунт с таким email уже существует", "EMAIL_EXISTS")
        conn.close()
        link = f"{APP_URL}/?verify_email={urllib.parse.quote(verify_token)}"
        send_email(email, "Подтвердите email в CardVault", f"Здравствуйте! Подтвердите email: {link}\nЕсли вы не регистрировались, просто игнорируйте письмо.")
        headers = [("Set-Cookie", cookie_header("cv_session", token, max_age=SESSION_DAYS * 24 * 3600))]
        payload = {"ok": True, "user": self.public_user(user), "message": "Аккаунт создан. Проверьте email для подтверждения."}
        if DEV_SHOW_TOKENS:
            payload["dev_email_verification_token"] = verify_token
        return self.send_json(payload, 201, headers)

    def login(self):
        data = self.read_json()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        conn = connect()
        row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not row or not verify_password(password, row["password_salt"], row["password_hash"]):
            conn.close()
            raise ApiError(401, "Неверный email или пароль", "BAD_CREDENTIALS")
        token = self.create_session(conn, row["id"])
        self.audit(conn, row["id"], "login", "user", str(row["id"]))
        conn.commit()
        conn.close()
        headers = [("Set-Cookie", cookie_header("cv_session", token, max_age=SESSION_DAYS * 24 * 3600))]
        return self.send_json({"ok": True, "user": self.public_user(row)}, 200, headers)

    def logout(self):
        token = self.cookies().get("cv_session", "")
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth.split(" ", 1)[1].strip()
        if token:
            conn = connect()
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (hash_token(token),))
            conn.commit()
            conn.close()
        return self.send_json({"ok": True}, 200, [("Set-Cookie", cookie_header("cv_session", "", max_age=0))])

    def verify_email(self):
        data = self.read_json()
        token = (data.get("token") or "").strip()
        if not token:
            raise ApiError(400, "Нужен токен подтверждения", "VALIDATION")
        conn = connect()
        row = conn.execute("SELECT * FROM one_time_tokens WHERE token_hash=? AND purpose='email_verify' AND used_at IS NULL", (hash_token(token),)).fetchone()
        if not row or row["expires_at"] < utc_now():
            conn.close()
            raise ApiError(400, "Ссылка подтверждения устарела", "TOKEN_EXPIRED")
        conn.execute("UPDATE one_time_tokens SET used_at=? WHERE id=?", (utc_now(), row["id"]))
        conn.execute("UPDATE users SET email_verified=1,updated_at=? WHERE id=?", (utc_now(), row["user_id"]))
        self.audit(conn, row["user_id"], "email_verified", "user", str(row["user_id"]))
        conn.commit()
        conn.close()
        return self.send_json({"ok": True, "message": "Email подтверждён"})

    def resend_verification(self):
        user = self.current_user()
        if user["email_verified"]:
            return self.send_json({"ok": True, "message": "Email уже подтверждён"})
        conn = connect()
        token = self.create_one_time_token(conn, user["id"], "email_verify", minutes=60 * 24 * 3)
        conn.commit()
        conn.close()
        link = f"{APP_URL}/?verify_email={urllib.parse.quote(token)}"
        send_email(user["email"], "Подтвердите email в CardVault", f"Подтвердите email: {link}")
        payload = {"ok": True, "message": "Письмо отправлено"}
        if DEV_SHOW_TOKENS:
            payload["dev_email_verification_token"] = token
        return self.send_json(payload)

    def password_reset_request(self):
        data = self.read_json()
        email = (data.get("email") or "").strip().lower()
        conn = connect()
        row = conn.execute("SELECT id,email FROM users WHERE email=?", (email,)).fetchone()
        token = None
        if row:
            token = self.create_one_time_token(conn, row["id"], "password_reset", minutes=60)
            conn.commit()
            link = f"{APP_URL}/?reset_password={urllib.parse.quote(token)}"
            send_email(row["email"], "Сброс пароля CardVault", f"Ссылка для сброса пароля действует 1 час: {link}")
        conn.close()
        payload = {"ok": True, "message": "Если аккаунт существует, мы отправили письмо для сброса пароля."}
        if token and DEV_SHOW_TOKENS:
            payload["dev_password_reset_token"] = token
        return self.send_json(payload)

    def password_reset_confirm(self):
        data = self.read_json()
        token = (data.get("token") or "").strip()
        password = data.get("password") or ""
        if len(password) < 8:
            raise ApiError(400, "Пароль должен быть не короче 8 символов", "VALIDATION")
        conn = connect()
        row = conn.execute("SELECT * FROM one_time_tokens WHERE token_hash=? AND purpose='password_reset' AND used_at IS NULL", (hash_token(token),)).fetchone()
        if not row or row["expires_at"] < utc_now():
            conn.close()
            raise ApiError(400, "Ссылка сброса устарела", "TOKEN_EXPIRED")
        salt, digest = hash_password(password)
        conn.execute("UPDATE users SET password_salt=?, password_hash=?, updated_at=? WHERE id=?", (salt, digest, utc_now(), row["user_id"]))
        conn.execute("UPDATE one_time_tokens SET used_at=? WHERE id=?", (utc_now(), row["id"]))
        conn.execute("DELETE FROM sessions WHERE user_id=?", (row["user_id"],))
        self.audit(conn, row["user_id"], "password_reset", "user", str(row["user_id"]))
        conn.commit()
        conn.close()
        return self.send_json({"ok": True, "message": "Пароль обновлён. Войдите снова."})

    def get_products(self, query: dict[str, list[str]]):
        category = query.get("category", [""])[0]
        search = query.get("q", [""])[0].strip().lower()
        conn = connect()
        sql = "SELECT * FROM products WHERE status='active'"
        args: list[Any] = []
        if category:
            sql += " AND category=?"
            args.append(category)
        if search:
            sql += " AND (LOWER(title) LIKE ? OR LOWER(category) LIKE ? OR LOWER(description) LIKE ?)"
            like = f"%{search}%"
            args += [like, like, like]
        sql += " ORDER BY featured DESC, price DESC"
        rows = conn.execute(sql, args).fetchall()
        products = [public_product(r, conn) for r in rows]
        conn.close()
        return self.send_json({"ok": True, "products": products})

    def get_product(self, product_id: str):
        conn = connect()
        row = conn.execute("SELECT * FROM products WHERE id=? AND status='active'", (product_id,)).fetchone()
        if not row:
            conn.close()
            raise ApiError(404, "Лот не найден", "NOT_FOUND")
        product = public_product(row, conn)
        conn.close()
        return self.send_json({"ok": True, "product": product})

    def get_cart_payload(self, conn: sqlite3.Connection, user_id: int) -> dict:
        rows = conn.execute(
            """
            SELECT ci.product_id,ci.qty,p.*
            FROM cart_items ci JOIN products p ON p.id=ci.product_id
            WHERE ci.user_id=? AND p.status='active'
            ORDER BY ci.updated_at DESC
            """,
            (user_id,),
        ).fetchall()
        items = []
        subtotal = 0
        count = 0
        for r in rows:
            p = public_product(r, conn)
            qty = int(r["qty"])
            items.append({"product_id": r["product_id"], "qty": qty, "product": p, "line_total": p["price"] * qty})
            subtotal += p["price"] * qty
            count += qty
        insurance = max(900, round(subtotal * 0.01)) if count else 0
        shipping_fee = 0 if count else 0
        total = subtotal + insurance + shipping_fee
        return {"items": items, "subtotal": subtotal, "insurance": insurance, "shipping_fee": shipping_fee, "total": total, "count": count}

    def get_cart(self):
        user = self.current_user()
        conn = connect()
        payload = self.get_cart_payload(conn, user["id"])
        conn.close()
        return self.send_json({"ok": True, "cart": payload})

    def add_cart_item(self):
        user = self.current_user()
        data = self.read_json()
        product_id = (data.get("product_id") or "").strip()
        qty = max(1, min(99, int(data.get("qty") or 1)))
        conn = connect()
        product = conn.execute("SELECT id,stock FROM products WHERE id=? AND status='active'", (product_id,)).fetchone()
        if not product:
            conn.close()
            raise ApiError(404, "Лот не найден", "NOT_FOUND")
        existing = conn.execute("SELECT qty FROM cart_items WHERE user_id=? AND product_id=?", (user["id"], product_id)).fetchone()
        new_qty = qty + (int(existing["qty"]) if existing else 0)
        if new_qty > int(product["stock"]):
            conn.close()
            raise ApiError(409, "Недостаточно товара в наличии", "OUT_OF_STOCK")
        conn.execute(
            """
            INSERT INTO cart_items(user_id,product_id,qty,updated_at) VALUES(?,?,?,?)
            ON CONFLICT(user_id,product_id) DO UPDATE SET qty=excluded.qty, updated_at=excluded.updated_at
            """,
            (user["id"], product_id, new_qty, utc_now()),
        )
        conn.commit()
        payload = self.get_cart_payload(conn, user["id"])
        conn.close()
        return self.send_json({"ok": True, "cart": payload}, 201)

    def update_cart_item(self, product_id: str):
        user = self.current_user()
        data = self.read_json()
        qty = max(0, min(99, int(data.get("qty") or 0)))
        conn = connect()
        if qty == 0:
            conn.execute("DELETE FROM cart_items WHERE user_id=? AND product_id=?", (user["id"], product_id))
        else:
            product = conn.execute("SELECT stock FROM products WHERE id=? AND status='active'", (product_id,)).fetchone()
            if not product:
                conn.close()
                raise ApiError(404, "Лот не найден", "NOT_FOUND")
            if qty > int(product["stock"]):
                conn.close()
                raise ApiError(409, "Недостаточно товара в наличии", "OUT_OF_STOCK")
            conn.execute("UPDATE cart_items SET qty=?,updated_at=? WHERE user_id=? AND product_id=?", (qty, utc_now(), user["id"], product_id))
        conn.commit()
        payload = self.get_cart_payload(conn, user["id"])
        conn.close()
        return self.send_json({"ok": True, "cart": payload})

    def delete_cart_item(self, product_id: str):
        user = self.current_user()
        conn = connect()
        conn.execute("DELETE FROM cart_items WHERE user_id=? AND product_id=?", (user["id"], product_id))
        conn.commit()
        payload = self.get_cart_payload(conn, user["id"])
        conn.close()
        return self.send_json({"ok": True, "cart": payload})

    def get_favorites(self):
        user = self.current_user()
        conn = connect()
        rows = conn.execute("SELECT product_id FROM favorites WHERE user_id=? ORDER BY created_at DESC", (user["id"],)).fetchall()
        conn.close()
        return self.send_json({"ok": True, "favorites": [r["product_id"] for r in rows]})

    def add_favorite(self, product_id: str):
        user = self.current_user()
        conn = connect()
        product = conn.execute("SELECT id FROM products WHERE id=? AND status='active'", (product_id,)).fetchone()
        if not product:
            conn.close()
            raise ApiError(404, "Лот не найден", "NOT_FOUND")
        conn.execute("INSERT OR IGNORE INTO favorites(user_id,product_id,created_at) VALUES(?,?,?)", (user["id"], product_id, utc_now()))
        conn.commit()
        rows = conn.execute("SELECT product_id FROM favorites WHERE user_id=?", (user["id"],)).fetchall()
        conn.close()
        return self.send_json({"ok": True, "favorites": [r["product_id"] for r in rows]}, 201)

    def delete_favorite(self, product_id: str):
        user = self.current_user()
        conn = connect()
        conn.execute("DELETE FROM favorites WHERE user_id=? AND product_id=?", (user["id"], product_id))
        conn.commit()
        rows = conn.execute("SELECT product_id FROM favorites WHERE user_id=?", (user["id"],)).fetchall()
        conn.close()
        return self.send_json({"ok": True, "favorites": [r["product_id"] for r in rows]})

    def create_stripe_checkout(self, order_no: str, amount_minor: int, description: str, email: str) -> tuple[str, str]:
        if not STRIPE_SECRET_KEY:
            raise ApiError(503, "Stripe не настроен: добавьте STRIPE_SECRET_KEY в .env", "PAYMENT_NOT_CONFIGURED")
        data = {
            "mode": "payment",
            "success_url": f"{APP_URL}/payment-result.html?status=success&order={urllib.parse.quote(order_no)}&session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{APP_URL}/payment-result.html?status=cancel&order={urllib.parse.quote(order_no)}",
            "client_reference_id": order_no,
            "customer_email": email,
            "metadata[order_no]": order_no,
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": PAYMENT_CURRENCY,
            "line_items[0][price_data][unit_amount]": str(amount_minor),
            "line_items[0][price_data][product_data][name]": description[:180],
        }
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        req = urllib.request.Request("https://api.stripe.com/v1/checkout/sessions", data=encoded, method="POST")
        auth = base64.b64encode((STRIPE_SECRET_KEY + ":").encode()).decode()
        req.add_header("Authorization", "Basic " + auth)
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise ApiError(502, f"Ошибка платежного провайдера: {detail}", "PAYMENT_PROVIDER_ERROR")
        return payload.get("id", ""), payload.get("url", "")

    def checkout(self):
        user = self.current_user()
        data = self.read_json()
        shipping = data.get("shipping") if isinstance(data.get("shipping"), dict) else {}
        method = (data.get("payment_method") or PAYMENT_PROVIDER or "manual").lower()
        required = ["name", "email", "phone", "address"]
        if any(not str(shipping.get(k, "")).strip() for k in required):
            raise ApiError(400, "Заполните имя, email, телефон и адрес доставки", "VALIDATION")
        if not valid_email(str(shipping.get("email", ""))):
            raise ApiError(400, "Введите корректный email", "VALIDATION")
        conn = connect()
        try:
            payload = self.get_cart_payload(conn, user["id"])
            if not payload["items"]:
                raise ApiError(400, "Корзина пуста", "EMPTY_CART")
            for item in payload["items"]:
                product = conn.execute("SELECT stock FROM products WHERE id=?", (item["product_id"],)).fetchone()
                if not product or int(product["stock"]) < item["qty"]:
                    raise ApiError(409, f"Недостаточно товара: {item['product']['title']}", "OUT_OF_STOCK")
            order_no = "CV-" + datetime.now().strftime("%Y%m%d") + "-" + secrets.token_hex(3).upper()
            cur = conn.execute(
                """
                INSERT INTO orders(order_no,user_id,total,subtotal,insurance,shipping_fee,status,payment_status,payment_provider,shipping_json,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (order_no, user["id"], payload["total"], payload["subtotal"], payload["insurance"], payload["shipping_fee"], "pending_payment", "awaiting_payment", method, json.dumps(shipping, ensure_ascii=False), utc_now(), utc_now()),
            )
            order_id = cur.lastrowid
            for item in payload["items"]:
                p = item["product"]
                conn.execute("INSERT INTO order_items(order_id,product_id,title,qty,price) VALUES(?,?,?,?,?)", (order_id, p["id"], p["title"], item["qty"], p["price"]))
                conn.execute("UPDATE products SET stock=stock-?,updated_at=? WHERE id=?", (item["qty"], utc_now(), p["id"]))
            conn.execute("INSERT INTO shipment_events(order_id,title,description,created_at) VALUES(?,?,?,?)", (order_id, "Заказ создан", "Лоты зарезервированы до оплаты.", utc_now()))
            conn.execute("DELETE FROM cart_items WHERE user_id=?", (user["id"],))
            self.audit(conn, user["id"], "checkout", "order", order_no, {"total": payload["total"], "method": method})
            conn.commit()
        except ApiError:
            conn.rollback()
            conn.close()
            raise

        payment_url = ""
        payment_session_id = ""
        if method == "stripe":
            try:
                # Stripe expects the amount in minor units. For zero-decimal currencies, configure PAYMENT_CURRENCY/amount externally.
                payment_session_id, payment_url = self.create_stripe_checkout(order_no, int(payload["total"]), f"CardVault заказ {order_no}", shipping["email"])
                conn.execute("UPDATE orders SET payment_session_id=?, payment_url=?, updated_at=? WHERE id=?", (payment_session_id, payment_url, utc_now(), order_id))
                conn.commit()
            except ApiError:
                conn.close()
                raise
        else:
            payment_url = f"{APP_URL}/payment-result.html?status=manual&order={urllib.parse.quote(order_no)}"
            conn.execute("UPDATE orders SET payment_url=?, updated_at=? WHERE id=?", (payment_url, utc_now(), order_id))
            conn.commit()
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        conn.close()
        return self.send_json({"ok": True, "order": self.order_public(order), "payment_url": payment_url, "payment_session_id": payment_session_id}, 201)

    def order_public(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "order_no": row["order_no"],
            "total": int(row["total"]),
            "subtotal": int(row["subtotal"]),
            "insurance": int(row["insurance"]),
            "shipping_fee": int(row["shipping_fee"]),
            "status": row["status"],
            "payment_status": row["payment_status"],
            "payment_provider": row["payment_provider"],
            "payment_url": row["payment_url"],
            "tracking_number": row["tracking_number"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def get_orders(self):
        user = self.current_user()
        conn = connect()
        rows = conn.execute("SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC", (user["id"],)).fetchall()
        orders = []
        for o in rows:
            items = conn.execute("SELECT product_id,title,qty,price FROM order_items WHERE order_id=?", (o["id"],)).fetchall()
            events = conn.execute("SELECT title,description,created_at FROM shipment_events WHERE order_id=? ORDER BY id", (o["id"],)).fetchall()
            d = self.order_public(o)
            d["items"] = [dict(i) for i in items]
            d["events"] = [dict(e) for e in events]
            orders.append(d)
        conn.close()
        return self.send_json({"ok": True, "orders": orders})

    def stripe_webhook(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        sig = self.headers.get("Stripe-Signature", "")
        if STRIPE_WEBHOOK_SECRET:
            try:
                parts = dict(part.split("=", 1) for part in sig.split(",") if "=" in part)
                timestamp = parts.get("t", "")
                v1 = parts.get("v1", "")
                signed = timestamp.encode() + b"." + raw
                expected = hmac.new(STRIPE_WEBHOOK_SECRET.encode(), signed, hashlib.sha256).hexdigest()
                if not timestamp or not v1 or not hmac.compare_digest(expected, v1):
                    raise ValueError("bad signature")
            except Exception:
                raise ApiError(400, "Некорректная подпись Stripe", "BAD_SIGNATURE")
        event = json.loads(raw.decode("utf-8"))
        event_type = event.get("type")
        obj = event.get("data", {}).get("object", {})
        order_no = obj.get("client_reference_id") or obj.get("metadata", {}).get("order_no")
        if event_type == "checkout.session.completed" and order_no:
            conn = connect()
            order = conn.execute("SELECT id,user_id FROM orders WHERE order_no=?", (order_no,)).fetchone()
            if order:
                conn.execute("UPDATE orders SET payment_status='paid',status='paid',updated_at=? WHERE order_no=?", (utc_now(), order_no))
                conn.execute("INSERT INTO shipment_events(order_id,title,description,created_at) VALUES(?,?,?,?)", (order["id"], "Оплата получена", "Платеж подтвержден Stripe Checkout.", utc_now()))
                self.audit(conn, order["user_id"], "stripe_paid", "order", order_no)
                conn.commit()
            conn.close()
        return self.send_json({"ok": True})

    def upload_files(self):
        user = self.current_user(required=False)
        data = self.read_json()
        purpose = (data.get("purpose") or "sell_request").strip()[:40]
        files = data.get("files")
        if not isinstance(files, list) or not files:
            raise ApiError(400, "Добавьте хотя бы один файл", "VALIDATION")
        if len(files) > 8:
            raise ApiError(400, "Максимум 8 файлов за раз", "VALIDATION")
        saved = []
        conn = connect()
        try:
            for item in files:
                if not isinstance(item, dict):
                    continue
                name = (item.get("name") or "image").strip()[:120]
                data_url = item.get("data_url") or ""
                m = re.match(r"^data:(image/(png|jpeg|jpg|webp));base64,(.+)$", data_url, re.I | re.S)
                if not m:
                    raise ApiError(400, "Разрешены только изображения PNG, JPG или WEBP", "BAD_FILE")
                mime = m.group(1).lower().replace("image/jpg", "image/jpeg")
                raw = base64.b64decode(m.group(3), validate=True)
                if len(raw) > MAX_UPLOAD_BYTES:
                    raise ApiError(413, "Файл слишком большой", "FILE_TOO_LARGE")
                ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[mime]
                day = datetime.now().strftime("%Y/%m/%d")
                dest_dir = UPLOAD_DIR / day
                dest_dir.mkdir(parents=True, exist_ok=True)
                stored = secrets.token_hex(16) + ext
                path = dest_dir / stored
                path.write_bytes(raw)
                url = "/uploads/" + day + "/" + stored
                cur = conn.execute(
                    "INSERT INTO uploads(user_id,original_name,stored_name,url,mime,size,purpose,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (user["id"] if user else None, name, stored, url, mime, len(raw), purpose, utc_now()),
                )
                saved.append({"id": cur.lastrowid, "url": url, "name": name, "mime": mime, "size": len(raw)})
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return self.send_json({"ok": True, "uploads": saved}, 201)

    def create_sell_request(self):
        user = self.current_user()
        data = self.read_json()
        card = (data.get("card") or "").strip()
        category = (data.get("category") or "").strip()
        price = (data.get("price") or "").strip()
        photos = data.get("photos") if isinstance(data.get("photos"), list) else []
        if not card or not category or not price:
            raise ApiError(400, "Укажите название карты, категорию и цену", "VALIDATION")
        conn = connect()
        cur = conn.execute(
            """
            INSERT INTO sell_requests(user_id,card,category,grade,price,message,photos_json,status,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (user["id"], card[:180], category[:80], (data.get("grade") or "")[:60], price[:80], (data.get("message") or "")[:1500], json.dumps(photos[:8], ensure_ascii=False), "new", utc_now(), utc_now()),
        )
        self.audit(conn, user["id"], "sell_request_created", "sell_request", str(cur.lastrowid))
        conn.commit()
        request_id = cur.lastrowid
        conn.close()
        return self.send_json({"ok": True, "request": {"id": request_id, "status": "new"}}, 201)

    def create_verification_request(self):
        user = self.current_user(required=False)
        data = self.read_json()
        card = (data.get("card") or "").strip()
        email = (data.get("email") or (user or {}).get("email") or "").strip().lower()
        photos = data.get("photos") if isinstance(data.get("photos"), list) else []
        if not card or not valid_email(email):
            raise ApiError(400, "Укажите карту и корректный email", "VALIDATION")
        conn = connect()
        cur = conn.execute(
            "INSERT INTO verification_requests(user_id,card,email,photos_json,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (user["id"] if user else None, card[:180], email, json.dumps(photos[:8], ensure_ascii=False), "new", utc_now(), utc_now()),
        )
        self.audit(conn, user["id"] if user else None, "verification_request_created", "verification_request", str(cur.lastrowid))
        conn.commit()
        request_id = cur.lastrowid
        conn.close()
        return self.send_json({"ok": True, "request": {"id": request_id, "status": "new"}}, 201)

    def get_stats(self):
        conn = connect()
        sold = conn.execute("SELECT COALESCE(SUM(qty),0) AS c FROM order_items").fetchone()["c"]
        orders = conn.execute("SELECT COUNT(*) AS c FROM orders").fetchone()["c"]
        users = conn.execute("SELECT COUNT(*) AS c FROM users WHERE role='customer'").fetchone()["c"]
        avg = conn.execute("SELECT ROUND(AVG(rating),1) AS r, COUNT(*) AS c FROM reviews WHERE is_public=1").fetchone()
        active_products = conn.execute("SELECT COUNT(*) AS c FROM products WHERE status='active'").fetchone()["c"]
        conn.close()
        return self.send_json({"ok": True, "stats": {"sold_cards": int(sold) + 129487, "orders": int(orders), "verified_sellers": 8742, "positive_reviews": 25318, "countries": 96, "registered_customers": int(users), "rating": float(avg["r"] or 4.9), "review_count": int(avg["c"] or 0) + 25318, "active_products": int(active_products)}})

    def get_reviews(self):
        conn = connect()
        rows = conn.execute("SELECT author,city,rating,text,created_at FROM reviews WHERE is_public=1 ORDER BY id DESC LIMIT 20").fetchall()
        conn.close()
        return self.send_json({"ok": True, "reviews": [dict(r) for r in rows]})

    # Admin API
    def admin_dashboard(self):
        admin = self.current_user(admin=True)
        conn = connect()
        dashboard = {
            "orders": conn.execute("SELECT COUNT(*) AS c FROM orders").fetchone()["c"],
            "awaiting_payment": conn.execute("SELECT COUNT(*) AS c FROM orders WHERE payment_status='awaiting_payment'").fetchone()["c"],
            "paid": conn.execute("SELECT COUNT(*) AS c FROM orders WHERE payment_status='paid'").fetchone()["c"],
            "sell_requests": conn.execute("SELECT COUNT(*) AS c FROM sell_requests WHERE status IN ('new','review')").fetchone()["c"],
            "verification_requests": conn.execute("SELECT COUNT(*) AS c FROM verification_requests WHERE status IN ('new','review')").fetchone()["c"],
            "products": conn.execute("SELECT COUNT(*) AS c FROM products WHERE status='active'").fetchone()["c"],
            "revenue": conn.execute("SELECT COALESCE(SUM(total),0) AS c FROM orders WHERE payment_status='paid'").fetchone()["c"],
        }
        self.audit(conn, admin["id"], "admin_dashboard")
        conn.commit()
        conn.close()
        return self.send_json({"ok": True, "dashboard": dashboard})

    def admin_products(self):
        self.current_user(admin=True)
        conn = connect()
        rows = conn.execute("SELECT * FROM products ORDER BY updated_at DESC").fetchall()
        products = [public_product(r, conn) for r in rows]
        conn.close()
        return self.send_json({"ok": True, "products": products})

    def admin_create_product(self):
        admin = self.current_user(admin=True)
        data = self.read_json()
        title = (data.get("title") or "").strip()
        if not title:
            raise ApiError(400, "Название обязательно", "VALIDATION")
        product_id = slugify(data.get("id") or title)[:60]
        conn = connect()
        if conn.execute("SELECT id FROM products WHERE id=?", (product_id,)).fetchone():
            conn.close()
            product_id += "-" + secrets.token_hex(3)
        p = self.clean_product_payload(data)
        conn.execute(
            """
            INSERT INTO products(id,title,category,grade,price,stock,description,seller_name,seller_rating,status,featured,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (product_id, p["title"], p["category"], p["grade"], p["price"], p["stock"], p["description"], p["seller_name"], p["seller_rating"], p["status"], p["featured"], utc_now(), utc_now()),
        )
        for i, img in enumerate(data.get("images") if isinstance(data.get("images"), list) else []):
            if isinstance(img, dict) and img.get("url"):
                conn.execute("INSERT INTO product_images(product_id,url,alt,sort_order,created_at) VALUES(?,?,?,?,?)", (product_id, img["url"], img.get("alt") or title, i, utc_now()))
        self.audit(conn, admin["id"], "product_created", "product", product_id)
        conn.commit()
        row = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        product = public_product(row, conn)
        conn.close()
        return self.send_json({"ok": True, "product": product}, 201)

    def clean_product_payload(self, data: dict) -> dict:
        return {
            "title": (data.get("title") or "").strip()[:220],
            "category": (data.get("category") or "Другое").strip()[:80],
            "grade": (data.get("grade") or "RAW").strip()[:60],
            "price": max(0, int(data.get("price") or 0)),
            "stock": max(0, int(data.get("stock") or 0)),
            "description": (data.get("description") or "").strip()[:2500],
            "seller_name": (data.get("seller_name") or "CardVault").strip()[:120],
            "seller_rating": max(0, min(5, float(data.get("seller_rating") or 4.9))),
            "status": data.get("status") if data.get("status") in ("active", "draft", "archived") else "active",
            "featured": 1 if data.get("featured") else 0,
        }

    def admin_update_product(self, product_id: str):
        admin = self.current_user(admin=True)
        data = self.read_json()
        p = self.clean_product_payload(data)
        conn = connect()
        if not conn.execute("SELECT id FROM products WHERE id=?", (product_id,)).fetchone():
            conn.close()
            raise ApiError(404, "Лот не найден", "NOT_FOUND")
        conn.execute(
            """
            UPDATE products SET title=?,category=?,grade=?,price=?,stock=?,description=?,seller_name=?,seller_rating=?,status=?,featured=?,updated_at=? WHERE id=?
            """,
            (p["title"], p["category"], p["grade"], p["price"], p["stock"], p["description"], p["seller_name"], p["seller_rating"], p["status"], p["featured"], utc_now(), product_id),
        )
        if isinstance(data.get("images"), list):
            conn.execute("DELETE FROM product_images WHERE product_id=?", (product_id,))
            for i, img in enumerate(data["images"]):
                if isinstance(img, dict) and img.get("url"):
                    conn.execute("INSERT INTO product_images(product_id,url,alt,sort_order,created_at) VALUES(?,?,?,?,?)", (product_id, img["url"], img.get("alt") or p["title"], i, utc_now()))
        self.audit(conn, admin["id"], "product_updated", "product", product_id)
        conn.commit()
        row = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        product = public_product(row, conn)
        conn.close()
        return self.send_json({"ok": True, "product": product})

    def admin_delete_product(self, product_id: str):
        admin = self.current_user(admin=True)
        conn = connect()
        conn.execute("UPDATE products SET status='archived',updated_at=? WHERE id=?", (utc_now(), product_id))
        self.audit(conn, admin["id"], "product_archived", "product", product_id)
        conn.commit()
        conn.close()
        return self.send_json({"ok": True})

    def admin_orders(self):
        self.current_user(admin=True)
        conn = connect()
        rows = conn.execute("SELECT o.*,u.email,u.name FROM orders o JOIN users u ON u.id=o.user_id ORDER BY o.created_at DESC LIMIT 300").fetchall()
        orders = []
        for row in rows:
            d = dict(row)
            d["shipping"] = json.loads(row["shipping_json"] or "{}")
            d["items"] = [dict(i) for i in conn.execute("SELECT product_id,title,qty,price FROM order_items WHERE order_id=?", (row["id"],)).fetchall()]
            d["events"] = [dict(e) for e in conn.execute("SELECT title,description,created_at FROM shipment_events WHERE order_id=? ORDER BY id", (row["id"],)).fetchall()]
            orders.append(d)
        conn.close()
        return self.send_json({"ok": True, "orders": orders})

    def admin_update_order(self, order_id: int):
        admin = self.current_user(admin=True)
        data = self.read_json()
        allowed_status = {"pending_payment", "paid", "authentication", "packing", "shipped", "delivered", "cancelled", "refunded"}
        allowed_payment = {"awaiting_payment", "paid", "failed", "refunded"}
        conn = connect()
        row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            conn.close()
            raise ApiError(404, "Заказ не найден", "NOT_FOUND")
        status = data.get("status") if data.get("status") in allowed_status else row["status"]
        payment_status = data.get("payment_status") if data.get("payment_status") in allowed_payment else row["payment_status"]
        tracking = (data.get("tracking_number") if data.get("tracking_number") is not None else row["tracking_number"]) or ""
        conn.execute("UPDATE orders SET status=?,payment_status=?,tracking_number=?,updated_at=? WHERE id=?", (status, payment_status, tracking[:120], utc_now(), order_id))
        note = (data.get("event") or "").strip()
        if note:
            conn.execute("INSERT INTO shipment_events(order_id,title,description,created_at) VALUES(?,?,?,?)", (order_id, note[:160], (data.get("event_description") or "")[:600], utc_now()))
        self.audit(conn, admin["id"], "order_updated", "order", str(order_id), data)
        conn.commit()
        conn.close()
        return self.send_json({"ok": True})

    def admin_sell_requests(self):
        self.current_user(admin=True)
        conn = connect()
        rows = conn.execute("SELECT sr.*,u.email,u.name FROM sell_requests sr JOIN users u ON u.id=sr.user_id ORDER BY sr.created_at DESC LIMIT 300").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["photos"] = json.loads(d.pop("photos_json") or "[]")
            out.append(d)
        conn.close()
        return self.send_json({"ok": True, "sell_requests": out})

    def admin_update_sell_request(self, request_id: int):
        admin = self.current_user(admin=True)
        data = self.read_json()
        status = data.get("status") if data.get("status") in ("new", "review", "approved", "rejected", "published") else "review"
        note = (data.get("admin_note") or "").strip()[:1000]
        conn = connect()
        if not conn.execute("SELECT id FROM sell_requests WHERE id=?", (request_id,)).fetchone():
            conn.close()
            raise ApiError(404, "Заявка не найдена", "NOT_FOUND")
        conn.execute("UPDATE sell_requests SET status=?,admin_note=?,updated_at=? WHERE id=?", (status, note, utc_now(), request_id))
        self.audit(conn, admin["id"], "sell_request_updated", "sell_request", str(request_id), data)
        conn.commit()
        conn.close()
        return self.send_json({"ok": True})

    def admin_verification_requests(self):
        self.current_user(admin=True)
        conn = connect()
        rows = conn.execute("SELECT * FROM verification_requests ORDER BY created_at DESC LIMIT 300").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["photos"] = json.loads(d.pop("photos_json") or "[]")
            out.append(d)
        conn.close()
        return self.send_json({"ok": True, "verification_requests": out})

    def admin_update_verification_request(self, request_id: int):
        admin = self.current_user(admin=True)
        data = self.read_json()
        status = data.get("status") if data.get("status") in ("new", "review", "authentic", "not_authentic", "need_more_photos") else "review"
        note = (data.get("admin_note") or "").strip()[:1000]
        conn = connect()
        if not conn.execute("SELECT id FROM verification_requests WHERE id=?", (request_id,)).fetchone():
            conn.close()
            raise ApiError(404, "Заявка не найдена", "NOT_FOUND")
        conn.execute("UPDATE verification_requests SET status=?,admin_note=?,updated_at=? WHERE id=?", (status, note, utc_now(), request_id))
        self.audit(conn, admin["id"], "verification_request_updated", "verification_request", str(request_id), data)
        conn.commit()
        conn.close()
        return self.send_json({"ok": True})


def main() -> None:
    create_schema()
    seed_data()
    server = ThreadingHTTPServer((HOST, PORT), CardVaultHandler)
    print(f"CardVault Pro is running: http://localhost:{PORT}")
    print(f"Database: {DB_PATH}")
    print(f"Admin login: {INITIAL_ADMIN_EMAIL} / {INITIAL_ADMIN_PASSWORD}")
    print("Change SECRET_KEY and admin password before production launch.")
    server.serve_forever()


if __name__ == "__main__":
    main()
