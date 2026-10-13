# -*- coding: utf-8 -*-
"""Тесты выгрузки SolveHub: сохраняются ВСЕ пункты задачи, а не только problems[0].

Баг 13.10.2026: SolveHub отдаёт в списке problems сразу и задачу, и её пункты
(б, в, г…), а скрипты сохраняли problems[0]. Сети в тестах нет: ответы подставные.

Запуск:
    venv313/Scripts/python.exe -m unittest scripts.tests.test_solvehub_fetch -v
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SOLVEHUB_DIR = Path(__file__).resolve().parent.parent / "solvehub"


def load_module(name):
    """Скрипты solvehub/ — не пакет, грузим по пути; каждый раз заново (чистые счётчики)."""
    spec = importlib.util.spec_from_file_location(f"_t_{name}", SOLVEHUB_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_part(hash_, parent, md, **extra):
    row = {"id": 1, "hash": hash_, "parent_hash": parent, "title": "Задача", "md": md,
           "answer_md": None, "check_type": "uncheckable", "check_options": None,
           "correct_answer": None}
    row.update(extra)
    return row


THREE = [
    make_part("h1", None, "Условие. а) $C=0$", correct_answer="40"),
    make_part("h2", "h1", "б) $C=400$", correct_answer="20"),
    make_part("h3", "h2", "в) $C=1225$", check_type="number"),
]


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def trpc_payload(problems):
    return [{"result": {"data": {"json": {"problems": problems, "rounds": [], "accessible": True}}}}]


class FetchProblemTests(unittest.TestCase):
    def setUp(self):
        self.fp = load_module("fetch_problems")

    def fetch(self, problems, hash_="h1"):
        with mock.patch.object(self.fp.requests, "get",
                               return_value=FakeResponse(200, trpc_payload(problems))):
            return self.fp.fetch_problem(hash_)

    def test_three_records_give_three_parts(self):
        record = self.fetch(THREE)
        self.assertEqual(record["_parts_count"], 3)
        self.assertEqual([p["hash"] for p in record["_parts"]], ["h1", "h2", "h3"])
        self.assertEqual(record["_parts"][2]["md"], "в) $C=1225$")
        self.assertEqual(record["_parts"][2]["check_type"], "number")

    def test_old_fields_are_the_first_record(self):
        record = self.fetch(THREE)
        for key, value in THREE[0].items():
            self.assertEqual(record[key], value, key)
        self.assertEqual(record["_parts"][0], THREE[0])  # в _parts[0] повторяется сама задача

    def test_record_is_json_serializable(self):
        # _parts[0] — копия, а не ссылка на сам record: иначе цикл и падение json.dump
        record = self.fetch(THREE)
        self.assertEqual(json.loads(json.dumps(record))["_parts_count"], 3)

    def test_single_record_gives_one_part(self):
        record = self.fetch(THREE[:1])
        self.assertEqual(record["_parts_count"], 1)
        self.assertEqual(len(record["_parts"]), 1)

    def test_empty_list_is_clear_error(self):
        with self.assertRaisesRegex(RuntimeError, "пустой ответ"):
            self.fetch([])

    def test_429_waits_a_minute_and_retries_same_hash(self):
        responses = [FakeResponse(429), FakeResponse(200, trpc_payload(THREE))]
        with mock.patch.object(self.fp.requests, "get", side_effect=responses), \
                mock.patch.object(self.fp.time, "sleep") as sleep:
            record = self.fp.fetch_problem("h1")
        self.assertEqual(record["_parts_count"], 3)
        sleep.assert_any_call(60)

    def test_three_blocks_in_a_row_stop_the_run(self):
        with mock.patch.object(self.fp.requests, "get", return_value=FakeResponse(503)) as get, \
                mock.patch.object(self.fp.time, "sleep"):
            with self.assertRaises(self.fp.ServerBlocked):
                self.fp.fetch_problem("h1")
        self.assertEqual(get.call_count, 3)

    def test_request_budget_is_enforced(self):
        self.fp._request_limit = 1
        responses = [FakeResponse(503), FakeResponse(200, trpc_payload(THREE))]
        with mock.patch.object(self.fp.requests, "get", side_effect=responses) as get, \
                mock.patch.object(self.fp.time, "sleep"):
            with self.assertRaises(self.fp.RequestBudgetExceeded):
                self.fp.fetch_problem("h1")
        self.assertEqual(get.call_count, 1)


class MainTests(unittest.TestCase):
    """main() с --out-dir/--hashes-file/--resume на подставных ответах."""

    def setUp(self):
        self.fp = load_module("fetch_problems")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.out = root / "v2" / "problems"
        self.hashes = root / "hashes.json"
        self.hashes.write_text(json.dumps({"hashes": ["h1", "h9"]}), encoding="utf-8")

    def run_main(self, *extra, responses=None):
        argv = ["--out-dir", str(self.out), "--hashes-file", str(self.hashes), *extra]
        if responses is None:
            responses = lambda *a, **k: FakeResponse(200, trpc_payload(THREE))  # noqa: E731
        with mock.patch.object(self.fp.requests, "get", side_effect=responses), \
                mock.patch.object(self.fp.time, "sleep"):
            self.fp.main(argv)

    def test_file_has_parts_and_journal_row(self):
        self.run_main()
        saved = json.loads((self.out / "h1.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["_parts_count"], 3)
        self.assertEqual(len(saved["_parts"]), 3)
        journal = [json.loads(x) for x in
                   (self.out.parent / "journal.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(j["hash"], j["status"], j["parts"]) for j in journal],
                         [("h1", "ok", 3), ("h9", "ok", 3)])

    def test_resume_skips_files_with_parts_but_refetches_old_format(self):
        self.out.mkdir(parents=True)
        (self.out / "h1.json").write_text(json.dumps({"hash": "h1", "_parts": [{}]}), encoding="utf-8")
        (self.out / "h9.json").write_text(json.dumps({"hash": "h9"}), encoding="utf-8")  # старый формат
        calls = []

        def responses(*a, **k):
            calls.append(k["params"]["input"])
            return FakeResponse(200, trpc_payload(THREE))

        self.run_main("--resume", responses=responses)
        self.assertEqual(len(calls), 1)
        self.assertIn("h9", calls[0])
        self.assertEqual(json.loads((self.out / "h9.json").read_text(encoding="utf-8"))["_parts_count"], 3)

    def test_block_stops_run_and_prints_resume_command(self):
        with mock.patch("builtins.print") as printed:
            self.run_main(responses=lambda *a, **k: FakeResponse(429))
        self.assertFalse((self.out / "h1.json").exists())
        text = "\n".join(str(c.args[0]) for c in printed.call_args_list if c.args)
        self.assertIn("--resume", text)
        self.assertIn(str(self.out), text)
        journal = (self.out.parent / "journal.jsonl").read_text(encoding="utf-8")
        self.assertIn('"stopped"', journal)


class RscReserveTests(unittest.TestCase):
    def setUp(self):
        self.rsc = load_module("rsc_reserve")

    def stream(self, problems, text_chunk=None):
        # Настоящий RSC-поток компактный (без пробелов после «:»), на этом держится поиск маркера.
        head = json.dumps({"initialData": {"problems": problems}}, ensure_ascii=False,
                          separators=(",", ":"))
        out = f"0:{head}\n"
        if text_chunk is not None:
            out += f"1:T{len(text_chunk.encode('utf-8')):x},{text_chunk}"
        return out

    def fetch(self, stream):
        with mock.patch.object(self.rsc, "fetch_raw", return_value=("u", 200, stream)):
            return self.rsc.fetch_problem_via_rsc("h1")

    def test_three_records_give_three_parts(self):
        record = self.fetch(self.stream(THREE))
        self.assertEqual(record["_parts_count"], 3)
        self.assertEqual([p["hash"] for p in record["_parts"]], ["h1", "h2", "h3"])
        self.assertEqual(record["hash"], "h1")

    def test_refs_are_resolved_in_every_part(self):
        parts = [make_part("h1", None, "$1"), make_part("h2", "h1", "б) $1")]
        record = self.fetch(self.stream(parts, text_chunk="а)\nтекст"))
        self.assertEqual(record["md"], "а)\nтекст")
        self.assertEqual(record["_parts"][0]["md"], "а)\nтекст")
        self.assertEqual(record["_parts"][1]["md"], "б) $1")  # не ссылка, остаётся как есть

    def test_single_record(self):
        record = self.fetch(self.stream(THREE[:1]))
        self.assertEqual(record["_parts_count"], 1)

    def test_empty_list_is_clear_error(self):
        with self.assertRaisesRegex(RuntimeError, "не нашёл"):
            self.fetch(self.stream([]))


if __name__ == "__main__":
    unittest.main()
