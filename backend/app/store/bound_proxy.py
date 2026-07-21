"""Bound / lazy module-level singleton proxy — no Runtime imports.

Used by Store (bound later by RuntimeContainer) and by Runtime module
singletons (``_LazyProxy = BoundProxy`` with an immediate factory).
"""

from __future__ import annotations

from typing import Any, Callable


class BoundProxy:
    """Transparent forwarder to a factory-provided instance.

    Attribute writes/deletes stay on the proxy (unittest.mock.patch friendly).

    - Store: ``BoundProxy()`` then ``bind(factory)`` from RuntimeContainer.
    - Runtime: ``BoundProxy(lambda: runtime.x)`` (alias ``_LazyProxy``).
    """

    def __init__(self, factory: Callable[[], Any] | None = None) -> None:
        self.__dict__["_factory"] = factory

    def bind(self, factory: Callable[[], Any]) -> None:
        self.__dict__["_factory"] = factory

    def _resolve(self) -> Any:
        factory = self.__dict__.get("_factory")
        if factory is None:
            raise RuntimeError(
                "Store singleton not bound; import app.core.runtime.runtime_container first"
            )
        return factory()

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
            return False
        return bool(factory())

    def __repr__(self) -> str:
        try:
            return repr(self._resolve())
        except Exception as exc:
            return f"<BoundProxy unbound-or-error: {exc}>"
