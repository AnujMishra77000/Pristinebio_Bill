"""Exercise the supplied Nginx routing, preserving the existing root website."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import socket
import subprocess
from threading import Thread
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPRedirectHandler
import sys

import pytest
from dotenv import dotenv_values

from app.core.config import Settings


ROOT = Path(__file__).resolve().parents[2]


def test_generated_deployment_settings_are_private_valid_and_never_overwritten(tmp_path):
    output = tmp_path / ".env.production"
    command = [sys.executable, str(ROOT / "deploy/create_env.py"), "--output", str(output)]
    created = subprocess.run(command, capture_output=True, text=True)
    assert created.returncode == 0, created.stderr
    original = output.read_bytes()
    values = dotenv_values(output)
    assert output.stat().st_mode & 0o777 == 0o600
    assert values["NEXT_PUBLIC_BASE_PATH"] == "/bill"
    assert values["NEXT_PUBLIC_API_BASE_URL"] == "/bill/api/v1"
    settings = Settings(_env_file=output)
    assert settings.frontend_origin == "https://www.pristinebiopharma.in"
    assert settings.cookie_secure is True
    assert settings.cookie_name("access") == "__Host-billing_access"
    for key in ("JWT_SECRET_KEY", "MFA_ENCRYPTION_KEY", "POSTGRES_PASSWORD"):
        assert values[key] and values[key] not in created.stdout + created.stderr
    repeated = subprocess.run(command, capture_output=True, text=True)
    assert repeated.returncode != 0
    assert output.read_bytes() == original


@contextmanager
def upstream(kind):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/api/v1/customers/":
                self.send_response(307)
                self.send_header("Location", "http://www.pristinebiopharma.in/api/v1/customers?limit=10")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf" if self.path.endswith("/pdf") else "text/plain")
            if self.path == "/api/v1/auth/csrf":
                self.send_header("Set-Cookie", "__Host-billing_csrf=test; Secure; HttpOnly; Path=/; SameSite=lax")
            self.end_headers()
            self.wfile.write(f"{kind}:{self.path}".encode())

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"|".join([self.path.encode(), self.headers.get("Origin", "").encode(),
                                       self.headers.get("Cookie", "").encode(), self.headers.get("X-CSRF-Token", "").encode(), body]))

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def proxy(tmp_path):
    nginx = shutil.which("nginx")
    if not nginx:
        pytest.skip("Nginx executable is required for the deployment proxy test")
    locations = (ROOT / "deploy/nginx/bill.locations.conf").read_text()
    with upstream("frontend") as frontend, upstream("backend") as backend:
        locations = locations.replace("127.0.0.1:3000", f"127.0.0.1:{frontend}").replace("127.0.0.1:8000", f"127.0.0.1:{backend}")
        with socket.socket() as address:
            address.bind(("127.0.0.1", 0))
            port = address.getsockname()[1]
        config = tmp_path / "nginx.conf"
        config.write_text(f"""
daemon off;
master_process off;
pid {tmp_path}/nginx.pid;
error_log {tmp_path}/error.log;
events {{ worker_connections 64; }}
http {{
    access_log off;
    client_body_temp_path {tmp_path}/body;
    proxy_temp_path {tmp_path}/proxy;
    fastcgi_temp_path {tmp_path}/fastcgi;
    uwsgi_temp_path {tmp_path}/uwsgi;
    scgi_temp_path {tmp_path}/scgi;
    server {{
        listen 127.0.0.1:{port};
        server_name www.pristinebiopharma.in;
        location / {{ return 200 'existing-main-site'; }}
        {locations}
    }}
}}
""")
        checked = subprocess.run([nginx, "-t", "-p", str(tmp_path), "-c", str(config)], capture_output=True, text=True)
        assert checked.returncode == 0, checked.stderr
        process = subprocess.Popen([nginx, "-p", str(tmp_path), "-c", str(config)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            for _ in range(100):
                if process.poll() is not None:
                    pytest.fail(process.stderr.read().decode())
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    time.sleep(0.02)
            else:
                pytest.fail("Test Nginx failed to start")
            yield f"http://127.0.0.1:{port}"
        finally:
            process.terminate()
            process.wait(timeout=5)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def test_bill_pages_assets_and_api_are_routed_without_replacing_the_root_site(proxy):
    opener = build_opener(NoRedirect)
    for path, expected in [
        ("/", "existing-main-site"), ("/bill", "frontend:/bill"),
        ("/bill/login", "frontend:/bill/login"), ("/bill/_next/static/test.js", "frontend:/bill/_next/static/test.js"),
        ("/bill/api/v1/invoices?document_type=sales", "backend:/api/v1/invoices?document_type=sales"),
        ("/billing", "existing-main-site"),
    ]:
        response = opener.open(proxy + path)
        assert response.read().decode() == expected
    response = opener.open(proxy + "/bill/api/v1/invoices/7/pdf")
    assert response.headers["Content-Type"] == "application/pdf"
    assert response.read() == b"backend:/api/v1/invoices/7/pdf"


def test_bill_proxy_preserves_csrf_origin_cookies_and_request_body(proxy):
    opener = build_opener(NoRedirect)
    response = opener.open(proxy + "/bill/api/v1/auth/csrf")
    assert response.headers["Set-Cookie"] == "__Host-billing_csrf=test; Secure; HttpOnly; Path=/; SameSite=lax"
    payload = b'{"email":"test@example.com","password":"Test12"}'
    response = opener.open(Request(proxy + "/bill/api/v1/auth/login", data=payload, headers={
        "Origin": "https://www.pristinebiopharma.in", "Cookie": "__Host-billing_csrf=test",
        "X-CSRF-Token": "test", "Content-Type": "application/json",
    }))
    assert response.read() == b"/api/v1/auth/login|https://www.pristinebiopharma.in|__Host-billing_csrf=test|test|" + payload


def test_backend_canonical_redirect_stays_under_bill(proxy):
    with pytest.raises(HTTPError) as captured:
        build_opener(NoRedirect).open(proxy + "/bill/api/v1/customers/")
    assert captured.value.code == 307
    assert captured.value.headers["Location"].endswith("/bill/api/v1/customers?limit=10")
