from datetime import datetime, timedelta, timezone

import settings


def _row_dict(row) -> dict:
    return {key: row[key] for key in row.keys()}


def get_overview() -> dict:
    db = settings.connect()
    try:
        clients = [_row_dict(r) for r in db.execute("SELECT * FROM clients")]
    finally:
        db.close()
    now = datetime.now(timezone.utc)
    month_prefix = now.strftime("%Y-%m")
    active = [c for c in clients if c["status"] == "active"]
    pending = [c for c in clients if c["status"] == "pending"]
    expired = [c for c in clients if c["status"] == "expired"]
    rejected = [c for c in clients if c["status"] == "rejected"]
    revenue_month = sum(
        (c["amount_usd"] or 0)
        for c in active
        if (c["hired_at"] or "").startswith(month_prefix)
    )
    revenue_total = sum((c["amount_usd"] or 0) for c in active)
    by_plan = {}
    for c in active:
        plan = c["plan"] or "unknown"
        by_plan[plan] = by_plan.get(plan, 0) + 1
    by_method = {}
    for c in clients:
        if c["status"] in ("active", "pending"):
            method = c["method"] or "unknown"
            by_method[method] = by_method.get(method, 0) + 1
    return {
        "total": len(clients),
        "active": len(active),
        "pending": len(pending),
        "expired": len(expired),
        "rejected": len(rejected),
        "revenue_month": round(revenue_month, 2),
        "revenue_total": round(revenue_total, 2),
        "by_plan": by_plan,
        "by_method": by_method,
    }


def get_sales(days: int = 30) -> list[dict]:
    days = max(1, min(days, 365))
    db = settings.connect()
    try:
        rows = db.execute(
            "SELECT hired_at, amount_usd FROM clients WHERE status = 'active'"
        ).fetchall()
    finally:
        db.close()
    today = datetime.now(timezone.utc).date()
    buckets: dict[str, dict] = {}
    for i in range(days):
        day = (today - timedelta(days=days - 1 - i)).isoformat()
        buckets[day] = {"date": day, "revenue": 0.0, "sales": 0}
    for hired_at, amount in rows:
        if not hired_at:
            continue
        day = hired_at[:10]
        if day in buckets:
            buckets[day]["revenue"] += amount or 0
            buckets[day]["sales"] += 1
    out = []
    for day in sorted(buckets):
        b = buckets[day]
        out.append({"date": b["date"], "revenue": round(b["revenue"], 2), "sales": b["sales"]})
    return out


def get_clients(status: str | None = None) -> list[dict]:
    db = settings.connect()
    try:
        if status:
            rows = db.execute(
                "SELECT * FROM clients WHERE status = ? ORDER BY hired_at DESC", (status,)
            ).fetchall()
        else:
            rows = db.execute("SELECT * FROM clients ORDER BY hired_at DESC").fetchall()
        return [_row_dict(r) for r in rows]
    finally:
        db.close()


def get_settings() -> dict:
    db = settings.connect()
    try:
        demo = db.execute("SELECT value FROM settings WHERE key = 'demo_mode'").fetchone()
        daily = db.execute("SELECT value FROM settings WHERE key = 'daily_amount'").fetchone()
    finally:
        db.close()
    return {
        "demo_mode": (demo[0] == "true") if demo else False,
        "daily_amount": float(daily[0]) if daily else 25.0,
    }
