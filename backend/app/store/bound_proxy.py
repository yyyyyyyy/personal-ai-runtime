"""Bound / lazy module-level singleton proxy — no Runtime *static* imports.

Used by Store (bound by RuntimeContainer) and by Runtime module singletons
(``_LazyProxy = BoundProxy`` with an immediate factory).

If a caller touches ``db`` / ``vector_store`` before importing
``runtime_container``, the first attribute access lazily loads the container
via ``importlib`` (not visible to ``check_layer_deps`` AST R2) so scripts and
tests keep working without an import-order footgun.
"""

from __future__ import annotations

import importlib
from typing import Any, Callable


class BoundProxy:
    """Transparent forwarder to a factory-provided instance.

    Attribute writes/deletes stay on the proxy (unittest.mock.patch friendly).

    - Store: ``BoundProxy()`` then ``bind(factory)`` from RuntimeContainer
      (or auto-bind on first use).
    - Runtime: ``BoundProxy(lambda: runtime.x)`` (alias ``_LazyProxy``).
    """

    def __init__(self, factory: Callable[[], Any] | None = None) -> None:
        self.__dict__["_factory"] = factory

    def bind(self, factory: Callable[[], Any]) -> None:
        self.__dict__["_factory"] = factory

    def _ensure_bound(self) -> Callable[[], Any]:
        factory = self.__dict__.get("_factory")
        if factory is not None:
            return factory
        # Lazy bootstrap: load RuntimeContainer which calls bind_*_factory.
        importlib.import_module("app.core.runtime.runtime_container")
        factory = self.__dict__.get("_factory")
        if factory is None:
            raise RuntimeError(
                "Store singleton not bound after loading runtime_container"
            )
        return factory

    def _resolve(self) -> Any:
        return self._ensure_bound()()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._resolve(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        self.__dict__[name] = value

    def __delattr__(self, name: str) -> None:
        if name in self.__dict__:
            del self.__dict__[name]
        else:
            delattr(self._resolve(), name)

    def __bool__(self) -> bool:
        factory = self.__dict__.get("_factory")
        if factory is None:
            try:
                factory = self._ensure_bound()
            except Exception:
                return False
        return bool(factory())

    def __repr__(self) -> str:
        try:
            return repr(self._resolve())
        except Exception as exc:
            return f"<BoundProxy unbound-or-error: {exc}>"
