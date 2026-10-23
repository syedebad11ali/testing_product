"""Serves the static site (frontend/ and public/assets/) from the same Flask app.

On Vercel, ``public/assets`` is also served by the CDN at the same ``/assets/...`` URL;
these routes are what make plain ``python -m backend.app`` work locally.
"""
from __future__ import annotations

from flask import Flask, redirect, send_from_directory

from backend.config import Settings


def register_web(app: Flask, settings: Settings) -> None:
    fe, assets = settings.frontend_dir, settings.assets_dir

    @app.get("/")
    def index():
        return send_from_directory(fe, "index.html")

    @app.get("/orv.html")  # legacy URL kept alive
    def legacy_owner_verification():
        return redirect("/#owner-verification", code=301)

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
