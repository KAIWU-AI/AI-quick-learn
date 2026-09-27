from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import httpx
from openai import APIConnectionError

from demo_visualizer import Trace
from demo_visualizer.report import answer_html, usage_total, write_trace
from test_demos import demo2, demo3, response, scripted_client


class TraceTests(unittest.TestCase):
    def test_answer_formatting_does_not_enable_html_or_links(self) -> None:
        value = "**90 分钟**，`<script>`，<img src=x> [link](javascript:alert(1))"
        rendered = answer_html(value)
        self.assertIn("<strong>90 分钟</strong>", rendered)
        self.assertIn("<code>&lt;script&gt;</code>", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img", rendered)
        self.assertNotIn("<a", rendered)

    def test_conversation_snapshots_actual_requests_and_keeps_original_state(self) -> None:
        client, requests = scripted_client([response("记住了"), response("蓝鲸17")])
        with redirect_stdout(io.StringIO()), Trace(2, "test-model") as trace:
            demo2.run_conversation(client, "test-model", ["蓝鲸17", "代号？"], trace)
        self.assertEqual(trace.status, "completed")
        self.assertEqual(
            [event.kind for event in trace.events],
            ["user", "request", "response", "memory", "answer"] * 2,
        )
        recorded = [event for event in trace.events if event.kind == "request"]
        self.assertEqual(len(recorded[0].data["request"]["input"]), 1)
        self.assertEqual(recorded[1].data["request"]["input"][0], requests[1]["input"][0])
        self.assertIn("opaque-state", json.dumps(requests))
        self.assertNotIn("opaque-state", repr(trace.events))
        self.assertTrue(all("tools" not in event.data["request"] for event in recorded))
        memory = [event for event in trace.events if event.kind == "memory"]
        self.assertEqual(memory[0].data["after"], 3)
        self.assertEqual(len(memory[0].data["history"]), 3)
        self.assertEqual(memory[1].data["before"], 3)

    def test_tool_sequence_pairing_and_actual_feedback(self) -> None:
        client, requests = scripted_client([
            response(calls=[("list", "list_courses", "{}")]),
            response(calls=[
                ("a", "get_course", '{"course_id":"api"}'),
                ("b", "get_course", '{"course_id":"memory"}'),
                ("c", "get_course", '{"course_id":"tools"}'),
            ]),
            response(calls=[("sum", "sum_minutes", '{"minutes":[20,30,40]}')]),
            response("api → memory → tools，总计 90 分钟"),
        ])
        with redirect_stdout(io.StringIO()), Trace(3, "test-model") as trace:
            answer = demo3.run_agent(client, "test-model", "全部课程时长", trace=trace)
        self.assertIn("90", answer)
        self.assertEqual(len(requests), 4)
        calls = [event for event in trace.events if event.kind == "tool_call"]
        results = [event for event in trace.events if event.kind == "tool_result"]
        self.assertEqual([event.data["call_id"] for event in calls], ["list", "a", "b", "c", "sum"])
        self.assertEqual([event.data["call_id"] for event in calls], [event.data["call_id"] for event in results])
        self.assertEqual(results[-1].data["output"], {"total_minutes": 90})
        events = trace.events
        for event in calls:
            position = events.index(event)
            self.assertEqual([item.kind for item in events[position:position + 3]], ["tool_call", "tool_result", "memory"])
        request_events = [event for event in events if event.kind == "request"]
        self.assertEqual(len(request_events[0].data["request"]["input"]), 1)
        self.assertEqual(events[-1].kind, "final")
        self.assertEqual(trace.status, "completed")
        self.assertEqual(
            [item["call_id"] for item in request_events[2].data["request"]["input"] if item.get("type") == "function_call_output"],
            ["list", "a", "b", "c"],
        )

    def test_reset_is_visible_without_destroying_trace_or_resetting_budget(self) -> None:
        client, requests = scripted_client([response("记住了"), response("没有代号")])
        with mock.patch("builtins.input", side_effect=["蓝鲸17", "/reset", "代号？"]), redirect_stdout(io.StringIO()), Trace(2) as trace:
            demo2.interactive_chat(client, "test", 2, trace)
        reset = next(event for event in trace.events if event.kind == "reset")
        self.assertEqual(reset.data, {"before": 3, "after": 0, "history": []})
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[1]["input"], [{"role": "user", "content": "代号？"}])
        self.assertEqual(len(trace.events[3].data["history"]), 3)
        self.assertEqual([event.step for event in trace.events if event.kind == "request"], [1, 2])

    def test_errors_and_limits_persist_partial_report_without_final_answer(self) -> None:
        for returned in (response(status="incomplete"), response(), response(calls=[("one", "list_courses", "{}")])):
            with self.subTest(status=returned.status, output=returned.output):
                client, _ = scripted_client([returned])
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "报告 folder" / "result.html"
                    with redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
                        with Trace(3, "test", path) as trace:
                            demo3.run_agent(client, "test", "test", max_steps=1, trace=trace)
                    document = path.read_text(encoding="utf-8")
                self.assertEqual(trace.status, "failed")
                self.assertEqual(trace.events[-1].kind, "error")
                self.assertFalse(any(event.kind == "final" for event in trace.events))
                self.assertIn("运行失败", document)
                self.assertIn("尚未获得回答", document)
                self.assertIn("完整返回 / RESPONSE", document)

    def test_failed_conversation_records_response_but_does_not_commit_memory(self) -> None:
        client, _ = scripted_client([response(status="incomplete")])
        history = [{"role": "user", "content": "已有历史"}]
        before = copy.deepcopy(history)
        with redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
            with Trace(2) as trace:
                demo2.chat_turn(client, "test", history, "新问题", trace)
        self.assertEqual(history, before)
        self.assertFalse(any(event.kind == "memory" for event in trace.events))
        self.assertTrue(next(event for event in trace.events if event.kind == "response").error)

    def test_recovered_tool_error_is_not_final_run_failure(self) -> None:
        client, _ = scripted_client([
            response(calls=[("bad", "get_course", '{"course_id":"bad"}')]),
            response(calls=[("good", "get_course", '{"course_id":"api"}')]),
            response("修正完成"),
        ])
        with redirect_stdout(io.StringIO()), Trace(3) as trace:
            demo3.run_agent(client, "test", "test", trace=trace)
        results = [event for event in trace.events if event.kind == "tool_result"]
        self.assertTrue(results[0].error)
        self.assertFalse(results[1].error)
        self.assertEqual(trace.status, "completed")

    def test_api_failure_is_sanitized_and_snapshot_exists_before_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.html"
            client = mock.Mock()

            def fail(**kwargs):
                self.assertIn("发送模型请求", path.read_text(encoding="utf-8"))
                raise APIConnectionError(
                    message="private-token-must-not-appear",
                    request=httpx.Request("POST", "https://example.invalid"),
                )

            client.responses.create.side_effect = fail
            with redirect_stdout(io.StringIO()), self.assertRaises(APIConnectionError):
                with Trace(2, "test", path) as trace:
                    demo2.run_conversation(client, "test", ["test"], trace)
            document = path.read_text(encoding="utf-8")
        self.assertEqual([event.kind for event in trace.events], ["user", "request", "error"])
        self.assertNotIn("private-token-must-not-appear", document)
        self.assertIn("APIConnectionError", document)

    def test_keyboard_interrupt_is_not_swallowed(self) -> None:
        with self.assertRaises(KeyboardInterrupt):
            with Trace(3) as trace:
                raise KeyboardInterrupt
        self.assertEqual(trace.status, "interrupted")
        self.assertTrue(trace.events[-1].error)

    def test_html_escapes_every_payload_and_hashes_only_trusted_script(self) -> None:
        payload = '</script><img src=x onerror=alert(1)> __ANSWER__'
        trace = Trace(3, payload)
        trace.add("user", payload, text=payload)
        trace.add("tool_call", payload, 1, name=payload, call_id=payload, arguments=json.dumps({payload: False}))
        trace.add("tool_result", payload, 1, name=payload, call_id=payload, output={"encrypted_content": "opaque-state", payload: [None, {}, []]})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.html"
            write_trace(path, trace)
            document = path.read_text(encoding="utf-8")
        self.assertEqual(document.count("<script>"), 1)
        self.assertEqual(document.count("</script>"), 1)
        self.assertNotIn("<img", document)
        self.assertNotIn("opaque-state", document)
        self.assertIn("&lt;img", document)
        self.assertIn("__ANSWER__", document)
        self.assertIn('href="#event-2"', document)
        self.assertIn('href="#event-1"', document)
        self.assertIn("boolean", document)
        script = document.split("<script>")[1].split("</script>")[0]
        digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
        self.assertIn(f"script-src 'sha256-{digest}'", document)
        self.assertNotIn("https://", document)
        self.assertNotIn("fetch(", script)
        self.assertNotIn("innerHTML", script)

    def test_missing_usage_is_not_zero_and_partial_usage_is_labelled(self) -> None:
        trace = Trace(2)
        trace.add("response", "返回", response={"usage": {"input_tokens": 30, "output_tokens": 5}})
        trace.add("response", "返回", response={"usage": None})
        self.assertEqual(usage_total(trace, "input_tokens"), "30（仅 1/2 个返回已报告）")
        self.assertEqual(usage_total(trace, "output_tokens"), "5（仅 1/2 个返回已报告）")
        self.assertEqual(usage_total(trace, "missing"), "未报告")

    def test_cli_failure_still_writes_dashboard(self) -> None:
        for module in (demo2, demo3):
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "failed.html"
                with mock.patch("sys.argv", [module.__name__, "--output", str(path)]), mock.patch.object(
                    module, "create_client", side_effect=ValueError("缺少配置")
                ), redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
                    module.main()
                self.assertIn("缺少配置", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
