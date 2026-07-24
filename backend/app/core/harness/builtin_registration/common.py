"""Shared builtins registration primitives."""

from __future__ import annotations

import asyncio
import functools
import inspect
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from app.core.harness.mcp_hub import ToolDef


@dataclass(frozen=True)
class BuiltinToolSpec:
    """Declarative builtin tool — registered via ``_register_specs``."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    is_async: bool = False
    requires_confirmation: bool = False
    # Wrap sync handlers with ``asyncio.to_thread`` (implies ``is_async=True``).
    offload: bool = False


def _offload(fn: Callable[..., str]) -> Callable[..., Awaitable[str]]:
    """Run a sync tool handler in a worker thread so it won't block the event loop.

    The wrapper keeps ``__signature__`` from ``fn`` so ``MCPHub`` kwargs
    filtering still drops unexpected LLM arguments.
    """

    @functools.wraps(fn)
    async def _handler(*args: object, **kwargs: object) -> str:
        return await asyncio.to_thread(fn, *args, **kwargs)

    try:
        _handler.__signature__ = inspect.signature(fn)  # type: ignore[attr-defined]
    except (TypeError, ValueError):
        pass
    return _handler


def _register_specs(hub, specs: Sequence[BuiltinToolSpec]) -> None:
    for spec in specs:
        handler: Callable[..., str | Awaitable[str]] = (
            _offload(spec.handler) if spec.offload else spec.handler
        )
        hub.register_tool(ToolDef(
            name=spec.name,
            description=spec.description,
            parameters=spec.parameters,
            handler=handler,
            is_async=spec.is_async or spec.offload,
            requires_confirmation=spec.requires_confirmation,
        ))
