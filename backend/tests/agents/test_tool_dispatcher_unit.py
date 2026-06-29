"""Unit tests for ToolDispatcher message building."""


class MockConversation:
    def save_tool_result(self, result, call_id):
        pass


class MockKernel:
    async def invoke_capability(self, name, args, actor, correlation_id, execution_id):
        return {"status": "success", "result": '{"ok": true}'}


class TestToolDispatcherMessages:
    def test_build_tool_call_messages(self):
        from app.core.agents.tool_dispatcher import ToolDispatcher
        conv = MockConversation()
        td = ToolDispatcher(kernel=MockKernel(), conversation=conv)
        tc_data = [
            {"id": "tc1", "function_name": "read_file", "arguments": '{"path": "/tmp/x"}'},
            {"id": "tc2", "function_name": "web_search", "arguments": '{"q": "test"}'},
        ]
        msgs = td.build_tool_call_messages("some content", tc_data)
        assert len(msgs) == 1  # single assistant message
        assert msgs[0]["role"] == "assistant"
        assert msgs[0]["content"] == "some content"
        assert len(msgs[0]["tool_calls"]) == 2
        assert msgs[0]["tool_calls"][0]["function"]["name"] == "read_file"

    def test_build_tool_call_messages_empty(self):
        from app.core.agents.tool_dispatcher import ToolDispatcher
        td = ToolDispatcher(kernel=MockKernel(), conversation=MockConversation())
        msgs = td.build_tool_call_messages("", [])
        assert len(msgs) == 1
        assert msgs[0]["role"] == "assistant"
        assert msgs[0]["content"] is None
