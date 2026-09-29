#!/usr/bin/env python3
"""A-fid gestion — application locale de suivi du temps et de facturation."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import socket
import sys
import threading
import traceback
import webbrowser
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

import database as db
from invoices import build_invoice_pdf

HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT") or 8765)


def required_password() -> str:
    env = (os.environ.get("AFID_PASSWORD") or "").strip()
    if env:
        return env
    return (db.get_settings().get("access_code") or "").strip()


def session_secret() -> str:
    env = (os.environ.get("AFID_SECRET") or "").strip()
    if env:
        return env
    path = Path(os.environ.get("AFID_DATA") or (APP_DIR / "data")) / "secret.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    value = secrets.token_hex(24)
    path.write_text(value, encoding="utf-8")
    return value


def make_token(password: str) -> str:
    return hmac.new(session_secret().encode(), password.encode(), hashlib.sha256).hexdigest()


def public_paths(path: str) -> bool:
    return (
        path in ("/login", "/static/login.html", "/api/login", "/api/info")
        or path.startswith("/static/")
        or path.endswith(".png")
        or path.endswith(".jpg")
        or path.endswith(".css")
        or path.endswith(".js")
        or path.endswith(".json")
        or path == "/favicon.ico"
        or path == "/manifest.json"
    )


def lan_addresses():
    ips = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        if ip and not ip.startswith("127.") and ip not in ips:
            ips.insert(0, ip)
    except Exception:
        pass
    return ips


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(APP_DIR), **kwargs)

    def _cookie(self, name):
        raw = self.headers.get("Cookie") or ""
        jar = SimpleCookie()
        try:
            jar.load(raw)
        except Exception:
            return ""
        if name in jar:
            return jar[name].value
        return ""

    def _authorized(self) -> bool:
        password = required_password()
        if not password:
            return True
        token = self._cookie("afid")
        return bool(token) and hmac.compare_digest(token, make_token(password))

    def _set_cookie(self, name, value, extra_headers=None):
        headers = extra_headers or []
        headers.append(f"Set-Cookie: {name}={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000")
        return headers

    def _send_bytes(self, data, content_type, extra_headers=None, status=200):
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for line in extra_headers or []:
                k, v = line.split(": ", 1)
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)
        except (ConnectionResetError, BrokenPipeError):
            pass

    def _login_page(self, status=200):
        path = APP_DIR / "static" / "login.html"
        return self._send_bytes(path.read_bytes(), "text/html; charset=utf-8", status=status)
        try:
            sys.stdout.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))
        except Exception:
            pass

    def _json(self, payload, status=200):
        raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)
        except (ConnectionResetError, BrokenPipeError):
            pass

    def _error(self, message, status=400):
        self._json({"error": str(message)}, status)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _id_from(self, prefix: str) -> int | None:
        path = urlparse(self.path).path.rstrip("/")
        if not path.startswith(prefix):
            return None
        rest = path[len(prefix):].strip("/")
        if not rest:
            return None
        first = rest.split("/")[0]
        if first.isdigit():
            return int(first)
        return None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)
        try:
            if path.startswith("/data"):
                return self._error("Interdit", 403)
            if path in ("/login", "/static/login.html"):
                return self._login_page()
            if path == "/api/info":
                return self._json({
                    "name": "A-fid gestion",
                    "auth_required": bool(required_password()),
                    "logged_in": self._authorized(),
                    "lan": [f"http://{ip}:{PORT}/" for ip in lan_addresses()],
                    "local": f"http://127.0.0.1:{PORT}/",
                })
            if not self._authorized() and not public_paths(path):
                if path.startswith("/api/"):
                    return self._error("Connexion requise", 401)
                return self._login_page()
            if path in ("/", "/index.html"):
                data = (APP_DIR / "static" / "index.html").read_bytes()
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except (ConnectionResetError, BrokenPipeError):
                    return
                return
            if path == "/api/info":
                return self._json({
                    "name": "A-fid gestion",
                    "lan": [f"http://{ip}:{PORT}/" for ip in lan_addresses()],
                    "local": f"http://127.0.0.1:{PORT}/",
                })
            if path == "/api/dashboard":
                return self._json(db.dashboard())
            if path == "/api/settings":
                settings = db.get_settings()
                settings.pop("access_code", None)
                return self._json(settings)
            if path == "/api/clients":
                return self._json(db.list_clients())
            if path.startswith("/api/clients/"):
                item = db.get_client(self._id_from("/api/clients/"))
                return self._json(item) if item else self._error("Client introuvable", 404)
            if path == "/api/entries":
                filters = {
                    "client_id": (qs.get("client_id") or [None])[0],
                    "from": (qs.get("from") or [None])[0],
                    "to": (qs.get("to") or [None])[0],
                    "unbilled": (qs.get("unbilled") or [None])[0],
                }
                return self._json(db.list_entries(filters))
            if path == "/api/timer":
                return self._json(db.get_timer())
            if path == "/api/invoices":
                return self._json(db.list_invoices())
            if path.startswith("/api/invoices/") and path.endswith("/pdf"):
                iid = self._id_from("/api/invoices/")
                pdf = build_invoice_pdf(iid)
                inv = db.get_invoice(iid)
                filename = f"{inv['number']}.pdf".encode("ascii", "replace").decode()
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", f'inline; filename="{filename}"')
                self.send_header("Content-Length", str(len(pdf)))
                self.end_headers()
                self.wfile.write(pdf)
                return
            if path.startswith("/api/invoices/"):
                item = db.get_invoice(self._id_from("/api/invoices/"))
                return self._json(item) if item else self._error("Facture introuvable", 404)
            return super().do_GET()
        except Exception as exc:
            traceback.print_exc()
            return self._error(exc, 500)

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        try:
            body = self._body()
            if path == "/api/login":
                password = required_password()
                given = str(body.get("password") or body.get("code") or "")
                if not password:
                    return self._json({"ok": True, "auth_required": False})
                if not hmac.compare_digest(given, password):
                    return self._error("Mot de passe incorrect", 401)
                raw = json.dumps({"ok": True}).encode("utf-8")
                return self._send_bytes(
                    raw,
                    "application/json; charset=utf-8",
                    extra_headers=self._set_cookie("afid", make_token(password)),
                )
            if path == "/api/logout":
                raw = json.dumps({"ok": True}).encode("utf-8")
                return self._send_bytes(
                    raw,
                    "application/json; charset=utf-8",
                    extra_headers=["Set-Cookie: afid=; Path=/; Max-Age=0"],
                )
            if not self._authorized():
                return self._error("Connexion requise", 401)
            if path == "/api/clients":
                if not (body.get("name") or "").strip():
                    return self._error("Le nom du client est obligatoire")
                return self._json(db.create_client(body), 201)
            if path == "/api/entries":
                return self._json(db.create_entry(body), 201)
            if path == "/api/timer/start":
                return self._json(db.start_timer(int(body["client_id"]), body.get("description") or ""))
            if path == "/api/timer/stop":
                return self._json(db.stop_timer())
            if path == "/api/timer/cancel":
                return self._json(db.cancel_timer())
            if path == "/api/invoices":
                return self._json(db.create_invoice(body), 201)
            if path.startswith("/api/invoices/") and path.endswith("/status"):
                item = db.update_invoice_status(self._id_from("/api/invoices/"), body.get("status"))
                return self._json(item) if item else self._error("Facture introuvable", 404)
            return self._error("Route inconnue", 404)
        except ValueError as exc:
            return self._error(exc, 400)
        except Exception as exc:
            traceback.print_exc()
            return self._error(exc, 500)

    def do_PUT(self):
        path = urlparse(self.path).path.rstrip("/")
        try:
            if not self._authorized():
                return self._error("Connexion requise", 401)
            body = self._body()
            if path == "/api/settings":
                saved = db.save_settings(body)
                saved.pop("access_code", None)
                return self._json(saved)
            if path.startswith("/api/clients/"):
                item = db.update_client(self._id_from("/api/clients/"), body)
                return self._json(item) if item else self._error("Client introuvable", 404)
            if path.startswith("/api/entries/"):
                item = db.update_entry(self._id_from("/api/entries/"), body)
                return self._json(item) if item else self._error("Saisie introuvable", 404)
            return self._error("Route inconnue", 404)
        except ValueError as exc:
            return self._error(exc, 400)
        except Exception as exc:
            traceback.print_exc()
            return self._error(exc, 500)

    def do_DELETE(self):
        path = urlparse(self.path).path.rstrip("/")
        try:
            if not self._authorized():
                return self._error("Connexion requise", 401)
            if path.startswith("/api/clients/"):
                ok = db.delete_client(self._id_from("/api/clients/"))
                if not ok:
                    return self._error("Impossible de supprimer un client déjà facturé", 400)
                return self._json({"ok": True})
            if path.startswith("/api/entries/"):
                if not db.delete_entry(self._id_from("/api/entries/")):
                    return self._error("Saisie introuvable", 404)
                return self._json({"ok": True})
            if path.startswith("/api/invoices/"):
                if not db.delete_invoice(self._id_from("/api/invoices/")):
                    return self._error("Facture introuvable", 404)
                return self._json({"ok": True})
            return self._error("Route inconnue", 404)
        except ValueError as exc:
            return self._error(exc, 400)
        except Exception as exc:
            traceback.print_exc()
            return self._error(exc, 500)


def main():
    db.init_db()
    cloud = bool(os.environ.get("PORT") and os.environ.get("PORT") != "8765")
    host = "0.0.0.0" if cloud or ("--reseau" in sys.argv or "--network" in sys.argv) else HOST
    server = ThreadingHTTPServer((host, PORT), Handler)
    local = f"http://127.0.0.1:{PORT}/"
    print("=" * 56)
    print("  A-fid gestion")
    print("  Controle horaire et facturation")
    print(f"  Ordinateur : {local}")
    if host == "0.0.0.0":
        addrs = lan_addresses()
        if addrs:
            print("  Telephone (meme Wi-Fi) :")
            for ip in addrs:
                print(f"    http://{ip}:{PORT}/")
        else:
            print("  Telephone : http://IP-DU-PC:8765/")
        print("  Sur Android : Chrome > menu > Ajouter a l'ecran d'accueil")
    print("  Laissez cette fenetre ouverte pendant l'utilisation.")
    print("=" * 56)
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(local)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArret de A-fid gestion.")
        server.server_close()


if __name__ == "__main__":
    main()
