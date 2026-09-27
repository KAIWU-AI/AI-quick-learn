from __future__ import annotations

import copy
import importlib
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from openai.types.responses import Response

import demo_support
from demo1.report import write_report

demo1 = importlib.import_module("demo1.__main__")
demo2 = importlib.import_module("demo2.__main__")
demo3 = importlib.import_module("demo3.__main__")


def response(text: str = "", calls: list[tuple[str, str, str]] | None = None, **changes) -> Response:
    output = [{"type": "reasoning", "id": "rs_test", "summary": [], "encrypted_content": "opaque-state"}]
    output.extend(
        {"type": "function_call", "id": f"fc_{call_id}", "call_id": call_id, "name": name, "arguments": args}
        for call_id, name, args in calls or []
    )
    if text:
        output.append({
            "type": "message", "id": "msg_test", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}],
        })
    return Response.model_validate({
        "id": "resp_test", "created_at": 1, "object": "response", "model": "test-model",
        "status": "completed", "output": output, "parallel_tool_calls": True,
        "tool_choice": "auto", "tools": [], "error": None, "incomplete_details": None,
        **changes,
    })


def scripted_client(responses: list[Response]):
    client = mock.Mock()
    remaining = iter(responses)
    requests = []

    def create(**kwargs):
        requests.append(copy.deepcopy(kwargs))
        return next(remaining)

    client.responses.create.side_effect = create
    return client, requests


class DemoTests(unittest.TestCase):
    def test_demo1_one_request_and_full_response(self) -> None:
        client, requests = scripted_client([response("回答")])
        output = io.StringIO()
        with redirect_stdout(output):
            result = demo1.run(client, "test-model", "问题")
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["input"], "问题")
        self.assertFalse(requests[0]["store"])
        self.assertNotIn("tools", requests[0])
        self.assertEqual(result.output_text, "回答")
        self.assertIn("完整 API 返回", output.getvalue())
        self.assertNotIn("opaque-state", output.getvalue())
        self.assertEqual(result.output[0].encrypted_content, "opaque-state")

    def test_visual_report_escapes_untrusted_text_and_preserves_placeholders(self) -> None:
        prompt = '<script>alert("input")</script> __ANSWER__'
        answer = '<img src=x onerror=alert("output")>'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "中文 folder" / "result.html"
            write_report(path, "test-model", prompt, response(answer))
            document = path.read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;", document)
        self.assertIn("&lt;img", document)
        self.assertNotIn("<script>", document)
        self.assertNotIn("<img", document)
        self.assertIn("__ANSWER__", document)
        self.assertIn("展开完整 API 返回 JSON", document)
        self.assertIn("未提供", document)
        self.assertNotIn("https://", document)

    def test_conversation_preserves_history_without_tools(self) -> None:
        client, requests = scripted_client([response("已记住"), response("蓝鲸17")])
        with redirect_stdout(io.StringIO()):
            answers = demo2.run_conversation(client, "test-model", ["代号是蓝鲸17", "我的代号？"])
        self.assertEqual(answers, ["已记住", "蓝鲸17"])
        self.assertEqual(len(requests[0]["input"]), 1)
        self.assertEqual(requests[1]["input"][0]["content"], "代号是蓝鲸17")
        self.assertEqual(requests[1]["input"][-1]["content"], "我的代号？")
        self.assertTrue(any(item.get("encrypted_content") == "opaque-state" for item in requests[1]["input"]))
        for request in requests:
            self.assertNotIn("tools", request)
            self.assertNotIn("previous_response_id", request)
            self.assertFalse(request["store"])
            self.assertEqual(request["include"], ["reasoning.encrypted_content"])

    def test_incomplete_conversation_does_not_modify_memory(self) -> None:
        history = [{"role": "user", "content": "已存在"}]
        before = copy.deepcopy(history)
        client, _ = scripted_client([response(status="incomplete", incomplete_details={"reason": "max_output_tokens"})])
        with redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
            demo2.chat_turn(client, "test-model", history, "新问题")
        self.assertEqual(history, before)

    def test_interactive_reset_drops_context_but_not_budget(self) -> None:
        client, requests = scripted_client([response("第一轮"), response("我不知道之前的代号")])
        with mock.patch("builtins.input", side_effect=["代号蓝鲸17", "/reset", "我的代号？"]), redirect_stdout(io.StringIO()):
            demo2.interactive_chat(client, "test-model", 2)
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[1]["input"], [{"role": "user", "content": "我的代号？"}])

    def test_batch_calls_and_reasoning_are_returned_with_correct_call_ids(self) -> None:
        client, requests = scripted_client([
            response(calls=[("first", "get_course", '{"course_id":"api"}'), ("second", "get_course", '{"course_id":"tools"}')]),
            response(calls=[("total", "sum_minutes", '{"minutes":[20,40]}')]),
            response("总共60分钟"),
        ])
        with redirect_stdout(io.StringIO()):
            result = demo3.run_agent(client, "test-model", "求时长")
        self.assertEqual(result, "总共60分钟")
        second_input = requests[1]["input"]
        self.assertEqual(second_input[1]["type"], "reasoning")
        outputs = [item for item in second_input if item.get("type") == "function_call_output"]
        self.assertEqual([item["call_id"] for item in outputs], ["first", "second"])
        self.assertEqual(json.loads(outputs[0]["output"])["minutes"], 20)
        final_output = requests[2]["input"][-1]
        self.assertEqual(final_output["call_id"], "total")
        self.assertEqual(json.loads(final_output["output"])["total_minutes"], 60)

    def test_tool_errors_are_observable_and_can_be_corrected(self) -> None:
        client, requests = scripted_client([
            response(calls=[("bad", "get_course", '{"course_id":"unknown"}')]),
            response(calls=[("fixed", "get_course", '{"course_id":"api"}')]),
            response("修正完成"),
        ])
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(demo3.run_agent(client, "test-model", "测试"), "修正完成")
        self.assertIn("error", json.loads(requests[1]["input"][-1]["output"]))
        self.assertIn("error", output.getvalue())
        self.assertNotIn("opaque-state", output.getvalue())

    def test_invalid_tool_inputs_do_not_produce_success(self) -> None:
        cases = [
            ("unknown", "{}"), ("list_courses", '{"extra":1}'),
            ("get_course", "not json"), ("get_course", "[]"),
            ("get_course", '{"course_id":true}'), ("get_course", "{}"),
            ("sum_minutes", '{"minutes":[]}'), ("sum_minutes", '{"minutes":[true]}'),
            ("sum_minutes", '{"minutes":[1.5]}'), ("sum_minutes", '{"minutes":[-1]}'),
            ("sum_minutes", '{"minutes":[481]}'),
            ("sum_minutes", json.dumps({"minutes": [1] * 11})),
        ]
        for name, args in cases:
            with self.subTest(name=name, args=args):
                self.assertIn("error", json.loads(demo3.dispatch_tool(name, args)))
        self.assertEqual(json.loads(demo3.dispatch_tool("sum_minutes", '{"minutes":[20,30,40]}')), {"total_minutes": 90})

    def test_loop_exhaustion_and_empty_responses_fail(self) -> None:
        for value in [response(), response(status="incomplete")]:
            client, _ = scripted_client([value])
            with redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
                demo3.run_agent(client, "test-model", "test")
        client, requests = scripted_client([response(calls=[("one", "list_courses", "{}")])])
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "上限"):
            demo3.run_agent(client, "test-model", "test", max_steps=1)
        self.assertEqual(len(requests), 1)

    def test_tool_schemas_are_strict_and_have_no_optional_properties(self) -> None:
        self.assertEqual(len(demo3.TOOLS), 3)
        for tool in demo3.TOOLS:
            self.assertEqual(tool["type"], "function")
            self.assertTrue(tool["strict"])
            parameters = tool["parameters"]
            self.assertFalse(parameters["additionalProperties"])
            self.assertEqual(set(parameters["required"]), set(parameters["properties"]))


class ClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = mock.patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.dotenv = mock.patch.object(demo_support, "load_dotenv")
        self.dotenv.start()
        self.addCleanup(self.dotenv.stop)

    def test_api_key_configuration_is_explicit(self) -> None:
        os.environ.update(OPENAI_MODEL="test-model", OPENAI_API_KEY="test-placeholder")
        with mock.patch.object(demo_support, "OpenAI") as constructor:
            _, model = demo_support.create_client()
        self.assertEqual(model, "test-model")
        self.assertEqual(constructor.call_args.kwargs["api_key"], "test-placeholder")
        self.assertEqual(constructor.call_args.kwargs["max_retries"], 0)

    def test_azure_cli_passes_refreshable_provider_not_token(self) -> None:
        os.environ.update(
            OPENAI_MODEL="deployment", OPENAI_AUTH="azure-cli",
            OPENAI_BASE_URL="https://example.openai.azure.com/openai/v1/",
        )
        with mock.patch.object(demo_support, "AzureCliCredential"), mock.patch.object(
            demo_support, "get_bearer_token_provider"
        ) as provider, mock.patch.object(demo_support, "OpenAI") as constructor:
            demo_support.create_client()
        self.assertIs(constructor.call_args.kwargs["api_key"], provider.return_value)
        self.assertEqual(provider.call_args.args[1], "https://ai.azure.com/.default")
        provider.return_value.assert_not_called()

    def test_rejects_bad_configuration_before_sending_credentials(self) -> None:
        with self.assertRaises(ValueError):
            demo_support.create_client()
        os.environ.update(OPENAI_MODEL="test-model", OPENAI_AUTH="azure-cli")
        for url in (
            "http://example.openai.azure.com/openai/v1/",
            "https://example.openai.azure.com.evil.example/openai/v1/",
            "https://example.openai.azure.com/not-v1/",
            "https://user:pass@example.openai.azure.com/openai/v1/",
        ):
            with self.subTest(url=url), mock.patch.object(demo_support, "OpenAI") as constructor:
                os.environ["OPENAI_BASE_URL"] = url
                with self.assertRaises(ValueError):
                    demo_support.create_client()
                constructor.assert_not_called()

    def test_dotenv_does_not_override_environment(self) -> None:
        from dotenv import load_dotenv
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "OPENAI_MODEL=file-model\nOPENAI_API_KEY=test-placeholder\n", encoding="utf-8"
            )
            os.environ["OPENAI_MODEL"] = "process-model"
            with mock.patch.object(demo_support, "__file__", str(root / "demo_support.py")), mock.patch.object(
                demo_support, "load_dotenv", wraps=load_dotenv
            ), mock.patch.object(demo_support, "OpenAI"):
                _, model = demo_support.create_client()
        self.assertEqual(model, "process-model")

    def test_cli_errors_are_nonzero(self) -> None:
        with mock.patch.object(demo_support, "configure_console"), redirect_stderr(io.StringIO()) as errors:
            with self.assertRaises(SystemExit) as context:
                demo_support.run_cli(mock.Mock(side_effect=ValueError("missing configuration")))
        self.assertEqual(context.exception.code, 1)
        self.assertIn("missing configuration", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
