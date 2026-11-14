"""E8: the admin dashboard. Server-side checks, plus a real browser run (headless Chrome over
the DevTools protocol) when Chrome is installed: sign in, see usage, create and revoke a
key, create a profile, with no script errors and no Content-Security-Policy violations."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.conftest import ADMIN, admin, bearer, make_settings, new_org

# -- server side -------------------------------------------------------------------------


def test_dashboard_is_served_locked_down(client: Any) -> None:
    r = client.get("/dashboard/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert r.headers["x-frame-options"] == "DENY"
    js = client.get("/dashboard/static/app.js")
    assert js.status_code == 200 and "javascript" in js.headers["content-type"]
    assert "innerHTML" not in js.text and "eval(" not in js.text  # data is never parsed as HTML
    assert client.get("/dashboard/static/../app.py").status_code == 404
    assert client.get("/dashboard/static/secrets.txt").status_code == 404
    assert client.get("/dashboard", follow_redirects=False).status_code == 307


def test_me(client: Any) -> None:
    org_id, key = new_org(client, name="Acme Calls")
    me = client.get("/v1/me", headers=bearer(key)).json()
    assert me == {
        "actor": me["actor"],
        "superadmin": False,
        "org_id": org_id,
        "org_name": "Acme Calls",
        "scopes": ["admin", "stream", "usage:read"],
    }
    assert client.get("/v1/me", headers=admin()).json()["superadmin"] is True
    assert client.get("/v1/me").status_code == 401


def test_every_api_path_the_dashboard_calls_exists(client: Any) -> None:
    import re

    js = client.get("/dashboard/static/app.js").text
    used = {re.sub(r"\$\{[^}]+\}", "{id}", m) for m in re.findall(r'["`](/v1/[^"`?]+)', js)}
    spec = {re.sub(r"\{[^}]+\}", "{id}", p) for p in client.get("/openapi.json").json()["paths"]}
    assert used and used <= spec, used - spec


def test_every_dashboard_string_has_an_arabic_translation(client: Any) -> None:
    """I-025: everything the dashboard shows goes through t() and exists in Arabic."""
    import re

    js = client.get("/dashboard/static/app.js").text
    html = client.get("/dashboard/").text
    i18n = client.get("/dashboard/static/i18n.js")
    assert i18n.status_code == 200 and "javascript" in i18n.headers["content-type"]
    unq = lambda x: x.replace('\\"', '"')  # noqa: E731
    keys = {unq(k) for k in re.findall(r'^\s*"((?:[^"\\]|\\.)*)":\s', i18n.text, re.M)}
    used = {unq(x) for x in re.findall(r'\bt\("((?:[^"\\]|\\.)*)"', js)}
    used |= set(re.findall(r'data-i18n(?:-label)?="([^"]+)"', html))
    # passed to t() as values: field labels, page titles, statuses and roles from the API
    field = r'^\s*\["\w+", (?:"\w+"|\[[^\]]*\]), "((?:[^"\\]|\\.)*)"\],$'
    used |= {unq(x) for x in re.findall(field, js, re.M)}
    titles = re.search(r"const TITLES = \{(.*)\};", js)
    assert titles is not None
    used |= set(re.findall(r'\w+: "([^"]+)"', titles.group(1)))
    used |= {"ended", "failed", "active", "revoked", "default", "sent", "pending", "empty",
             "suspended", "process", "relay", "admin", "viewer"}  # fmt: skip
    assert len(used) > 120
    assert used <= keys, sorted(used - keys)
    assert re.search(r"\bt\(`", js) is None  # template strings cannot be looked up
    # visible text is never a bare English literal outside t()
    tags = "h1|h2|p|button|th|label|legend|option"
    bare = re.findall(rf'h\("(?:{tags})", \{{[^}}]*\}}, "([A-Z][^"]+)"', js)
    assert bare == [], bare


# -- real browser ------------------------------------------------------------------------

CHROME = next(
    (p for p in map(shutil.which, ("google-chrome", "chromium", "chromium-browser")) if p), None
)
SHOTS = Path(os.environ.get("NEXORA_DASHBOARD_SHOTS", tempfile.gettempdir())) / "nexora-dashboard"
IGNORED = ("Failed to load resource",)  # expected 401/404 probes (signed out, SSO off)
_axe = os.environ.get("NEXORA_AXE_JS")
AXE = Path(_axe) if _axe and Path(_axe).is_file() else None
if os.environ.get("CI") and CHROME and AXE is None:
    raise RuntimeError("CI runs the dashboard accessibility audit: set NEXORA_AXE_JS")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class Browser:
    """Just enough of the Chrome DevTools protocol: navigate, run JS, screenshot, errors."""

    def __init__(self) -> None:
        from websockets.sync.client import connect

        self.dir = tempfile.mkdtemp(prefix="nexora-chrome-")
        args = [
            str(CHROME),
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--no-first-run",
            "--remote-debugging-port=0",
            f"--user-data-dir={self.dir}",
            "--window-size=1280,900",
            "about:blank",
        ]
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port_file = Path(self.dir) / "DevToolsActivePort"
        deadline = time.time() + 20
        while not port_file.exists() or len(port_file.read_text().splitlines()) < 2:
            if time.time() > deadline:
                raise RuntimeError("chrome did not start")
            time.sleep(0.1)
        port = port_file.read_text().splitlines()[0]
        pages = httpx.get(f"http://127.0.0.1:{port}/json").json()
        page = next(p for p in pages if p["type"] == "page")
        self.ws = connect(page["webSocketDebuggerUrl"], max_size=64 * 1024 * 1024)
        self.n = 0
        self.errors: list[str] = []
        for m in ("Page.enable", "Runtime.enable", "Log.enable"):
            self.call(m)

    def _note(self, msg: dict[str, Any]) -> None:
        method, params = msg.get("method"), msg.get("params", {})
        if method == "Runtime.exceptionThrown":
            self.errors.append(json.dumps(params["exceptionDetails"])[:400])
        elif method == "Log.entryAdded" and params["entry"]["level"] == "error":
            text = params["entry"]["text"]
            if not text.startswith(IGNORED):
                self.errors.append(text)
        elif method == "Runtime.consoleAPICalled" and params["type"] == "error":
            self.errors.append(str(params["args"])[:400])

    def call(self, method: str, **params: Any) -> dict[str, Any]:
        self.n += 1
        my = self.n
        self.ws.send(json.dumps({"id": my, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv(timeout=30))
            self._note(msg)
            if msg.get("id") == my:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return dict(msg.get("result", {}))

    def js(self, expr: str) -> Any:
        r = self.call("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"])
        return r["result"].get("value")

    def wait(self, expr: str, timeout: float = 15) -> Any:
        deadline = time.time() + timeout
        while time.time() < deadline:
            v = self.js(expr)
            if v:
                return v
            time.sleep(0.1)
        page = self.js("document.body.innerText")[:600]
        raise AssertionError(f"timed out: {expr}\npage: {page}\nerrors: {self.errors}")

    def click(self, text: str, within: str = "") -> None:
        """Click the button labelled ``text`` (inside the CSS selector ``within``)."""
        sel, label = json.dumps(f"{within} button".strip()), json.dumps(text)
        found = f"[...document.querySelectorAll({sel})].find(x => x.textContent === {label})"
        self.js(f"{found}.click()")

    @staticmethod
    def row_has(*texts: str) -> str:
        cond = " && ".join(f"r.textContent.includes({json.dumps(t)})" for t in texts)
        return f"[...document.querySelectorAll('#view tbody tr')].some(r => {cond})"

    def audit(self, where: str) -> None:
        """Run axe-core (WCAG 2.0/2.1 A and AA rules) on the page; fail on any violation.
        Needs NEXORA_AXE_JS (axe.min.js, e.g. from ``npm install axe-core``); skipped
        without it locally, required in CI."""
        if AXE is None:
            return
        if not self.js("typeof axe !== 'undefined'"):
            self.js(AXE.read_text())  # through the DevTools protocol, not the page's CSP
        found = self.js(
            "axe.run(document, {runOnly: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']})"
            ".then(r => r.violations.map(v => v.id + ': ' + v.help + ' -> '"
            " + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | ')))"
        )
        assert found == [], f"{where}: {found}"

    def shot(self, name: str) -> Path:
        import base64

        SHOTS.mkdir(parents=True, exist_ok=True)
        data = self.call("Page.captureScreenshot", format="png")["data"]
        path = SHOTS / f"{name}.png"
        path.write_bytes(base64.b64decode(data))
        return path

    def close(self) -> None:
        self.ws.close()
        self.proc.terminate()
        self.proc.wait(10)
        shutil.rmtree(self.dir, ignore_errors=True)


@pytest.fixture
def live(tmp_path: Path) -> Any:
    import uvicorn

    from nexora_server.app import create_app
    from nexora_server.db import SessionRecord, utcnow

    port = _free_port()
    app = create_app(make_settings(tmp_path), prewarm=False)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            if httpx.get(f"{base}/readyz").status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    body = {"name": "Acme <b>Calls</b>", "monthly_minutes_quota": 600}
    org = httpx.post(f"{base}/v1/orgs", json=body, headers={"Authorization": f"Bearer {ADMIN}"})
    org_id, key = org.json()["organization"]["id"], org.json()["api_key"]
    now = utcnow()
    with app.state.db.session() as db:  # some usage to chart
        for d in range(12):
            at = now - timedelta(days=d)
            db.add(
                SessionRecord(
                    org_id=org_id,
                    mode="process",
                    status="ended",
                    audio_seconds=60.0 * (d % 5 + 1),
                    started_at=at,
                    ended_at=at,
                    quality={"snr_db": 18.5},
                )
            )
    yield base, key
    server.should_exit = True
    t.join(10)


PAGE_READY = "!!document.querySelector('#view h1') && !document.querySelector('#view').ariaBusy"
SET_ECHO = (
    "const c = [...document.querySelectorAll('dialog[open] label.check')]"
    ".find(l => l.textContent.startsWith('Echo cancellation')).querySelector('input');"
    "c.indeterminate = false; c.checked = true"
)
REVOKE = (
    "[...document.querySelectorAll('#view tbody tr')]"
    ".find(r => r.textContent.includes('browser test'))"
    ".querySelector('button.danger').click()"
)


@pytest.mark.skipif(CHROME is None, reason="Chrome not installed")
def test_dashboard_in_a_real_browser(live: Any) -> None:
    base, key = live
    b = Browser()
    try:
        b.call("Page.navigate", url=f"{base}/dashboard/")
        b.wait("document.readyState === 'complete' && !document.querySelector('#signin').hidden")
        b.js(f"document.querySelector('#signin-key').value = {json.dumps(key)}")
        b.js("document.querySelector('#signin-form').requestSubmit()")
        b.wait("!document.querySelector('#nav').hidden && !!document.querySelector('svg.chart')")
        text = b.js("document.body.innerText")
        assert "Acme <b>Calls</b>" in text  # shown as text, not markup
        assert b.js("document.querySelectorAll('main b').length") == 0
        assert "minutes this month" in text and "of 600 minute quota" in text
        bars = b.js(
            "[...document.querySelectorAll('svg.chart rect')].map(r => +r.getAttribute('height'))"
        )
        assert len(bars) in (30, 31) and sum(1 for x in bars if x > 0) == 12  # gaps show as zero
        assert b.js("sessionStorage.length") == 1 and b.js("localStorage.length") == 0
        b.shot("overview")

        b.js("location.hash = '#/keys'")
        b.wait("document.querySelector('#view h1')?.textContent === 'API keys'")
        rows = b.js("document.querySelectorAll('#view tbody tr').length")
        b.click("New key")
        b.wait("!!document.querySelector('dialog[open]')")
        b.js("document.querySelector('dialog[open] input[type=text]').value = 'browser test'")
        b.click("Create", "dialog[open]")
        secret = b.wait("document.querySelector('dialog[open] .secret')?.textContent")
        auth = {"Authorization": f"Bearer {secret}"}
        b.shot("new-key")
        b.click("Done", "dialog[open]")
        b.wait(f"document.querySelectorAll('#view tbody tr').length === {rows + 1}")
        assert httpx.get(f"{base}/v1/me", headers=auth).status_code == 200
        b.js(REVOKE)
        b.wait("!!document.querySelector('dialog[open]')")
        b.click("Revoke", "dialog[open]")
        b.wait(b.row_has("browser test", "revoked"))
        assert httpx.get(f"{base}/v1/me", headers=auth).status_code == 401

        b.js("location.hash = '#/profiles'")
        b.wait("document.querySelector('#view h1')?.textContent === 'Profiles'")
        b.click("New profile")
        b.wait("!!document.querySelector('dialog[open]')")
        b.js("document.querySelector('dialog[open] input[type=text]').value = 'speakerphone'")
        b.js(SET_ECHO)
        b.click("Save", "dialog[open]")
        b.wait(b.row_has("speakerphone"))
        prof = httpx.get(f"{base}/v1/profiles", headers={"Authorization": f"Bearer {key}"}).json()
        assert prof[0]["name"] == "speakerphone"
        assert prof[0]["audio_settings"]["echo_cancellation"] is True
        b.shot("profiles")

        for view in ("sessions", "audit"):
            b.js(f"location.hash = '#/{view}'")
            b.wait("!!document.querySelector('#view table tbody tr')")
            b.shot(view)
            if view == "sessions":
                assert "18.5" in b.js("document.body.innerText")  # per-call quality column
        b.js("location.hash = '#/team'")
        b.wait("document.querySelector('#view h1')?.textContent === 'Team'")
        b.js("document.querySelector('#view input[type=email]').value = 'Ops@Acme.example'")
        b.click("Add", "#view")
        b.wait(b.row_has("ops@acme.example", "admin"))
        b.js("location.hash = '#/billing'")
        b.wait("document.querySelector('#view h1')?.textContent === 'Billing'")
        b.shot("billing")

        downloads = Path(tempfile.mkdtemp(prefix="nexora-dl-"))
        b.call("Page.setDownloadBehavior", behavior="allow", downloadPath=str(downloads))
        b.js("location.hash = '#/audit'")
        b.wait("document.querySelector('#view h1')?.textContent === 'Audit log'")
        b.click("Export CSV", "#view")
        deadline = time.time() + 10
        while not list(downloads.glob("audit-*.csv")) and time.time() < deadline:
            time.sleep(0.1)
        (csv_file,) = list(downloads.glob("audit-*.csv"))
        assert "sso.member.add" in csv_file.read_text() and "key.revoke" in csv_file.read_text()

        # I-025: accessibility audit (axe-core, WCAG 2 A/AA) of every page, keyboard focus,
        # small screens and Arabic right-to-left
        views = ("overview", "keys", "profiles", "sessions", "team", "billing", "audit")
        if AXE is not None:  # the audit itself works: an image without alt text fails it
            b.js("document.querySelector('#view').append(Object.assign(new Image(), {src: 'x'}))")
            with pytest.raises(AssertionError, match="image-alt"):
                b.audit("self-check")
        for view in views:
            b.js(f"location.hash = '#/{view}'")
            b.wait(PAGE_READY)
            assert b.js("document.activeElement === document.querySelector('#view h1')"), view
            b.audit(view)
        assert b.js("document.querySelector('nav a[aria-current=page]').hash") == "#/audit"
        assert b.js("document.querySelector('.skip').getAttribute('href')") == "#main"

        b.js("document.querySelector('#lang').value = 'ar'")
        b.js("document.querySelector('#lang').dispatchEvent(new Event('change'))")
        b.wait("document.documentElement.dir === 'rtl' && document.documentElement.lang === 'ar'")
        b.wait("document.querySelector('#view h1')?.textContent === 'سجل التدقيق'")
        assert b.js("document.querySelector('nav a').textContent") == "نظرة عامة"
        assert b.js("document.querySelector('#view th').textContent") == "الوقت"
        assert b.js("localStorage.getItem('nexora.dashboard.lang')") == "ar"  # the user chose it
        for view in views:
            b.js(f"location.hash = '#/{view}'")
            b.wait(PAGE_READY)
            b.audit(f"{view} (ar)")
        b.js("location.hash = '#/overview'")
        b.wait("!!document.querySelector('svg.chart')")
        assert "دقيقة هذا الشهر" in b.js("document.body.innerText")
        b.shot("overview-ar")
        # the chart keeps time running left to right; keys and IDs stay left to right
        assert b.js("getComputedStyle(document.querySelector('svg.chart')).direction") == "ltr"

        b.call(
            "Emulation.setDeviceMetricsOverride",
            width=390,
            height=844,
            deviceScaleFactor=1,
            mobile=True,
        )
        for view in ("overview", "keys", "sessions"):
            b.js(f"location.hash = '#/{view}'")
            b.wait(PAGE_READY)
            # nothing wider than the phone: wide tables scroll inside their own box
            assert b.js("document.documentElement.scrollWidth <= window.innerWidth + 1"), view
            b.shot(f"phone-{view}-ar")
        b.js("document.querySelector('#lang').value = 'en'")
        b.js("document.querySelector('#lang').dispatchEvent(new Event('change'))")
        b.wait("document.documentElement.dir === 'ltr'")
        b.shot("phone-sessions-en")
        b.call("Emulation.clearDeviceMetricsOverride")

        b.js("document.querySelector('#signout').click()")
        b.wait("!document.querySelector('#signin').hidden")
        assert b.js("sessionStorage.length") == 0
        assert b.errors == [], b.errors  # no script errors, no CSP violations
    finally:
        b.close()
