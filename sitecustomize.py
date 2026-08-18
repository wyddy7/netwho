"""Imported automatically at interpreter start inside the container.

The Dockerfile sets ``ENV PYTHONPATH=/app``, and Python's ``site`` module
imports ``sitecustomize`` from anywhere on ``sys.path`` — so every Python
process in the image, including ad-hoc ``docker exec ... python`` sessions,
gets the loguru logging guard (see app/logging_guard.py) before any user code
runs.

The app itself installs the same guard in app/config.py, and THAT path fails
loudly if the guard is broken. This one must never break interpreter startup,
so it swallows everything.
"""
try:
    from app.logging_guard import install

    install()
except Exception:  # noqa: BLE001 — interpreter startup must survive anything
    pass
