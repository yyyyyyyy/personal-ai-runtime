"""ContextAssembler budget, priority, and failure isolation."""

from __future__ import annotations

import pytest

from app.assembler.context_assembler import ContextAssembler
from app.context_runtime import ContextFragment, FragmentResult, RuntimeContext


class TestContextAssembler:
    @pytest.mark.asyncio
    async def test_assemble_budget_keeps_small_fragment(self):
        class BigFragment(ContextFragment):
            id: str = "big.frag"

            async def collect(self, ctx):
                return FragmentResult(content="X" * 10000)

        class SmallFragment(ContextFragment):
            id: str = "small.frag"
            priority: int = 30

            async def collect(self, ctx):
                return FragmentResult(content="hello")

        result = await ContextAssembler().assemble(
            [BigFragment(), SmallFragment()],
            RuntimeContext(),
            budget=100,
        )
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_assemble_high_priority_still_budgeted(self):
        class HighPriority(ContextFragment):
            id: str = "high"
            priority: int = 100

            async def collect(self, ctx):
                return FragmentResult(content="H" * 400)

        class LowPriority(ContextFragment):
            id: str = "low"
            priority: int = 10

            async def collect(self, ctx):
                return FragmentResult(content="ok")

        result = await ContextAssembler().assemble(
            [HighPriority(), LowPriority()],
            RuntimeContext(),
            budget=10,
        )
        assert "ok" in result
        assert "H" not in result

    @pytest.mark.asyncio
    async def test_assemble_collect_failure_is_isolated(self, monkeypatch):
        from app.assembler import context_assembler as ca

        logged: list[str] = []

        def _capture_error(msg, *args, **kwargs):
            try:
                logged.append(msg % args if args else str(msg))
            except Exception:
                logged.append(str(msg))

        monkeypatch.setattr(ca.logger, "error", _capture_error)

        class Boom(ContextFragment):
            id: str = "boom"

            async def collect(self, ctx):
                raise RuntimeError("collect broke")

        class Ok(ContextFragment):
            id: str = "ok"
            priority: int = 10

            async def collect(self, ctx):
                return FragmentResult(content="alive")

        result = await ContextAssembler().assemble(
            [Boom(), Ok()],
            RuntimeContext(),
            budget=2000,
        )
        assert "alive" in result
        assert any("collect broke" in m for m in logged)

    def test_fragment_result_token_estimate(self):
        r = FragmentResult(content="")
        assert r.token_count == 0
        assert FragmentResult(content="hello").token_count == 1
        assert FragmentResult(content="X" * 100).token_count == 25
