"""Backend guard / verify scripts package.

Canonical invocation (from ``backend/``)::

    python -m scripts.verify_rebuild
    python -m scripts.check_boundary

Direct ``python scripts/<name>.py`` also works: each entrypoint prepends
``backend/`` onto ``sys.path`` before importing ``scripts._bootstrap``.
"""
