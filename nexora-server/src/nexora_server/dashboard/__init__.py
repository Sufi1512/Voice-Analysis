"""Admin dashboard (E8): a static single-page app served at ``/dashboard``.

No build step and no third-party scripts: ``static/app.js`` calls the REST API with the
signed-in admin's credentials and renders everything with ``textContent`` (never HTML from
data). The page is served with a strict Content-Security-Policy.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse, Response

STATIC = Path(__file__).resolve().parent / "static"
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
}
FILES = {"app.js": "text/javascript", "app.css": "text/css"}

router = APIRouter(include_in_schema=False)


@router.get("/dashboard")
def dashboard_root() -> Response:
    return RedirectResponse("/dashboard/", status_code=307)


@router.get("/dashboard/")
def dashboard_index() -> Response:
    return FileResponse(STATIC / "index.html", media_type="text/html", headers=SECURITY_HEADERS)


@router.get("/dashboard/static/{name}")
def dashboard_static(name: str) -> Response:
    if name not in FILES:  # fixed list: no path traversal
        return Response(status_code=404)
    return FileResponse(STATIC / name, media_type=FILES[name], headers=SECURITY_HEADERS)
