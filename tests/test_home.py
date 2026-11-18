"""Test the serving-to-scorecard boundary without Docker or a GPU."""
import io
import json
import unittest
from unittest.mock import patch

from bench.home import answer_text, grade, request_task
from bench.home_report import summarize_scenario, timely


def sse(*packets):
    return io.BytesIO(
        b"".join(b"data: " + json.dumps(packet).encode() + b"\n\n" for packet in packets)
        + b"data: [DONE]\n\n"
    )


class HomeLabTest(unittest.TestCase):
    def test_types_and_duplicate_keys(self):
        self.assertEqual(grade('{"n": true}', {"n": 1}, "stop"), "wrong_value")
        self.assertEqual(grade('{"n": 0, "n": 1}', {"n": 1}, "stop"), "invalid_json")
        self.assertEqual(grade('{"n": 1}', {"n": 1}, "length"), "truncated")

    def test_visible_answer_ignores_raw_think_tags(self):
        self.assertEqual(answer_text([(8, "<think>text</thi"), (9, "nk> "), (10, "{}")]),
                         ("{}", 10))
        self.assertEqual(answer_text([(8, "<think>only")]), ("", None))

    def test_stream_reasoning_and_fenced_recovery(self):
        stream = sse(
            {"choices": [{"delta": {"reasoning_content": "hidden"}}]},
            {"choices": [{"delta": {"content": "\x60\x60\x60json\n{\"name\":\"ROWAN\"}\n\x60\x60\x60"}}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"completion_tokens": 12}},
        )
        with patch("bench.home.HTTP.open", return_value=stream):
            row = request_task("http://127.0.0.1:8000", "model",
                               {"prompt": "demo", "expected": {"name": "ROWAN"},
                                "sensitive": ["rowan"]},
                               {"max_output_tokens": 64, "request_timeout_s": 1})
        self.assertEqual(row["status"], "invalid_json")
        self.assertEqual(row["fence_correct"], 1)
        self.assertEqual(row["redaction_leak"], 1)
        self.assertEqual(row["output_tokens"], 12)
        self.assertLessEqual(row["first_token_ms"], row["first_answer_ms"])

    def test_goodput_counts_only_correct_replies_within_both_limits(self):
        budget = {"first_answer_ms": 500, "complete_ms": 5000}
        base = {"kind": "extract", "language": "en", "status": "correct", "redaction_leak": "",
                "first_token_ms": 90, "first_answer_ms": 100, "complete_ms": 1000,
                "output_tokens": 10}
        rows = [base, dict(base, complete_ms=7000), dict(base, first_answer_ms=None),
                dict(base, status="wrong_value")]
        self.assertFalse(timely(rows[2], budget))
        result = summarize_scenario(rows, budget, seconds=12)
        self.assertEqual((result["n"], result["correct"], result["timely"]), (4, 3, 1))
        self.assertEqual(result["goodput_per_min"], 5)
        self.assertEqual(result["failures"], {"wrong_value": 1})


if __name__ == "__main__":
    unittest.main()
