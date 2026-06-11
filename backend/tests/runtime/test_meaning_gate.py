"""Meaning Gate — chat destiny framing guard (P0.3 extended)."""

import pytest

from app.core.runtime.meaning_gate import (
    MeaningGateClassifier,
    gate_assistant_text,
    gate_stream_delta,
)


class TestRegexFastPath:
    def test_softens_destiny_framing(self):
        out, warnings = gate_assistant_text("你就是这样的人，适合创业。")
        assert "你就是这样的人" not in out
        assert warnings

    def test_softens_niyizhi_type(self):
        out, warnings = gate_assistant_text("你一直是冒险型的人")
        assert "你一直是" not in out or "系统注意到" in out
        assert warnings

    def test_softens_benlaijiushi(self):
        out, warnings = gate_assistant_text("你本来就是偏感性的")
        assert warnings or "你本来就是" not in out

    def test_softens_tiansheng_shihe(self):
        out, warnings = gate_assistant_text("你天生适合做管理")
        assert warnings or "天生适合" not in out

    def test_softens_nishi_label(self):
        out, warnings = gate_assistant_text("你是创业者，这很明显。")
        assert warnings

    # --- Extended patterns (P0.3) ---

    def test_softens_guizili(self):
        out, warnings = gate_assistant_text("你骨子里就是个创业者。")
        assert warnings

    def test_softens_xingge_jueding(self):
        out, warnings = gate_assistant_text("你的性格决定了你会一直这样。")
        assert warnings

    def test_softens_yongyuan_buhui(self):
        out, warnings = gate_assistant_text("你永远不会改变这一点。")
        assert warnings

    def test_softens_zhebeizi(self):
        out, warnings = gate_assistant_text("你这辈子都会如此。")
        assert warnings

    def test_softens_zhuding(self):
        out, warnings = gate_assistant_text("你注定会走向创业。")
        assert warnings

    def test_softens_congxiao(self):
        out, warnings = gate_assistant_text("你从小就是独来独往的。")
        assert warnings

    def test_softens_gaibuliao(self):
        out, warnings = gate_assistant_text("你改不了这个习惯。")
        assert warnings

    def test_softens_nizheleiren(self):
        out, warnings = gate_assistant_text("你这类人往往会选择冒险。")
        assert warnings

    def test_softens_benzhi_shi(self):
        out, warnings = gate_assistant_text("你本质上就是一个追求自由的人。")
        assert warnings

    def test_softens_zhenzhengdeni(self):
        out, warnings = gate_assistant_text("真正的你是一个理想主义者。")
        assert warnings


class TestOutcomeEpilogue:
    def test_blocks_dangnian_xuanze(self):
        out, warnings = gate_assistant_text("事实证明你当年的选择是正确的。")
        assert warnings

    def test_blocks_zhengming_dui(self):
        out, warnings = gate_assistant_text("这也证明了你当时是对的。")
        assert warnings

    def test_blocks_shishi_zhengming(self):
        out, warnings = gate_assistant_text("事实证明你注定会成功。")
        assert warnings

    def test_blocks_xianzai_huitou(self):
        out, warnings = gate_assistant_text("现在回头看，你当初的决定是对的。")
        assert warnings

    def test_blocks_zuizhong_zhengming(self):
        out, warnings = gate_assistant_text("时间最终证明了你的选择。")
        assert warnings

    def test_blocks_jieju_yinzheng(self):
        out, warnings = gate_assistant_text("结局印证了你当初的判断。")
        assert warnings


class TestCleanText:
    def test_clean_text_unchanged(self):
        text = "根据你的目标，建议先列一份 pros/cons。"
        out, warnings = gate_assistant_text(text)
        assert out == text
        assert not warnings

    def test_clean_question_unchanged(self):
        text = "你想怎么安排这周的优先级？"
        out, warnings = gate_assistant_text(text)
        assert out == text
        assert not warnings

    def test_clean_suggestion_unchanged(self):
        text = "你可以考虑每天冥想10分钟来缓解压力。"
        out, warnings = gate_assistant_text(text)
        assert out == text
        assert not warnings


class TestStreamingGate:
    def test_sentence_boundary_gating(self):
        acc, delta, warnings = gate_stream_delta("你是一个", "追求自由的人。")
        assert warnings or len(acc) > 0

    def test_partial_sentence_passthrough(self):
        acc, delta, warnings = gate_stream_delta("你一直以来都在努力", "工作，但你是")
        assert not warnings  # sentence not complete
        assert delta == "工作，但你是"


class TestMeaningGateClassifierParse:
    def test_parse_true(self):
        result = MeaningGateClassifier._parse_response('{"is_destiny": true, "reason": "将推测表述为定论"}')
        assert result["is_destiny"] is True
        assert result["reason"]

    def test_parse_false(self):
        result = MeaningGateClassifier._parse_response('{"is_destiny": false, "reason": "仅是建议"}')
        assert result["is_destiny"] is False

    def test_parse_markdown_fence(self):
        result = MeaningGateClassifier._parse_response(
            '```json\n{"is_destiny": true, "reason": "test"}\n```'
        )
        assert result["is_destiny"] is True

    def test_parse_fallback_true(self):
        result = MeaningGateClassifier._parse_response("true")
        assert result["is_destiny"] is True

    def test_parse_fallback_false(self):
        result = MeaningGateClassifier._parse_response("not destiny")
        assert result["is_destiny"] is False


@pytest.mark.skip(
    reason="Ollama classifier requires a running Ollama server; run manually with --ollama",
)
class TestMeaningGateClassifierLive:
    @pytest.mark.asyncio
    async def test_classify_destiny(self):
        classifier = MeaningGateClassifier()
        result = await classifier.classify("你骨子里就是一个喜欢孤独的人")
        assert isinstance(result, dict)
        assert "is_destiny" in result

    @pytest.mark.asyncio
    async def test_classify_safe(self):
        classifier = MeaningGateClassifier()
        result = await classifier.classify("你可以考虑调整你的作息时间")
        assert isinstance(result, dict)
