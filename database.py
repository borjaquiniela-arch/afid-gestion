"""
TempoFacture — Contrôle horaire et facturation
Base de données SQLite
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("AFID_DATA", APP_DIR / "data"))
DB_PATH = DATA_DIR / "tempofacture.db"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return date.today().isoformat()


@contextmanager
def get_conn():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                address TEXT DEFAULT '',
                postal_code TEXT DEFAULT '',
                city TEXT DEFAULT '',
                country TEXT DEFAULT 'France',
                email TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                siret TEXT DEFAULT '',
                tva_intra TEXT DEFAULT '',
                hourly_rate_ht REAL NOT NULL DEFAULT 50,
                tva_rate REAL NOT NULL DEFAULT 20,
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS time_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                work_date TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL,
                hourly_rate_ht REAL NOT NULL,
                tva_rate REAL NOT NULL,
                billable INTEGER NOT NULL DEFAULT 1,
                invoice_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE,
                FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                number TEXT NOT NULL UNIQUE,
                client_id INTEGER NOT NULL,
                issue_date TEXT NOT NULL,
                due_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'brouillon',
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                apply_tva INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS timer (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                client_id INTEGER,
                description TEXT DEFAULT '',
                started_at TEXT,
                FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL
            );
            """
        )
        defaults = {
            "company_name": "A-fid comptabilité",
            "company_legal_form": "",
            "company_address": "Rue Es Crès 3",
            "company_postal_code": "2830",
            "company_city": "Courrendlin",
            "company_country": "Suisse",
            "company_email": "",
            "company_phone": "",
            "company_siret": "",
            "company_tva": "",
            "company_iban": "",
            "company_bic": "",
            "payment_days": "30",
            "invoice_prefix": "FACT",
            "next_invoice_seq": "1",
            "default_hourly_rate": "50",
            "default_tva_rate": "8.1",
            "tva_franchise": "1",
            "billing_tva": "sans",
            "access_code": "",
            "invoice_footer": "En cas de retard de paiement, un intérêt moratoire et les frais de recouvrement pourront être exigés.",
        }
        for key, value in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        identity = {
            "company_name": "A-fid comptabilité",
            "company_address": "Rue Es Crès 3",
            "company_postal_code": "2830",
            "company_city": "Courrendlin",
            "company_country": "Suisse",
        }
        for key, value in identity.items():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
        conn.execute("INSERT OR IGNORE INTO timer (id, client_id, description, started_at) VALUES (1, NULL, '', NULL)")
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(invoices)").fetchall()]
        if "apply_tva" not in cols:
            conn.execute("ALTER TABLE invoices ADD COLUMN apply_tva INTEGER NOT NULL DEFAULT 0")


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def get_settings() -> dict:
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def applies_tva(settings: dict | None = None) -> bool:
    s = settings or get_settings()
    mode = str(s.get("billing_tva") or "").lower()
    if mode == "sans":
        return False
    if mode == "avec":
        return True
    return str(s.get("tva_franchise") or "0") not in ("1", "true", "True")


def save_settings(data: dict) -> dict:
    allowed = {
        "company_name",
        "company_legal_form",
        "company_address",
        "company_postal_code",
        "company_city",
        "company_country",
        "company_email",
        "company_phone",
        "company_siret",
        "company_tva",
        "company_iban",
        "company_bic",
        "payment_days",
        "invoice_prefix",
        "default_hourly_rate",
        "default_tva_rate",
        "tva_franchise",
        "billing_tva",
        "access_code",
        "invoice_footer",
    }
    if "billing_tva" in data:
        mode = "sans" if str(data.get("billing_tva")).lower() in ("sans", "0", "false") else "avec"
        data = {**data, "billing_tva": mode, "tva_franchise": "1" if mode == "sans" else "0"}
    with get_conn() as conn:
        for key, value in data.items():
            if key in allowed:
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, str(value) if value is not None else ""),
                )
    return get_settings()


def list_clients() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.*,
                   COALESCE((
                       SELECT SUM(duration_minutes)
                       FROM time_entries e
                       WHERE e.client_id = c.id
                   ), 0) AS total_minutes,
                   COALESCE((
                       SELECT SUM(duration_minutes)
                       FROM time_entries e
                       WHERE e.client_id = c.id AND e.billable = 1 AND e.invoice_id IS NULL
                   ), 0) AS unbilled_minutes
            FROM clients c
            ORDER BY c.name COLLATE NOCASE
            """
        ).fetchall()
    return [row_to_dict(r) for r in rows]


def get_client(client_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    return row_to_dict(row)


def create_client(data: dict) -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO clients (
                name, address, postal_code, city, country, email, phone,
                siret, tva_intra, hourly_rate_ht, tva_rate, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (data.get("name") or "").strip(),
                data.get("address") or "",
                data.get("postal_code") or "",
                data.get("city") or "",
                data.get("country") or "France",
                data.get("email") or "",
                data.get("phone") or "",
                data.get("siret") or "",
                data.get("tva_intra") or "",
                float(data.get("hourly_rate_ht") or 50),
                0.0 if not applies_tva() else float(data.get("tva_rate") if data.get("tva_rate") not in (None, "") else (get_settings().get("default_tva_rate") or 8.1)),
                data.get("notes") or "",
                _now(),
            ),
        )
        cid = cur.lastrowid
    return get_client(cid)


def update_client(client_id: int, data: dict) -> dict | None:
    if not get_client(client_id):
        return None
    fields = [
        "name",
        "address",
        "postal_code",
        "city",
        "country",
        "email",
        "phone",
        "siret",
        "tva_intra",
        "hourly_rate_ht",
        "tva_rate",
        "notes",
    ]
    sets = []
    values = []
    for f in fields:
        if f in data:
            sets.append(f"{f} = ?")
            values.append(data[f])
    if sets:
        values.append(client_id)
        with get_conn() as conn:
            conn.execute(f"UPDATE clients SET {', '.join(sets)} WHERE id = ?", values)
    return get_client(client_id)


def delete_client(client_id: int) -> bool:
    with get_conn() as conn:
        used = conn.execute(
            "SELECT COUNT(*) AS n FROM invoices WHERE client_id = ?", (client_id,)
        ).fetchone()["n"]
        if used:
            return False
        conn.execute("DELETE FROM time_entries WHERE client_id = ?", (client_id,))
        conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))
    return True


def list_entries(filters: dict | None = None) -> list[dict]:
    filters = filters or {}
    sql = """
        SELECT e.*, c.name AS client_name
        FROM time_entries e
        JOIN clients c ON c.id = e.client_id
        WHERE 1=1
    """
    params: list = []
    if filters.get("client_id"):
        sql += " AND e.client_id = ?"
        params.append(int(filters["client_id"]))
    if filters.get("from"):
        sql += " AND e.work_date >= ?"
        params.append(filters["from"])
    if filters.get("to"):
        sql += " AND e.work_date <= ?"
        params.append(filters["to"])
    if filters.get("unbilled") in (True, "1", "true", "True"):
        sql += " AND e.billable = 1 AND e.invoice_id IS NULL"
    sql += " ORDER BY e.work_date DESC, e.id DESC"
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = row_to_dict(r)
        d["hours"] = round(d["duration_minutes"] / 60, 2)
        d["amount_ht"] = round(d["hours"] * d["hourly_rate_ht"], 2)
        out.append(d)
    return out


def get_entry(entry_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT e.*, c.name AS client_name
            FROM time_entries e
            JOIN clients c ON c.id = e.client_id
            WHERE e.id = ?
            """,
            (entry_id,),
        ).fetchone()
    if not row:
        return None
    d = row_to_dict(row)
    d["hours"] = round(d["duration_minutes"] / 60, 2)
    d["amount_ht"] = round(d["hours"] * d["hourly_rate_ht"], 2)
    return d


def create_entry(data: dict) -> dict:
    client = get_client(int(data["client_id"]))
    if not client:
        raise ValueError("Client introuvable")
    hours = data.get("hours")
    if hours is not None and hours != "":
        minutes = int(round(float(hours) * 60))
    else:
        minutes = int(data.get("duration_minutes") or 0)
    if minutes <= 0:
        raise ValueError("La durée doit être supérieure à 0")
    rate = data.get("hourly_rate_ht")
    rate = float(rate) if rate not in (None, "") else float(client["hourly_rate_ht"])
    tva = data.get("tva_rate")
    tva = float(tva) if tva not in (None, "") else float(client["tva_rate"])
    if not applies_tva():
        tva = 0.0
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO time_entries (
                client_id, description, work_date, duration_minutes,
                hourly_rate_ht, tva_rate, billable, invoice_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                int(data["client_id"]),
                (data.get("description") or "").strip(),
                data.get("work_date") or _today(),
                minutes,
                rate,
                tva,
                1 if str(data.get("billable", 1)) not in ("0", "false", "False") else 0,
                _now(),
            ),
        )
        eid = cur.lastrowid
    return get_entry(eid)


def update_entry(entry_id: int, data: dict) -> dict | None:
    existing = get_entry(entry_id)
    if not existing:
        return None
    if existing.get("invoice_id"):
        raise ValueError("Impossible de modifier une entrée déjà facturée")
    fields = {}
    if "description" in data:
        fields["description"] = data["description"]
    if "work_date" in data:
        fields["work_date"] = data["work_date"]
    if "client_id" in data:
        fields["client_id"] = int(data["client_id"])
    if "hours" in data and data["hours"] not in (None, ""):
        fields["duration_minutes"] = int(round(float(data["hours"]) * 60))
    elif "duration_minutes" in data:
        fields["duration_minutes"] = int(data["duration_minutes"])
    if "hourly_rate_ht" in data and data["hourly_rate_ht"] not in (None, ""):
        fields["hourly_rate_ht"] = float(data["hourly_rate_ht"])
    if "tva_rate" in data and data["tva_rate"] not in (None, ""):
        fields["tva_rate"] = float(data["tva_rate"])
    if "billable" in data:
        fields["billable"] = 1 if str(data["billable"]) not in ("0", "false", "False") else 0
    if fields:
        sets = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [entry_id]
        with get_conn() as conn:
            conn.execute(f"UPDATE time_entries SET {sets} WHERE id = ?", values)
    return get_entry(entry_id)


def delete_entry(entry_id: int) -> bool:
    existing = get_entry(entry_id)
    if not existing:
        return False
    if existing.get("invoice_id"):
        raise ValueError("Impossible de supprimer une entrée déjà facturée")
    with get_conn() as conn:
        conn.execute("DELETE FROM time_entries WHERE id = ?", (entry_id,))
    return True


def get_timer() -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT t.*, c.name AS client_name
            FROM timer t
            LEFT JOIN clients c ON c.id = t.client_id
            WHERE t.id = 1
            """
        ).fetchone()
    d = row_to_dict(row) or {"id": 1, "client_id": None, "description": "", "started_at": None, "client_name": None}
    if d.get("started_at"):
        started = datetime.strptime(d["started_at"], "%Y-%m-%d %H:%M:%S")
        d["elapsed_seconds"] = int((datetime.now() - started).total_seconds())
    else:
        d["elapsed_seconds"] = 0
    d["running"] = bool(d.get("started_at"))
    return d


def start_timer(client_id: int, description: str = "") -> dict:
    client = get_client(int(client_id))
    if not client:
        raise ValueError("Client introuvable")
    current = get_timer()
    if current.get("running"):
        raise ValueError("Un chronomètre est déjà en cours")
    with get_conn() as conn:
        conn.execute(
            "UPDATE timer SET client_id = ?, description = ?, started_at = ? WHERE id = 1",
            (int(client_id), description or "", _now()),
        )
    return get_timer()


def stop_timer() -> dict:
    current = get_timer()
    if not current.get("running"):
        raise ValueError("Aucun chronomètre en cours")
    started = datetime.strptime(current["started_at"], "%Y-%m-%d %H:%M:%S")
    minutes = max(1, int(round((datetime.now() - started).total_seconds() / 60)))
    entry = create_entry(
        {
            "client_id": current["client_id"],
            "description": current.get("description") or "Temps suivi",
            "work_date": started.date().isoformat(),
            "duration_minutes": minutes,
        }
    )
    with get_conn() as conn:
        conn.execute(
            "UPDATE timer SET client_id = NULL, description = '', started_at = NULL WHERE id = 1"
        )
    return {"timer": get_timer(), "entry": entry}


def cancel_timer() -> dict:
    with get_conn() as conn:
        conn.execute(
            "UPDATE timer SET client_id = NULL, description = '', started_at = NULL WHERE id = 1"
        )
    return get_timer()


def next_invoice_number() -> str:
    settings = get_settings()
    prefix = settings.get("invoice_prefix") or "FACT"
    year = date.today().year
    with get_conn() as conn:
        row = conn.execute(
            "SELECT number FROM invoices WHERE number LIKE ? ORDER BY id DESC LIMIT 1",
            (f"{prefix}-{year}-%",),
        ).fetchone()
    seq = 1
    if row:
        try:
            seq = int(row["number"].split("-")[-1]) + 1
        except ValueError:
            seq = 1
    return f"{prefix}-{year}-{seq:04d}"


def invoice_totals(invoice_id: int) -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM time_entries WHERE invoice_id = ?", (invoice_id,)
        ).fetchall()
    lines = []
    total_ht = 0.0
    tva_map: dict[float, float] = {}
    for r in rows:
        hours = r["duration_minutes"] / 60
        ht = round(hours * r["hourly_rate_ht"], 2)
        total_ht += ht
        tva_map[r["tva_rate"]] = tva_map.get(r["tva_rate"], 0) + round(ht * r["tva_rate"] / 100, 2)
        lines.append(
            {
                **row_to_dict(r),
                "hours": round(hours, 2),
                "amount_ht": ht,
            }
        )
    total_tva = round(sum(tva_map.values()), 2)
    return {
        "lines": lines,
        "total_ht": round(total_ht, 2),
        "total_tva": total_tva,
        "total_ttc": round(total_ht + total_tva, 2),
        "tva_by_rate": [{"rate": k, "amount": v} for k, v in sorted(tva_map.items())],
    }


def list_invoices() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT i.*, c.name AS client_name
            FROM invoices i
            JOIN clients c ON c.id = i.client_id
            ORDER BY i.issue_date DESC, i.id DESC
            """
        ).fetchall()
    out = []
    for r in rows:
        d = row_to_dict(r)
        d.update(invoice_totals(d["id"]))
        d.pop("lines", None)
        out.append(d)
    return out


def get_invoice(invoice_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT i.*, c.name AS client_name
            FROM invoices i
            JOIN clients c ON c.id = i.client_id
            WHERE i.id = ?
            """,
            (invoice_id,),
        ).fetchone()
    if not row:
        return None
    d = row_to_dict(row)
    d["client"] = get_client(d["client_id"])
    d.update(invoice_totals(d["id"]))
    return d


def create_invoice(data: dict) -> dict:
    client_id = int(data["client_id"])
    client = get_client(client_id)
    if not client:
        raise ValueError("Client introuvable")
    entry_ids = data.get("entry_ids") or []
    with get_conn() as conn:
        if entry_ids:
            placeholders = ",".join("?" * len(entry_ids))
            rows = conn.execute(
                f"""
                SELECT * FROM time_entries
                WHERE id IN ({placeholders})
                  AND client_id = ?
                  AND billable = 1
                  AND invoice_id IS NULL
                """,
                [*entry_ids, client_id],
            ).fetchall()
            if len(rows) != len(entry_ids):
                raise ValueError("Certaines heures ne peuvent pas être facturées")
        else:
            rows = conn.execute(
                """
                SELECT * FROM time_entries
                WHERE client_id = ? AND billable = 1 AND invoice_id IS NULL
                """,
                (client_id,),
            ).fetchall()
        if not rows:
            raise ValueError("Aucune heure à facturer pour ce client")
        settings = get_settings()
        days = int(settings.get("payment_days") or 30)
        issue = data.get("issue_date") or _today()
        due = data.get("due_date") or (date.fromisoformat(issue) + timedelta(days=days)).isoformat()
        number = next_invoice_number()
        apply_tva = data.get("apply_tva")
        if apply_tva is None:
            apply_tva = 1 if applies_tva(settings) else 0
        else:
            apply_tva = 0 if str(apply_tva) in ("0", "false", "False", "sans") else 1
        cur = conn.execute(
            """
            INSERT INTO invoices (number, client_id, issue_date, due_date, status, notes, created_at, apply_tva)
            VALUES (?, ?, ?, ?, 'brouillon', ?, ?, ?)
            """,
            (number, client_id, issue, due, data.get("notes") or "", _now(), apply_tva),
        )
        iid = cur.lastrowid
        for r in rows:
            if apply_tva == 0:
                conn.execute(
                    "UPDATE time_entries SET invoice_id = ?, tva_rate = 0 WHERE id = ?",
                    (iid, r["id"]),
                )
            else:
                conn.execute("UPDATE time_entries SET invoice_id = ? WHERE id = ?", (iid, r["id"]))
    return get_invoice(iid)


def update_invoice_status(invoice_id: int, status: str) -> dict | None:
    if status not in ("brouillon", "emise", "payee"):
        raise ValueError("Statut invalide")
    if not get_invoice(invoice_id):
        return None
    with get_conn() as conn:
        conn.execute("UPDATE invoices SET status = ? WHERE id = ?", (status, invoice_id))
    return get_invoice(invoice_id)


def delete_invoice(invoice_id: int) -> bool:
    inv = get_invoice(invoice_id)
    if not inv:
        return False
    if inv["status"] == "payee":
        raise ValueError("Impossible de supprimer une facture payée")
    with get_conn() as conn:
        conn.execute("UPDATE time_entries SET invoice_id = NULL WHERE invoice_id = ?", (invoice_id,))
        conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
    return True


def dashboard() -> dict:
    today = date.today()
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    month_start = today.replace(day=1).isoformat()
    with get_conn() as conn:
        def minutes(where: str, params: tuple = ()) -> int:
            row = conn.execute(
                f"SELECT COALESCE(SUM(duration_minutes), 0) AS m FROM time_entries WHERE {where}",
                params,
            ).fetchone()
            return int(row["m"])

        week_min = minutes("work_date >= ?", (week_start,))
        month_min = minutes("work_date >= ?", (month_start,))
        unbilled = conn.execute(
            """
            SELECT COALESCE(SUM(duration_minutes * hourly_rate_ht / 60.0), 0) AS amount,
                   COALESCE(SUM(duration_minutes), 0) AS minutes
            FROM time_entries
            WHERE billable = 1 AND invoice_id IS NULL
            """
        ).fetchone()
        issued = conn.execute(
            "SELECT COUNT(*) AS n FROM invoices WHERE status = 'emise'"
        ).fetchone()["n"]
        draft = conn.execute(
            "SELECT COUNT(*) AS n FROM invoices WHERE status = 'brouillon'"
        ).fetchone()["n"]
        clients_n = conn.execute("SELECT COUNT(*) AS n FROM clients").fetchone()["n"]
        recent = conn.execute(
            """
            SELECT e.*, c.name AS client_name
            FROM time_entries e
            JOIN clients c ON c.id = e.client_id
            ORDER BY e.id DESC
            LIMIT 8
            """
        ).fetchall()

    recent_list = []
    for r in recent:
        d = row_to_dict(r)
        d["hours"] = round(d["duration_minutes"] / 60, 2)
        d["amount_ht"] = round(d["hours"] * d["hourly_rate_ht"], 2)
        recent_list.append(d)

    return {
        "week_minutes": week_min,
        "month_minutes": month_min,
        "unbilled_minutes": int(unbilled["minutes"]),
        "unbilled_amount_ht": round(float(unbilled["amount"]), 2),
        "invoices_emises": issued,
        "invoices_brouillon": draft,
        "clients_count": clients_n,
        "recent_entries": recent_list,
        "timer": get_timer(),
        "settings": get_settings(),
    }
