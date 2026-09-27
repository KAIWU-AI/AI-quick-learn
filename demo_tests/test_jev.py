from __future__ import annotations

import copy
import importlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from demo1 import credentials, jev
from demo1.report import CallResult, write_dashboard


def jev_response() -> dict:
    return {
        "model": "jev-test",
        "answers": {"category": {
            "type": "choice", "choice": "billing", "confidence": 0.9,
            "probabilities": {"billing": 0.9, "technical": 0.05, "other": 0.05},
        }},
        "usage": {"input_tokens": 10, "output_tokens": 4},
    }


class JevTests(unittest.TestCase):
    def test_payload_contains_state_and_typed_question(self) -> None:
        payload = jev.make_request("工单", "jev-test")
        self.assertEqual(payload["state"], {"document": "工单"})
        self.assertEqual(payload["questions"]["category"]["type"], "choice")
        self.assertEqual(set(payload["questions"]["category"]["criteria"]), {"billing", "technical", "other"})
        self.assertNotIn("Authorization", payload)

    def test_http_call_is_post_and_key_is_not_in_body_or_result(self) -> None:
        raw = jev_response()
        raw["echo"] = "test-placeholder"
        with mock.patch.object(jev, "get_api_key", return_value="test-placeholder"), mock.patch.object(
            jev.urllib.request, "build_opener"
        ) as factory:
            factory.return_value.open.return_value.__enter__.return_value.read.return_value = json.dumps(raw).encode()
            result = jev.request_jev(jev.make_request("退款", "jev-test"))
        request = factory.return_value.open.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.full_url, jev.API_URL)
        self.assertEqual(request.get_header("Authorization"), "Bearer test-placeholder")
        self.assertNotIn(b"test-placeholder", request.data)
        self.assertNotIn("test-placeholder", json.dumps(result))
        self.assertIsInstance(factory.call_args.args[0], jev.NoRedirect)
        self.assertIsNone(jev.NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.invalid"))

    def test_invalid_responses_are_errors_not_empty_success(self) -> None:
        cases = []
        for field, value in (
            ("choice", []), ("confidence", True), ("confidence", float("nan")),
            ("confidence", -1), ("probabilities", {"billing": 1}),
        ):
            raw = jev_response()
            raw["answers"]["category"][field] = value
            cases.append(json.dumps(raw).encode())
        cases.extend([b"not json", b"[]", b"x" * 1_000_001])
        with mock.patch.object(jev, "get_api_key", return_value="test-placeholder"), mock.patch.object(
            jev.urllib.request, "build_opener"
        ) as factory:
            for body in cases:
                with self.subTest(body_length=len(body)):
                    factory.return_value.open.return_value.__enter__.return_value.read.return_value = body
                    with self.assertRaises(RuntimeError):
                        jev.request_jev(jev.make_request("工单", "jev-test"))

    def test_http_error_is_sanitized(self) -> None:
        error = urllib.error.HTTPError(jev.API_URL, 401, "private detail", {}, io.BytesIO(b"secret"))
        with mock.patch.object(jev, "get_api_key", return_value="test-placeholder"), mock.patch.object(
            jev.urllib.request, "build_opener"
        ) as factory:
            factory.return_value.open.side_effect = error
            with self.assertRaisesRegex(RuntimeError, "HTTP 401") as caught:
                jev.request_jev(jev.make_request("工单", "jev-test"))
        self.assertNotIn("private detail", str(caught.exception))
        self.assertNotIn("secret", str(caught.exception))

    def test_auth_modes_are_explicit_and_portable(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                jev.get_api_key()
            os.environ.update(JEV_AUTH="api-key", JEV_API_KEY="test-placeholder")
            self.assertEqual(jev.get_api_key(), "test-placeholder")
            os.environ["JEV_AUTH"] = "windows-credential"
            with mock.patch.object(jev, "read_windows_credential", return_value="stored-placeholder") as read:
                self.assertEqual(jev.get_api_key(), "stored-placeholder")
                read.assert_called_once_with("TypeSafe/Jev/APIKey")
        with mock.patch.object(credentials.os, "name", "posix"), self.assertRaisesRegex(RuntimeError, "Windows"):
            credentials.read_windows_credential("ignored")

    def test_demo1_calls_both_apis_and_renders_partial_failure(self) -> None:
        demo1 = importlib.import_module("demo1.__main__")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.html"
            with mock.patch("sys.argv", ["demo1", "工单", "--output", str(output)]), mock.patch.object(
                demo1, "load_dotenv"
            ), mock.patch.object(demo1, "call_llm", side_effect=RuntimeError("LLM unavailable")) as llm, mock.patch.object(
                demo1, "call_jev", return_value=(jev_response(), "billing")
            ) as call_jev, redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, "部分接口"):
                    demo1.main()
            llm.assert_called_once_with("工单")
            call_jev.assert_called_once()
            page = output.read_text(encoding="utf-8")
            self.assertIn("LLM unavailable", page)
            self.assertIn("billing", page)
            self.assertIn("JEV", page)

    def test_collection_does_not_mutate_request_or_invent_response(self) -> None:
        demo1 = importlib.import_module("demo1.__main__")
        payload = jev.make_request("工单", "jev-test")
        original = copy.deepcopy(payload)
        with redirect_stdout(io.StringIO()):
            result = demo1.collect_result("JEV", "TypeSafe systemone", payload, mock.Mock(side_effect=RuntimeError("failed")))
        self.assertEqual(payload, original)
        self.assertIsNone(result.response)
        self.assertEqual(result.error, "failed")
        self.assertGreaterEqual(result.elapsed_ms, 0)

    def test_tree_preserves_json_types_but_masks_opaque_state(self) -> None:
        data = {
            "object": {"array": [None, False, 3, "<script>not executable</script>"]},
            "empty_object": {}, "empty_array": [], "encrypted_content": "PRIVATE_OPAQUE_VALUE",
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.html"
            write_dashboard(output, "工单", [
                CallResult("OpenAI", "Responses API", {"input": "工单"}, response=data),
                CallResult("JEV", "TypeSafe systemone", {}, response=jev_response()),
            ])
            page = output.read_text(encoding="utf-8")
        self.assertGreaterEqual(page.count('<details class="branch"'), 10)
        for text in ("boolean", "null", "number", "array", "object", "空数组", "空对象"):
            self.assertIn(text, page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("PRIVATE_OPAQUE_VALUE", page)
        self.assertIn("集中程度，不是事实正确率", page)
        self.assertIn("90%", page)
        self.assertIn("choice → billing", page)


if __name__ == "__main__":
    unittest.main()
