"""Tests verifying the SSE wire format matches the documented contract."""

from app.sse.utility import construct_sse


class TestSSEContract:

    def test_markdown_event(self):
        result = construct_sse(event="markdown", data="Analyzing the prompt")
        text = result.decode("utf-8")
        assert text.startswith("event: markdown\n")
        assert "data: Analyzing the prompt\n" in text
        assert text.endswith("\n\n")

    def test_text_event(self):
        result = construct_sse(event="text", data="The answer is 42.")
        text = result.decode("utf-8")
        assert "event: text\n" in text
        assert "data: The answer is 42.\n" in text

    def test_error_event(self):
        result = construct_sse(event="error", data="Something failed")
        text = result.decode("utf-8")
        assert "event: error\n" in text
        assert "data: Something failed\n" in text

    def test_done_event(self):
        result = construct_sse(event="done", data="[Done]")
        text = result.decode("utf-8")
        assert "event: done\n" in text
        assert "data: [Done]\n" in text

    def test_multiline_data_uses_multiple_data_fields(self):
        result = construct_sse(event="text", data="Line 1\nLine 2\nLine 3")
        text = result.decode("utf-8")
        assert "data: Line 1\n" in text
        assert "data: Line 2\n" in text
        assert "data: Line 3\n" in text
        assert text.endswith("\n\n")

    def test_no_event_field_when_none(self):
        result = construct_sse(event=None, data="standalone data")
        text = result.decode("utf-8")
        assert not text.startswith("event:")
        assert "data: standalone data\n" in text

    def test_thread_event(self):
        result = construct_sse(event="thread", data='{"thread_id":"12345","parent_message_id":99}')
        text = result.decode("utf-8")
        assert "event: thread\n" in text
        assert '{"thread_id":"12345","parent_message_id":99}' in text

    def test_all_events_return_bytes(self):
        for event_type in ["markdown", "text", "error", "done", "thread"]:
            result = construct_sse(event=event_type, data="test")
            assert isinstance(result, bytes)

    def test_double_newline_terminator(self):
        for event_type in ["markdown", "text", "error", "done", "thread"]:
            result = construct_sse(event=event_type, data="payload")
            assert result.endswith(b"\n\n")
