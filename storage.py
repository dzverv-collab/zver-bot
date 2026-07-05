"""
ZVER Store CRM — Data storage layer
Handles applications.json, customers.json, data.json (counter)
"""

import csv
import io
import json
from datetime import datetime, timedelta
from pathlib import Path

APPS_FILE = Path("applications.json")
CUSTOMERS_FILE = Path("customers.json")
DATA_FILE = Path("data.json")


# ── Low-level I/O ──────────────────────────────────────────────────────────────

def _load(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


def _save(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Application counter ────────────────────────────────────────────────────────

def next_app_id() -> str:
    data = _load(DATA_FILE, {"counter": 0})
    data["counter"] = data.get("counter", 0) + 1
    app_id = f"ZV-{data['counter']:04d}"
    _save(DATA_FILE, data)
    return app_id


# ── Applications ───────────────────────────────────────────────────────────────

def load_applications() -> list:
    return _load(APPS_FILE, [])


def save_application(app: dict) -> None:
    apps = load_applications()
    apps.append(app)
    _save(APPS_FILE, apps)


def get_application(app_id: str) -> dict | None:
    for app in load_applications():
        if app.get("app_id") == app_id:
            return app
    return None


def update_application(app_id: str, **kwargs) -> None:
    apps = load_applications()
    for app in apps:
        if app.get("app_id") == app_id:
            app.update(kwargs)
            break
    _save(APPS_FILE, apps)


def get_app_status(app_id: str) -> str:
    app = get_application(app_id)
    return app.get("status", "") if app else ""


# ── Customers ──────────────────────────────────────────────────────────────────

def load_customers() -> dict:
    return _load(CUSTOMERS_FILE, {})


def get_customer(user_id: int) -> dict | None:
    return load_customers().get(str(user_id))


def upsert_customer(
    user_id: int,
    username: str,
    full_name: str,
    app_id: str,
    date: str,
    model: str,
) -> None:
    customers = load_customers()
    uid = str(user_id)
    if uid not in customers:
        customers[uid] = {
            "user_id": user_id,
            "username": username,
            "full_name": full_name,
            "app_count": 0,
            "last_app_date": date,
            "app_ids": [],
            "models": [],
        }
    c = customers[uid]
    c["app_count"] = c.get("app_count", 0) + 1
    c["last_app_date"] = date
    c["username"] = username
    c["full_name"] = full_name
    c.setdefault("app_ids", []).append(app_id)
    if model:
        c.setdefault("models", []).append(model)
    _save(CUSTOMERS_FILE, customers)


def find_customer(identifier: str) -> dict | None:
    """Find by user_id (numeric) or @username."""
    customers = load_customers()
    ident = identifier.lstrip("@").lower()
    for c in customers.values():
        if str(c.get("user_id")) == ident or (c.get("username") or "").lower() == ident:
            return c
    return None


# ── Search applications ────────────────────────────────────────────────────────

def find_applications(query: str) -> list:
    """Search by app_id, @username, user_id, or contact (phone/text)."""
    apps = load_applications()
    q = query.strip().lower()
    q_plain = q.lstrip("@").lstrip("+").replace(" ", "").replace("-", "")
    results = []
    for app in reversed(apps):
        contact_plain = (
            (app.get("contact") or "")
            .replace("+", "").replace(" ", "").replace("-", "").lower()
        )
        if (
            app.get("app_id", "").lower() == q
            or (app.get("username") or "").lower() == q.lstrip("@")
            or str(app.get("user_id", "")) == q_plain
            or (q_plain and q_plain in contact_plain)
        ):
            results.append(app)
        if len(results) >= 10:
            break
    return results


# ── Stats ──────────────────────────────────────────────────────────────────────

def _parse_app_date(app: dict):
    try:
        return datetime.strptime(app["date"], "%d.%m.%Y %H:%M").date()
    except Exception:
        return None


def get_stats() -> dict:
    apps = load_applications()
    now = datetime.now()
    today = now.date()

    def _filter(days: int | None):
        if days is None:
            return [a for a in apps if _parse_app_date(a) == today]
        cutoff = (now - timedelta(days=days)).date()
        return [a for a in apps if (d := _parse_app_date(a)) and d >= cutoff]

    def _compute(subset: list) -> dict:
        total = len(subset)
        done = sum(1 for a in subset if a.get("status") == "done")
        rejected = sum(1 for a in subset if a.get("status") == "rejected")
        working = sum(1 for a in subset if a.get("status") == "working")
        agreed = sum(1 for a in subset if a.get("status") == "agreed")
        conv = round(done / total * 100) if total else 0
        prices = [
            a["deal_price"]
            for a in subset
            if a.get("deal_price") and isinstance(a["deal_price"], (int, float))
        ]
        return {
            "total": total,
            "done": done,
            "rejected": rejected,
            "working": working,
            "agreed": agreed,
            "conversion": conv,
            "price_count": len(prices),
            "total_price": int(sum(prices)),
            "avg_price": int(sum(prices) / len(prices)) if prices else 0,
        }

    return {
        "today": _compute(_filter(None)),
        "week": _compute(_filter(7)),
        "month": _compute(_filter(30)),
    }


# ── CSV export ─────────────────────────────────────────────────────────────────

_EXPORT_FIELDS = [
    "application_id", "date", "status", "client_name", "username", "user_id",
    "device_type", "model", "memory", "battery", "color", "condition",
    "defects", "city", "contact", "deal_price",
]


def export_csv() -> bytes:
    apps = load_applications()
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_EXPORT_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for app in apps:
        defects = app.get("defects", [])
        writer.writerow({
            "application_id": app.get("app_id", ""),
            "date": app.get("date", ""),
            "status": app.get("status", ""),
            "client_name": app.get("full_name", ""),
            "username": app.get("username", ""),
            "user_id": app.get("user_id", ""),
            "device_type": app.get("device", ""),
            "model": app.get("model", ""),
            "memory": app.get("memory", ""),
            "battery": app.get("battery", ""),
            "color": app.get("color", ""),
            "condition": app.get("condition", ""),
            "defects": "; ".join(defects) if isinstance(defects, list) else str(defects),
            "city": app.get("city", ""),
            "contact": app.get("contact", ""),
            "deal_price": app.get("deal_price", ""),
        })
    return buf.getvalue().encode("utf-8-sig")  # BOM for Excel


# ── Customer card ──────────────────────────────────────────────────────────────

def get_customer_card(identifier: str) -> dict | None:
    customer = find_customer(identifier)
    if not customer:
        return None
    apps = load_applications()
    uid = str(customer["user_id"])
    customer_apps = [a for a in apps if str(a.get("user_id")) == uid]
    done_apps = [a for a in customer_apps if a.get("status") == "done"]
    prices = [
        a["deal_price"]
        for a in done_apps
        if a.get("deal_price") and isinstance(a["deal_price"], (int, float))
    ]
    return {
        **customer,
        "total_apps": len(customer_apps),
        "done_count": len(done_apps),
        "total_price": int(sum(prices)),
        "last_3_models": (customer.get("models") or [])[-3:],
    }
