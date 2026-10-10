"""Focused browser regression using the Phase 2 API contract, no live backend writes."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from playwright.sync_api import Route, expect, sync_playwright
from verify_manual_consignee_ui import _mock_api

BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3100")
USER = {"id": 1, "email": "admin@example.com", "full_name": "Admin User", "role": "admin", "branch_ids": [], "is_active": True, "password_change_required": False, "mfa_enabled": False, "mfa_required": False, "mfa_verified": True}


@dataclass
class Contract:
    user: dict = field(default_factory=lambda: dict(USER))
    signed_in: bool = False
    available: bool = False
    expired: bool = False
    recover: bool = False
    bad_secret: bool = False
    refresh_succeeds: bool = False
    calls: list = field(default_factory=list)
    saves: list = field(default_factory=list)

    def route(self, route: Route) -> None:
        request = route.request
        path = request.url.split("/api/v1")[-1]
        method = request.method
        headers = {"Access-Control-Allow-Origin": BASE_URL, "Access-Control-Allow-Credentials": "true", "Access-Control-Allow-Headers": "Content-Type, X-CSRF-Token, Idempotency-Key", "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS"}
        def reply(payload, status=200):
            route.fulfill(status=status, content_type="application/json", body=json.dumps(payload), headers=headers)
        if method == "OPTIONS":
            reply({})
            return
        payload = json.loads(request.post_data or "{}")
        self.calls.append((path, method, payload, request.headers))
        if method not in ("GET", "HEAD"):
            assert request.headers.get("x-csrf-token") == "test-csrf", (path, request.headers)
            assert "authorization" not in request.headers
        if path == "/auth/csrf":
            reply({"csrf_token": "test-csrf"})
        elif path == "/auth/me":
            reply(self.user if self.signed_in and not self.expired else {"detail": "expired"}, 200 if self.signed_in and not self.expired else 401)
        elif path == "/auth/refresh":
            if self.refresh_succeeds:
                self.expired = False
                self.signed_in = True
                reply({"user": self.user})
            else:
                reply({"detail": "expired"}, 401)
        elif path in ("/auth/login", "/auth/register", "/auth/invitations/accept"):
            self.signed_in = True
            self.expired = False
            reply({"user": self.user})
        elif path == "/auth/password":
            if self.bad_secret:
                reply({"detail": "Incorrect current password"}, 401)
                return
            self.user["password_change_required"] = False
            reply({"user": self.user})
        elif path == "/auth/mfa/enroll":
            reply({"secret": "JBSWY3DPEHPK3PXP", "provisioning_uri": "otpauth://totp/Pristine:admin?secret=JBSWY3DPEHPK3PXP"})
        elif path == "/auth/mfa/confirm":
            self.user.update(mfa_enabled=True, mfa_verified=True)
            reply({"user": self.user, "recovery_codes": ["recovery-one", "recovery-two"]})
        elif path == "/auth/mfa/verify":
            if self.bad_secret:
                reply({"detail": "Incorrect authenticator code"}, 401)
                return
            self.user["mfa_verified"] = True
            reply({"user": self.user})
        elif path == "/auth/mfa/recover":
            self.recover = True
            self.user.update(mfa_enabled=False, mfa_verified=False)
            reply({"user": self.user})
        elif path == "/auth/mfa/recovery-codes":
            reply({"recovery_codes": ["replacement-one", "replacement-two"]})
        elif path == "/auth/sessions":
            reply([{"id": "current-session", "created_at": "2026-09-16T00:00:00Z", "last_seen_at": "2026-09-16T01:00:00Z", "expires_at": "2026-10-16T00:00:00Z", "current": True}, {"id": "other-session", "created_at": "2026-09-15T00:00:00Z", "last_seen_at": "2026-09-15T01:00:00Z", "expires_at": "2026-10-15T00:00:00Z", "current": False}])
        elif path == "/users":
            reply([self.user, dict(USER, id=2, full_name="Other Admin", email="other@example.com")])
        elif path == "/auth/invitations" and method == "POST":
            reply({"id": 8, **payload, "expires_at": "2026-09-20T00:00:00Z", "token": "once-only-token"})
        elif path == "/auth/invitations":
            reply([{"id": 8, "email": "staff@example.com", "role": "staff", "branch_ids": [1], "expires_at": "2026-09-20T00:00:00Z", "accepted_at": None, "revoked_at": None}])
        elif path == "/auth/audit":
            reply([{"id": 1, "actor_id": 1, "action": "invitation_created", "entity_type": "invitation", "entity_id": "8", "created_at": "2026-09-16T00:00:00Z", "before": None, "after": {"role": "staff"}}])
        elif path == "/branches":
            reply([{"id": 1, "name": "Primary seller", "gstin": "36AAAAA0000A1Z5"}])
        elif method in ("DELETE", "PATCH") or path.endswith(("/mfa-reset", "/revoke-sessions")):
            reply({"detail": "Updated"})
        elif path in ("/auth/logout", "/auth/logout-all"):
            self.signed_in = False
            reply({"detail": "Logged out"})
        elif path == "/invoices" and method == "POST":
            self.saves.append((payload, request.headers.get("idempotency-key")))
            reply({"detail": "Session expired"} if self.expired else {"detail": "Unrelated save error"}, 401 if self.expired else 500)
        else:
            _mock_api(route)


def sign_in(page):
    page.get_by_label("Email", exact=True).fill("admin@example.com")
    page.get_by_label("Password", exact=True).fill("Abc123")
    page.locator('button[type="submit"]').click()


def verify_draft_preservation(browser):
    def scenario(contract):
        context = browser.new_context()
        context.route("**/api/v1/**", contract.route)
        page = context.new_page()
        page.set_default_timeout(10000)
        page.set_default_navigation_timeout(10000)
        return context, page
    contract = Contract(signed_in=True)
    context, page = scenario(contract)
    page.goto(f"{BASE_URL}/invoices")
    page.wait_for_timeout(1000)
    page.get_by_label("Buyer/vendor name").fill("Preserved Buyer")
    page.get_by_label("Address line 1", exact=True).fill("Buyer Street")
    page.get_by_label("City", exact=True).fill("Hyderabad")
    page.get_by_label("State", exact=True).fill("Telangana")
    page.get_by_label("Postal code", exact=True).fill("500001")
    page.get_by_label("Product name").fill("Sodium Citrate")
    page.get_by_label("HSN/SAC").fill("29181590")
    page.get_by_label("Rate", exact=True).fill("30.00")
    page.evaluate("window.preservedBuyerNode = document.querySelector('input[value=\"Preserved Buyer\"]')")
    contract.expired = True
    page.get_by_role("button", name="Save sales invoice draft").click()
    dialog = page.get_by_role("dialog", name="Restore secure access")
    expect(dialog).to_be_visible()
    expect(page.get_by_text("Session expired", exact=True)).to_be_visible()
    sign_in(dialog)
    expect(dialog).to_have_count(0)
    expect(page.get_by_label("Buyer/vendor name")).to_have_value("Preserved Buyer")
    assert page.evaluate("window.preservedBuyerNode != null && window.preservedBuyerNode === document.querySelector('input[value=\"Preserved Buyer\"]')")
    page.get_by_role("button", name="Save sales invoice draft").click()
    expect(page.get_by_text("Unrelated save error", exact=True)).to_be_visible()
    assert len(contract.saves) == 2 and contract.saves[0] == contract.saves[1]
    page.get_by_role("button", name="Log out", exact=True).click()
    expect(page.get_by_text("Sign in to continue", exact=True)).to_be_visible()
    assert any(c[0] == "/auth/logout" and c[1] == "POST" for c in contract.calls)
    context.close()
    print("PASS: session expiry preserves the mounted draft, payload and idempotency key", flush=True)


def verify_tab_concurrency(browser):
    contract = Contract(signed_in=True, expired=True, refresh_succeeds=True)
    context = browser.new_context()
    pending = []
    released = False
    def route(request_route):
        nonlocal released
        if request_route.request.url.endswith("/auth/me") and not released:
            pending.append(request_route)
            if len(pending) == 2:
                released = True
                for item in pending:
                    contract.calls.append(("/auth/me", "GET", {}, item.request.headers))
                    item.fulfill(status=401, content_type="application/json", body='{"detail":"expired"}', headers={"Access-Control-Allow-Origin": BASE_URL, "Access-Control-Allow-Credentials": "true"})
        else:
            contract.route(request_route)
    context.route("**/api/v1/**", route)
    context.add_init_script("""
        window.securityMessages = [];
        window.securityLocks = [];
        const OriginalChannel = window.BroadcastChannel;
        window.BroadcastChannel = class extends OriginalChannel {
            postMessage(message) { window.securityMessages.push(message); super.postMessage(message); }
        };
        const originalRequest = navigator.locks.request.bind(navigator.locks);
        navigator.locks.request = (...args) => { window.securityLocks.push(args[0]); return originalRequest(...args); };
    """)
    first, second = context.new_page(), context.new_page()
    for page in (first, second):
        page.set_default_timeout(10000)
        page.set_default_navigation_timeout(10000)
        page.goto(f"{BASE_URL}/invoices", wait_until="domcontentloaded")
    for page in (first, second):
        expect(page.get_by_label("Buyer/vendor name")).to_be_visible()
        assert page.evaluate("Object.keys(localStorage).length + Object.keys(sessionStorage).length") == 0
    assert sum(c[0] == "/auth/refresh" for c in contract.calls) == 1
    locks = first.evaluate("window.securityLocks") + second.evaluate("window.securityLocks")
    assert len(locks) >= 2 and all(name == "pristine-bio-billing.session-refresh" for name in locks)
    messages = first.evaluate("window.securityMessages") + second.evaluate("window.securityMessages")
    assert messages and all(set(message) == {"type"} for message in messages)
    first.get_by_role("button", name="Log out", exact=True).click()
    expect(second.get_by_text("Sign in to continue", exact=True)).to_be_visible()
    assert sum(c[0] == "/auth/logout" for c in contract.calls) == 1
    context.close()
    print("PASS: concurrent tabs rotate once under real Web Locks; metadata-only broadcast and cross-tab logout", flush=True)


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        verify_draft_preservation(browser)
        if os.environ.get("AUTH_REGRESSION_FOCUS") == "draft":
            browser.close()
            return
        verify_tab_concurrency(browser)
        def scenario(contract):
            context = browser.new_context()
            context.route("**/api/v1/**", contract.route)
            page = context.new_page()
            page.set_default_timeout(10000)
            page.set_default_navigation_timeout(10000)
            return context, page

        contract = Contract(user=dict(USER, password_change_required=True, mfa_enabled=False, mfa_verified=False))
        context, page = scenario(contract)
        page.goto(f"{BASE_URL}/login")
        expect(page.get_by_role("button", name="Register as Admin", exact=True)).to_be_visible()
        sign_in(page)
        expect(page.get_by_role("heading", name="Upgrade your password")).to_be_visible()
        page.get_by_label("Current password", exact=True).fill("Abc123")
        page.get_by_label("New passphrase", exact=True).fill("short")
        page.get_by_label("Confirm passphrase", exact=True).fill("short")
        page.get_by_role("button", name="Change password", exact=True).click()
        expect(page.locator('p[role="alert"]')).to_contain_text("6–10")
        assert not any(c[0] == "/auth/password" for c in contract.calls)
        page.get_by_label("New passphrase", exact=True).fill("River!73")
        page.get_by_label("Confirm passphrase", exact=True).fill("River!73")
        page.get_by_role("button", name="Change password", exact=True).click()
        page.wait_for_url(f"{BASE_URL}/")
        assert page.evaluate("Object.keys(localStorage).length + Object.keys(sessionStorage).length") == 0
        page.goto(f"{BASE_URL}/security")
        expect(page.get_by_role("heading", name="Authenticator")).to_have_count(0)
        expect(page.get_by_text("Set up authenticator", exact=True)).to_have_count(0)
        expect(page.get_by_text("other-session", exact=True)).to_be_visible()
        page.get_by_role("button", name="Revoke session other-session").click()
        expect(page.get_by_text("Session revoked.", exact=True)).to_be_visible()
        assert any(c[0] == "/auth/sessions/other-session" and c[1] == "DELETE" for c in contract.calls)
        page.get_by_role("button", name="Log out all sessions", exact=True).click()
        expect(page.get_by_text("Sign in to continue", exact=True)).to_be_visible()
        assert any(c[0] == "/auth/logout-all" for c in contract.calls)
        context.close()

        contract = Contract(user=dict(USER, mfa_enabled=True, mfa_required=True, mfa_verified=False))
        context, page = scenario(contract)
        page.goto(f"{BASE_URL}/login")
        sign_in(page)
        page.wait_for_url(f"{BASE_URL}/")
        expect(page.get_by_text("Verify your authenticator", exact=True)).to_have_count(0)
        assert not any(c[0].startswith("/auth/mfa/") for c in contract.calls)
        context.close()

        contract = Contract()
        context, page = scenario(contract)
        page.goto(f"{BASE_URL}/login#invite=fragment-secret")
        expect(page.get_by_role("heading", name="Accept invitation")).to_be_visible()
        assert page.evaluate("location.hash") == ""
        page.get_by_label("Full name", exact=True).fill("Invited User")
        page.get_by_label("New passphrase", exact=True).fill("River!73")
        page.get_by_label("Confirm passphrase", exact=True).fill("River!73")
        page.get_by_role("button", name="Accept invitation", exact=True).click()
        page.wait_for_url(f"{BASE_URL}/")
        assert next(c for c in contract.calls if c[0] == "/auth/invitations/accept")[2]["token"] == "fragment-secret"
        contract = Contract()
        context, page = scenario(contract)
        page.goto(f"{BASE_URL}/register")
        expect(page.get_by_role("heading", name="Create an Admin account")).to_be_visible()
        page.get_by_label("Full name", exact=True).fill("Second Admin")
        page.get_by_label("Email", exact=True).fill("second@example.com")
        page.get_by_label("New passphrase", exact=True).fill("River!73")
        page.get_by_label("Confirm passphrase", exact=True).fill("River!73")
        page.get_by_role("button", name="Create Admin account", exact=True).click()
        page.wait_for_url(f"{BASE_URL}/")
        assert next(c for c in contract.calls if c[0] == "/auth/register")[2]["email"] == "second@example.com"
        context.close()

        contract = Contract(signed_in=True)
        context, page = scenario(contract)
        page.goto(f"{BASE_URL}/users")
        page.get_by_label("Invitation email", exact=True).fill("staff@example.com")
        page.get_by_role("checkbox", name="Primary seller").first.check()
        page.get_by_role("button", name="Create invitation", exact=True).click()
        link = page.get_by_label("One-time invitation link", exact=True)
        expect(link).to_have_value(f"{BASE_URL}/login#invite=once-only-token")
        expect(page.get_by_text("invitation_created", exact=True)).to_be_visible()
        page.get_by_role("button", name="Revoke invitation 8", exact=True).click()
        page.get_by_role("button", name="Edit Other Admin", exact=True).click()
        page.get_by_label("Full name", exact=True).fill("Updated Admin")
        page.get_by_role("button", name="Save user", exact=True).click()
        expect(page.get_by_text("User updated.", exact=True)).to_be_visible()
        assert any(c[0] == "/users/2" and c[1] == "PATCH" and c[2]["full_name"] == "Updated Admin" for c in contract.calls)
        page.get_by_role("button", name="Revoke sessions for Other Admin", exact=True).click()
        expect(page.get_by_role("button", name="Reset MFA for Other Admin")).to_have_count(0)
        assert not any(c[0] == "/users" and c[1] == "POST" for c in contract.calls)
        context.close()

        browser.close()
        print("PASS: auth restrictions, no-MFA login, invitation/bootstrap, security, Admin controls, in-place reauthentication/save preservation")


if __name__ == "__main__":
    main()
