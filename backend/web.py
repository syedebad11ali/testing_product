"""Serves the static site (frontend/ and public/assets/) from the same Flask app.

On Vercel, ``public/assets`` is also served by the CDN at the same ``/assets/...`` URL;
these routes are what make plain ``python -m backend.app`` work locally.
"""
from __future__ import annotations

from urllib.parse import quote

from flask import Flask, Response, redirect, request, send_from_directory

from backend.security.guards import current_session

from backend.config import Settings


def register_web(app: Flask, settings: Settings) -> None:
    fe, assets = settings.frontend_dir, settings.assets_dir

    def private_page(filename: str, login_next: str | None = None):
        """Login-first: the application pages need a real server-side session (user, guest or admin). Without one the visitor is
        sent to the login page. ``login_next`` is a fixed server-side path, never request input, so this cannot be an open redirect.
        These responses depend on the session cookie, so shared caches must not keep them."""
        if not current_session():
            return redirect("/login" + (f"?next={login_next}" if login_next else ""), code=302)
        resp = send_from_directory(fe, filename)
        resp.headers["Cache-Control"] = "private, no-cache"
        resp.headers["Vary"] = "Cookie"
        return resp

    @app.get("/")
    @app.get("/index.html")
    def index():
        return private_page("index.html")

    @app.get("/orv.html")  # legacy URL kept alive
    def legacy_owner_verification():
        return redirect("/#owner-verification", code=301)

    @app.get("/nice-try")
    @app.get("/nice-try.html")
    def nice_try():
        # Static joke page. The *decision* to redirect here is made by the server login endpoint (phase 4).
        return send_from_directory(fe, "nice-try.html")

    @app.get("/privacy")
    @app.get("/privacy.html")
    def privacy_page():
        return send_from_directory(fe, "privacy.html")

    @app.get("/listings")
    @app.get("/listings.html")
    def listings_page():
        return private_page("listings.html", "/listings")

    @app.get("/messages")
    @app.get("/messages.html")
    def messages_page():
        # The page itself is static; every message call is authorised by the API. Signed-out visitors go to login first.
        sess = current_session()
        if not sess or sess["role"] == "guest":  # guests cannot use messaging: send them to the real login
            return redirect("/login?next=" + quote("/messages" + (("?" + request.query_string.decode()) if request.query_string else ""), safe="/"), code=302)
        return send_from_directory(fe, "messages.html")

    @app.get("/login")
    @app.get("/signup")
    def login_page():
        return send_from_directory(fe, "login.html")

    @app.get("/developer-login")
    @app.get("/developer-login.html")
    def developer_login_page():
        # Static page: the decision (admin session vs /nice-try) is made by POST /api/v1/auth/developer-login.
        return send_from_directory(fe, "developer-login.html")

    @app.get("/admin")
    @app.get("/admin.html")
    def admin_page():
        # Authorisation is decided here, from the server-side session -- not by hiding a link.
        sess = current_session()
        if not sess or sess["role"] != "admin" or sess["must_change_password"]:
            return redirect("/login" + ("?change=1" if sess and sess["must_change_password"] else ""), code=302)
        return send_from_directory(fe, "admin.html")

    @app.get("/robots.txt")
    def robots():
        base = request.url_root.rstrip("/")
        body = f"User-agent: *\nDisallow: /admin\nDisallow: /api/\nDisallow: /nice-try\nSitemap: {base}/sitemap.xml\n"
        return Response(body, mimetype="text/plain")

    @app.get("/sitemap.xml")
    def sitemap():
        base = request.url_root.rstrip("/")
        urls = "".join(f"<url><loc>{base}{path}</loc></url>" for path in ("/", "/login", "/privacy", "/listings"))
        xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
        return Response(xml, mimetype="application/xml")

    @app.get("/css/<path:filename>")
    def css(filename):
        return send_from_directory(fe / "css", filename)

    @app.get("/js/<path:filename>")
    def js(filename):
        return send_from_directory(fe / "js", filename)

    @app.get("/assets/<path:filename>")
    def assets_files(filename):
        return send_from_directory(assets, filename)

    # Embeddable chat widget — public URLs must not change (third-party sites embed them).
    @app.get("/chatbot-demo")
    def widget_demo():
        return send_from_directory(fe / "widget", "demo.html")

    @app.get("/static/chatbot.js")
    def widget_js():
        return send_from_directory(fe / "widget", "chatbot.js")

    @app.get("/static/chatbot.css")
    def widget_css():
        return send_from_directory(fe / "widget", "chatbot.css")
