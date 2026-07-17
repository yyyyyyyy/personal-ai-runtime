"""Tests for Context Runtime Stage 3 — PR-1 to PR-8."""



# ═══════════════════════════════════════════════════════════════════════════
# PR-1: Fragment Metadata
# ═══════════════════════════════════════════════════════════════════════════

class TestFragmentMetadata:
    """验证 ContextFragment 的元数据字段。"""

    def test_fragment_metadata_defaults(self):
        """新 Fragment 有默认 priority=50, max_tokens=2000, tags=frozenset()。"""
        from app.context_runtime import ContextFragment

        f = ContextFragment()
        assert f.id == ""
        assert f.priority == 50
        assert f.max_tokens == 2000
        assert f.tags == frozenset()

    def test_fragment_custom_metadata(self):
        """可以自定义 metadata。"""
        from app.context_runtime import ContextFragment

        f = ContextFragment(
            id="test.frag",
            priority=80,
            max_tokens=4000,
            tags=frozenset({"scenario", "test"}),
        )
        assert f.id == "test.frag"
        assert f.priority == 80
        assert f.max_tokens == 4000
        assert f.tags == frozenset({"scenario", "test"})


# ═══════════════════════════════════════════════════════════════════════════
# Prompt Artifact Identity
# ═══════════════════════════════════════════════════════════════════════════

class TestPromptArtifactIdentity:
    """Identity is canonical in PromptArtifactLoader, not a Fragment."""

    def test_identity_in_prompt_artifact(self):
        import asyncio

        from app.chat.prompt_artifact import (
            IDENTITY_ARTIFACT,
            PromptArtifactContext,
            PromptArtifactLoader,
        )

        result = asyncio.run(
            PromptArtifactLoader().load(
                PromptArtifactContext(available_tools=[], project_root="/tmp", stage="chat"),
            ),
        )
        assert IDENTITY_ARTIFACT in result
        assert "Personal AI Runtime" in result
        assert "Helpful" in result


# ═══════════════════════════════════════════════════════════════════════════
# PR-3: QueryAnalyzer
# ═══════════════════════════════════════════════════════════════════════════

class TestQueryAnalyzer:
    """验证规则匹配意图分析。"""

    def test_query_analyzer_planning(self):
        from app.core.runtime.governance.query_analyzer import QueryAnalyzer

        qa = QueryAnalyzer()
        result = qa.analyze("帮我规划下周的工作安排")
        assert "planning" in result.tags

    def test_query_analyzer_review(self):
        from app.core.runtime.governance.query_analyzer import QueryAnalyzer

        qa = QueryAnalyzer()
        result = qa.analyze("本周总结一下进展")
        assert "review" in result.tags

    def test_query_analyzer_coding(self):
        from app.core.runtime.governance.query_analyzer import QueryAnalyzer

        qa = QueryAnalyzer()
        result = qa.analyze("帮我修复这个 bug")
        assert "coding" in result.tags

    def test_query_analyzer_multiple_tags(self):
        from app.core.runtime.governance.query_analyzer import QueryAnalyzer

        qa = QueryAnalyzer()
        result = qa.analyze("帮我规划代码重构和本周回顾")
        assert "planning" in result.tags
        assert "coding" in result.tags
        assert "review" in result.tags

    def test_query_analyzer_empty(self):
        from app.core.runtime.governance.query_analyzer import QueryAnalyzer

        qa = QueryAnalyzer()
        result = qa.analyze("")
        assert result.tags == set()

    def test_query_analyzer_no_match(self):
        from app.core.runtime.governance.query_analyzer import QueryAnalyzer

        qa = QueryAnalyzer()
        result = qa.analyze("你好")
        assert result.tags == set()

    def test_query_analyzer_no_llm_dependency(self):
        """QueryAnalyzer 不依赖 LLM，只做规则匹配。"""
        from app.core.runtime.governance.query_analyzer import QueryAnalyzer

        qa = QueryAnalyzer()
        # 不需要 mock LLM
        result = qa.analyze("test string")
        assert isinstance(result.tags, set)


# ═══════════════════════════════════════════════════════════════════════════
# PR-4: FragmentSelector
# ═══════════════════════════════════════════════════════════════════════════

class TestFragmentSelector:
    """验证 Fragment 选择逻辑。"""

    def test_selector_core_tier_fragments(self):
        """无特定意图时，Core Tier + Priority Tier 被选中。"""
        from app.context_runtime import FragmentRegistry
        from app.core.runtime.governance.fragment_selector import (
            CORE_TIER_FRAGMENT_IDS,
            FragmentSelector,
        )
        from app.core.runtime.governance.query_analyzer import AnalysisResult
        from app.fragments.register import register_all_fragments

        registry = FragmentRegistry()
        register_all_fragments(registry)

        selector = FragmentSelector(registry)
        selected = selector.select(AnalysisResult(tags=set()))
        ids = {f.id for f in selected}
        for fid in CORE_TIER_FRAGMENT_IDS:
            assert fid in ids
        assert "core.conversation_state" in ids

    def test_selector_scenario_fragments_planning(self):
        """planning 标签触发 core.background。"""
        from app.context_runtime import FragmentRegistry
        from app.core.runtime.governance.fragment_selector import FragmentSelector
        from app.core.runtime.governance.query_analyzer import QueryAnalyzer
        from app.fragments.register import register_all_fragments

        registry = FragmentRegistry()
        register_all_fragments(registry)

        qa = QueryAnalyzer()
        analysis = qa.analyze("帮我规划下周")

        selector = FragmentSelector(registry)
        selected = selector.select(analysis)
        ids = {f.id for f in selected}
        assert "core.background" in ids
        assert "core.goals" in ids

    def test_selector_no_duplicates(self):
        """不重复选择同一 Fragment。"""
        from app.context_runtime import FragmentRegistry
        from app.core.runtime.governance.fragment_selector import FragmentSelector
        from app.core.runtime.governance.query_analyzer import AnalysisResult
        from app.fragments.register import register_all_fragments

        registry = FragmentRegistry()
        register_all_fragments(registry)

        selector = FragmentSelector(registry)
        selected = selector.select(AnalysisResult(tags={"planning"}))
        ids = [f.id for f in selected]
        assert len(ids) == len(set(ids))


# ═══════════════════════════════════════════════════════════════════════════
# PR-5: ContextAssembler
# ═══════════════════════════════════════════════════════════════════════════

class TestContextAssembler:
    """验证 Context 组装逻辑。"""

    def test_assemble_priority_order(self):
        """按 priority 降序组装。"""
        from app.assembler.context_assembler import ContextAssembler
        from app.context_runtime import ContextFragment, RuntimeContext

        f1 = ContextFragment(id="f1", priority=10, tags=frozenset({"low"}))
        f2 = ContextFragment(id="f2", priority=90, tags=frozenset({"high"}))

        import asyncio
        assembler = ContextAssembler()
        result = asyncio.run(assembler.assemble(
            [f1, f2], RuntimeContext(), budget=2000,
        ))
        # f2 (priority=90) 应该出现在 f1 之前
        # 两者都为空内容，所以结果也为空
        assert result == ""  # both return empty content

    def test_assemble_budget_limit(self):
        """超 budget 时跳过低优先级 Fragment。"""
        from app.assembler.context_assembler import ContextAssembler
        from app.context_runtime import ContextFragment, FragmentResult, RuntimeContext

        class BigFragment(ContextFragment):
            id: str = "big.frag"
            async def collect(self, ctx):
                return FragmentResult(content="X" * 10000)

        class SmallFragment(ContextFragment):
            id: str = "small.frag"
            priority: int = 30
            async def collect(self, ctx):
                return FragmentResult(content="hello")

        import asyncio
        assembler = ContextAssembler()
        result = asyncio.run(assembler.assemble(
            [BigFragment(), SmallFragment()],
            RuntimeContext(),
            budget=100,  # 极小预算
        ))
        # BigFragment 的 content 约 2500 tokens，超过 budget 100
        # SmallFragment 只有 "hello" (约 1 token)
        assert "hello" in result

    def test_assemble_identity_never_dropped(self):
        """Identity Fragment (priority=100) 永不被丢弃。"""
        from app.assembler.context_assembler import ContextAssembler
        from app.context_runtime import ContextFragment, FragmentResult, RuntimeContext

        class Identity(ContextFragment):
            id: str = "identity"
            priority: int = 100
            async def collect(self, ctx):
                return FragmentResult(content="I am AI")

        class HugeContext(ContextFragment):
            id: str = "huge"
            priority: int = 50
            async def collect(self, ctx):
                return FragmentResult(content="X" * 20000)

        import asyncio
        assembler = ContextAssembler()
        result = asyncio.run(assembler.assemble(
            [Identity(), HugeContext()],
            RuntimeContext(),
            budget=10,  # 极小预算
        ))
        # Identity 永不被丢弃，HugeContext 会被跳过
        assert "I am AI" in result
        assert "X" not in result  # HugeContext dropped due to budget

    def test_estimate_tokens(self):
        # FragmentResult.__post_init__
        # now computes token count inline as max(1, len(content) // 4).
        from app.context_runtime import FragmentResult

        r = FragmentResult(content="")
        assert r.token_count == 0
        r2 = FragmentResult(content="hello")
        assert r2.token_count == 1  # len=5 // 4 = 1
        r3 = FragmentResult(content="X" * 100)
        assert r3.token_count == 25  # 100 // 4 = 25


# ═══════════════════════════════════════════════════════════════════════════
# PR-6: ConversationStateFragment
# ═══════════════════════════════════════════════════════════════════════════

class TestConversationStateFragment:
    """验证会话状态 Fragment。"""

    def test_conversation_state_fragment(self):
        from app.context_runtime import RuntimeContext
        from app.fragments.universal.conversation_state import ConversationStateFragment

        f = ConversationStateFragment()
        assert f.id == "core.conversation_state"
        assert f.priority == 80  # reduced from 90: Brain handles full history separately
        assert "conversation" in f.tags

        # 新会话（无 conversation_id）— 不注入占位文案，避免噪声
        import asyncio
        result = asyncio.run(f.collect(RuntimeContext(conversation_id="")))
        assert result.content == ""

    def test_returns_summary_not_raw_transcript(self):
        """不返回原始全文 transcript。"""
        from app.fragments.universal.conversation_state import ConversationStateFragment

        f = ConversationStateFragment()
        assert f.max_tokens == 500  # compact cognitive summary; Brain injects full history


# ═══════════════════════════════════════════════════════════════════════════
# PR-7: BackgroundContextFragment (was MemoryContextFragment)
# ═══════════════════════════════════════════════════════════════════════════

class TestBackgroundContextFragment:
    """验证背景 Fragment 只读。"""

    def test_background_fragment(self, monkeypatch):
        from app.context_runtime import RuntimeContext
        from app.fragments.universal.background import BackgroundContextFragment

        f = BackgroundContextFragment()
        assert f.id == "core.background"
        assert f.priority == 58
        assert {"memory", "world"}.issubset(f.tags)  # merged from both sources

        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_world_context",
            lambda: "## Current Life Snapshot (last 30 days)\n- Active Goals: 1",
        )

        # 无 user_message 时仅返回 world snapshot（不需用户输入）
        import asyncio
        result = asyncio.run(f.collect(RuntimeContext(user_message="")))
        assert "Life Snapshot" in result.content  # world snapshot always present

    def test_background_fragment_is_read_only(self):
        """BackgroundFragment 没有 write/emit 方法。"""
        from app.fragments.universal.background import BackgroundContextFragment

        f = BackgroundContextFragment()
        assert not hasattr(f, 'store_memory')
        assert not hasattr(f, 'emit_event')
        assert not hasattr(f, 'write')



# ═══════════════════════════════════════════════════════════════════════════
# 集成测试：端到端 Pipeline
# ═══════════════════════════════════════════════════════════════════════════

class TestEndToEndPipeline:
    """验证完整 Pipeline: 消息 → 分析 → 选择 → 组装。"""

    def test_full_pipeline_general_message(self):
        """普通消息的完整 Pipeline。"""
        from app.assembler.context_assembler import ContextAssembler
        from app.context_runtime import FragmentRegistry, RuntimeContext
        from app.core.runtime.governance.fragment_selector import (
            CORE_TIER_FRAGMENT_IDS,
            FragmentSelector,
        )
        from app.core.runtime.governance.query_analyzer import QueryAnalyzer
        from app.fragments.register import register_all_fragments

        registry = FragmentRegistry()
        register_all_fragments(registry)

        qa = QueryAnalyzer()
        selector = FragmentSelector(registry)
        assembler = ContextAssembler()

        msg = "你好，今天天气怎么样"
        fragments = selector.select(qa.analyze(msg))
        ids = {f.id for f in fragments}
        for fid in CORE_TIER_FRAGMENT_IDS:
            assert fid in ids

        import asyncio
        result = asyncio.run(assembler.assemble(fragments, RuntimeContext(user_message=msg)))
        assert isinstance(result, str)

    def test_pipeline_planning_message(self):
        """规划类消息触发 core.background。"""
        from app.context_runtime import FragmentRegistry
        from app.core.runtime.governance.fragment_selector import FragmentSelector
        from app.core.runtime.governance.query_analyzer import QueryAnalyzer
        from app.fragments.register import register_all_fragments

        registry = FragmentRegistry()
        register_all_fragments(registry)

        qa = QueryAnalyzer()
        msg = "帮我规划下周的工作"
        analysis = qa.analyze(msg)
        assert "planning" in analysis.tags

        selector = FragmentSelector(registry)
        fragments = selector.select(analysis)
        ids = {f.id for f in fragments}
        assert "core.background" in ids
        assert "core.goals" in ids
