"""Controlled interventions use real Core/Provider code with a fake model transport."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from Benchmarks.agent_story.providers import SYSTEM, SEARCH_TOOL
from Benchmarks.support.common import encoded, read_rows

ROOT = Path(__file__).resolve().parents[3]
CONFIG = {"base_url": "http://127.0.0.1:1/v1", "model": "test-model",
          "temperature": 0, "seed": 42, "max_tokens": 1536, "timeout": 180}
CORPUS = [{"id": "chunk-one", "title": "人物故事", "text": "温迪：她是女士。",
           "source_file": "parsed/test.json", "source_pointer": ["/dialog/0/text"],
           "source_spans": [{"start": 0, "end": 6}], "source_kind": "wiki_excerpt"}]


def raw(message=None, finish="stop"):
    return {"choices": [{"message": message or {"role": "assistant", "content": "回答"},
                         "finish_reason": finish}], "model": "test-model"}


def tool_call():
    return {"role": "assistant", "content": None, "tool_calls": [{"id": "native-one",
            "type": "function", "function": {"name": "search_story",
            "arguments": '{"query":"人物故事"}'}}]}


class ControlsTests(unittest.TestCase):
    def test_prefill_force_is_captured_and_never_enters_followup_history(self):
        from probes.a06_diagnosis.controls import ObservedClient
        events = []
        replies = [raw(tool_call(), "tool_calls"), raw(), raw()]
        client = ObservedClient({**CONFIG, "tool_choice_mode": "required_single_tool_prefill"},
                                events.append, lambda *args: replies.pop(0))
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "原问"}]
        original = deepcopy(messages)
        client.begin(1, force_first=True)
        client.chat(messages, [SEARCH_TOOL], 20)
        client.chat(messages, [SEARCH_TOOL], 20)
        client.begin(2)
        client.chat(messages, [SEARCH_TOOL], 20)
        payloads = [e["payload"] for e in events if e["event"] == "request"]
        self.assertEqual(payloads[0]["messages"], original + [{"role": "assistant", "content": "<tool_call>\n"}])
        self.assertEqual(payloads[0]["tool_choice"], "required")
        self.assertEqual(payloads[0]["continue_final_message"], "content")
        self.assertIs(payloads[0]["add_generation_prompt"], False)
        self.assertEqual(payloads[0]["max_tokens"], 1536)
        self.assertEqual(messages, original)
        for payload in payloads[1:]:
            self.assertEqual(payload["messages"], original)
            self.assertNotIn("tool_choice", payload)
            self.assertNotIn("continue_final_message", payload)
            self.assertNotIn("add_generation_prompt", payload)

    def test_compatibility_force_records_required_and_restores_auto(self):
        from probes.a06_diagnosis.controls import ObservedClient
        sent, events = [], []
        def transport(endpoint, payload, timeout):
            sent.append(deepcopy(payload))
            return raw(tool_call(), "tool_calls") if len(sent) == 1 else raw()
        client = ObservedClient({**CONFIG, "tool_choice_mode": "required_single_tool"}, events.append, transport)
        client.begin(1, force_first=True)
        client.chat([{"role": "user", "content": "原问"}], [SEARCH_TOOL], 20)
        client.chat([{"role": "user", "content": "原问"}], [SEARCH_TOOL], 20)
        self.assertEqual(sent[0]["tool_choice"], "required")
        self.assertNotIn("tool_choice", sent[1])
        self.assertEqual(sent[0]["tools"], [SEARCH_TOOL])
        self.assertEqual(sent[0]["messages"], sent[1]["messages"])
        self.assertEqual(client.force_status, "succeeded")

    def client(self, responses):
        from probes.a06_diagnosis.controls import ObservedClient
        self.events, self.sent = [], []
        def transport(endpoint, payload, timeout):
            self.sent.append(deepcopy(payload))
            result = responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        return ObservedClient(CONFIG, self.events.append, transport=transport)

    def test_forces_only_first_request_and_keeps_original_payload(self):
        client = self.client([raw(tool_call(), "tool_calls"), raw(), raw()])
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "原问"}]
        client.begin(1, force_first=True)
        client.chat(messages, [SEARCH_TOOL], 20)
        client.chat(messages, [SEARCH_TOOL], 20)
        client.begin(2)
        client.chat(messages, [SEARCH_TOOL], 20)
        self.assertEqual(self.sent[0]["tool_choice"], {"type": "function", "function": {"name": "search_story"}})
        self.assertTrue(all("tool_choice" not in p for p in self.sent[1:]))
        ordinary = deepcopy(self.sent[0]); ordinary.pop("tool_choice")
        self.assertEqual(ordinary, self.sent[1])
        self.assertEqual(ordinary["messages"], messages)
        self.assertEqual(ordinary["chat_template_kwargs"], {"enable_thinking": False})
        self.assertNotIn("top_k", ordinary)

    def test_preflight_does_not_consume_scenario_force(self):
        client = self.client([raw(tool_call(), "tool_calls"), raw(tool_call(), "tool_calls")])
        client.begin(1, force_first=True)
        client.preflight()
        client.chat([{"role": "user", "content": "原问"}], [SEARCH_TOOL], 20)
        self.assertTrue(all("tool_choice" in p for p in self.sent))
        requests = [e for e in self.events if e["event"] == "request"]
        self.assertEqual([(e["turn"], e["request"]) for e in requests], [(0, 1), (1, 1)])

    def test_ignored_choice_and_truncation_are_not_success(self):
        from probes.a06_diagnosis.controls import ToolChoiceUnsupported
        for reply in (raw(), raw(tool_call(), "length")):
            with self.subTest(reply=reply):
                client = self.client([reply]); client.begin(1, force_first=True)
                with self.assertRaises(ToolChoiceUnsupported):
                    client.chat([], [SEARCH_TOOL], 20)
                self.assertEqual(client.force_status, "unsupported_or_ignored")
                self.assertEqual(self.events[-1]["raw_response"], reply)

    def test_transport_exception_keeps_attempt_without_secrets(self):
        client = self.client([ValueError("Authorization: secret")])
        client.begin(1)
        with self.assertRaises(ValueError):
            client.chat([], [SEARCH_TOOL], 20)
        self.assertEqual(self.events[-1]["exception_type"], "ValueError")
        self.assertNotIn("secret", json.dumps(self.events))

    def test_request_and_response_records_are_copies(self):
        message = {"role": "assistant", "content": "原文"}
        client = self.client([raw(message)])
        messages = [{"role": "user", "content": "问题"}]
        client.begin(1); result = client.chat(messages, [SEARCH_TOOL], 20)
        messages[0]["content"] = "修改"; result["raw_response"]["choices"][0]["message"]["content"] = "修改"
        self.assertEqual(self.events[0]["payload"]["messages"][0]["content"], "问题")
        self.assertEqual(self.events[1]["raw_response"]["choices"][0]["message"]["content"], "原文")

    def test_server_warning_overrides_apparent_tool_call_success(self):
        from probes.a06_diagnosis.controls import ToolChoiceUnsupported
        client = self.client([raw(tool_call(), "tool_calls")])
        client.choice_guard = lambda: False
        client.begin(1, force_first=True)
        with self.assertRaises(ToolChoiceUnsupported):
            client.chat([], [SEARCH_TOOL], 20)
        self.assertEqual(client.force_status, "unsupported_or_ignored")


class EvidenceTests(unittest.TestCase):
    def test_source_speaker_resolves_text_sibling_not_parent_object(self):
        from probes.a06_diagnosis.evidence import source_anchors
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory); (path / "parsed").mkdir()
            (path / "parsed/test.json").write_text(json.dumps({"对话": [{"说话者": "温迪", "内容": "她是女士。"}]}), encoding="utf-8")
            scene = {"reference_material": [{"sources": [{"file": "parsed/test.json", "pointer": "/对话/0/内容"}]}]}
            self.assertEqual(source_anchors(scene, path)[0]["speaker"], "温迪")

    def test_missing_mapping_preserves_denominator_and_full_spans(self):
        from probes.a06_diagnosis.evidence import map_anchors, coverage
        anchors = [{"source_file": "parsed/test.json", "source_pointer": "/dialog/0/text", "start": 0, "end": 6},
                   {"source_file": "parsed/test.json", "source_pointer": "/missing", "start": 0, "end": 1}]
        mapped = map_anchors(anchors, CORPUS)
        result = coverage(mapped, CORPUS)
        self.assertEqual(result["covered_groups"], 1)
        self.assertEqual(result["total_groups"], 2)
        self.assertEqual(result["recall"], .5)
        self.assertEqual(result["unmapped_groups"], 1)
        short = deepcopy(CORPUS); short[0]["source_spans"][0]["end"] = 5
        self.assertFalse(map_anchors(anchors[:1], short)[0]["ids"])

    def test_transfer_audit_checks_text_not_just_id(self):
        from probes.a06_diagnosis.evidence import audit_transfers
        wrapper = {"ok": True, "result": {"evidence": CORPUS}}
        trace = [{"direction": "receive", "message": {"type": "provider_call", "request_id": "p2",
                  "provider": "tool", "payload": {"call_id": "native-one"}}},
                 {"direction": "send", "message": {"type": "provider_result", "request_id": "p2", **wrapper}}]
        message = {"role": "tool", "tool_call_id": "native-one", "content": encoded(wrapper)}
        records = [{"event": "request", "turn": 1, "request": 2, "payload": {"messages": [message]}}]
        self.assertTrue(audit_transfers(trace, records)[0]["exact_match"])
        changed = deepcopy(records)
        altered = deepcopy(wrapper); altered["result"]["evidence"][0]["text"] = "同 ID 不同内容"
        changed[0]["payload"]["messages"][0]["content"] = encoded(altered)
        self.assertFalse(audit_transfers(trace, changed)[0]["exact_match"])
        self.assertFalse(audit_transfers(trace, [])[0]["delivered"])

    def test_injected_history_is_audited_without_real_tool_calls(self):
        from probes.a06_diagnosis.evidence import audit_injected_history
        fixture = {"messages": [{"role": "system", "content": SYSTEM}, tool_call(),
                   {"role": "tool", "tool_call_id": "native-one", "content": encoded({"ok": True, "result": {"evidence": CORPUS}})},
                   {"role": "assistant", "content": "正确首答"}]}
        records = [{"event": "request", "turn": 2, "request": 1, "endpoint": "chat/completions",
                    "payload": {"messages": fixture["messages"] + [{"role": "user", "content": "她呢"}]}}]
        self.assertTrue(audit_injected_history(fixture, records)["exact_match"])
        changed = deepcopy(records); changed[0]["payload"]["messages"][2]["content"] = '{"ok":true,"result":{"evidence":[]}}'
        self.assertFalse(audit_injected_history(fixture, changed)["exact_match"])
        self.assertFalse(audit_injected_history(fixture, [])["delivered"])


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)

    def test_real_worker_forced_retrieval_and_three_turn_history(self):
        from probes.a06_diagnosis.runner import run_live
        sent = []
        def transport(endpoint, payload, timeout):
            sent.append(deepcopy(payload))
            return raw(tool_call(), "tool_calls") if len(sent) == 1 else raw()
        scene = {"id": "a06", "turns": [{"content": "第一问"}, {"content": "她呢"}, {"content": "谁说的"}],
                 "reference_material": []}
        run_live(self.path / "A", scene, CORPUS, CONFIG, "A", transport=transport)
        row = read_rows(self.path / "A/results.jsonl")[0]
        self.assertEqual(row["execution_status"], "completed")
        self.assertEqual(row["model_calls"], 4)
        self.assertEqual(row["tool_calls"], 1)
        self.assertEqual([x["model_requests"] for x in row["turns"]], [2, 1, 1])
        self.assertEqual(row["violations"], [])
        self.assertTrue(all(x["exact_match"] for x in row["transfers"]))
        self.assertEqual([m["role"] for m in sent[2]["messages"]],
                         ["system", "user", "assistant", "tool", "assistant", "user"])
        self.assertNotIn("tool_choice", sent[1])
        with self.assertRaises(FileExistsError):
            run_live(self.path / "A", scene, CORPUS, CONFIG, "A", transport=transport)

    def test_c2_seed_survives_reset_then_uses_original_core_loop(self):
        from probes.a06_diagnosis.runner import run_live
        wrapper = {"ok": True, "result": {"evidence": CORPUS}}
        history = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "第一问"},
                   tool_call(), {"role": "tool", "tool_call_id": "native-one", "content": encoded(wrapper)},
                   {"role": "assistant", "content": "女士。[chunk-one]"}]
        fixture = {"messages": history, "selection": "direct_corpus_selection", "synthetic_history": True}
        sent = []
        def transport(endpoint, payload, timeout):
            sent.append(deepcopy(payload)); return raw()
        scene = {"id": "a06", "turns": [{"content": "第一问"}, {"content": "她呢"}, {"content": "谁说的"}],
                 "reference_material": []}
        run_live(self.path / "C2", scene, CORPUS, CONFIG, "C2", fixture=fixture, transport=transport)
        row = read_rows(self.path / "C2/results.jsonl")[0]
        self.assertEqual(row["execution_status"], "completed")
        self.assertEqual(row["model_calls"], 2)
        self.assertEqual(row["violations"], [])
        self.assertEqual([t["turn"] for t in row["turns"]], [2, 3])
        self.assertEqual(sent[0]["messages"][:-1], history)
        self.assertEqual(len(sent[1]["messages"]), len(history) + 3)
        self.assertTrue(all("tool_choice" not in p for p in sent))

    def test_unsupported_choice_stops_without_fabricated_tool(self):
        from probes.a06_diagnosis.runner import run_live
        scene = {"id": "a06", "turns": [{"content": "原问"}, {"content": "后问"}, {"content": "末问"}], "reference_material": []}
        run_live(self.path / "A", scene, CORPUS, CONFIG, "A", transport=lambda *args: raw())
        row = read_rows(self.path / "A/results.jsonl")[0]
        self.assertEqual(row["force_status"], "unsupported_or_ignored")
        self.assertNotEqual(row["execution_status"], "completed")
        self.assertEqual(row["tool_calls"], 0)
        self.assertEqual(row["unexecuted_turns"], [2, 3])
        self.assertEqual(row["api_http_responses"], 1)
        self.assertEqual(row["api_completed_responses"], 1)
        self.assertEqual(row["model_http_responses"], 0)

    def test_real_forced_condition_rejects_missing_log_before_network(self):
        from probes.a06_diagnosis.runner import run_live
        scene = {"id": "a06", "turns": [], "reference_material": []}
        with self.assertRaisesRegex(ValueError, "service log"):
            run_live(self.path / "A", scene, CORPUS, CONFIG, "A")
        self.assertFalse((self.path / "A").exists())

    def test_verification_detects_changed_raw_artifact(self):
        from probes.a06_diagnosis.runner import run_live
        from probes.a06_diagnosis.stages import verify_hashes
        scene = {"id": "a06", "turns": [{"content": str(i)} for i in range(3)], "reference_material": []}
        stage = self.path / "O"
        run_live(stage, scene, CORPUS, CONFIG, "O", transport=lambda *args: raw())
        self.assertEqual(verify_hashes(stage), [])
        (stage / "api.jsonl").write_text("changed", encoding="utf-8")
        self.assertIn("api.jsonl", verify_hashes(stage))

    def test_fresh_report_does_not_claim_reuse_or_ignored_force(self):
        from probes.a06_diagnosis.runner import run_live
        from probes.a06_diagnosis.stages import report_run
        scene = {"id": "a06", "turns": [{"content": str(i)} for i in range(3)], "reference_material": []}
        run_live(self.path / "O-r001", scene, CORPUS, CONFIG, "O", transport=lambda *args: raw())
        report_run(self.path / "report", self.path)
        report = (self.path / "report/report.md").read_text(encoding="utf-8")
        self.assertNotIn("本次实际新请求为0", report)
        self.assertNotIn("服务忽略指定工具", report)
        self.assertIn("| O-r001 | completed | 3 | 3 |", report)


class GateTests(unittest.TestCase):
    def test_public_launch_config_line_endings_do_not_change_identity(self):
        from probes.a06_diagnosis.environment import public_config_matches
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "api.json"
            path.write_bytes(b'{\r\n  "seed": 42\r\n}\r\n')
            self.assertTrue(public_config_matches(path, b'{\n  "seed": 42\n}\n'))
            self.assertFalse(public_config_matches(path, b'{"seed":43}'))

    def test_diagnostic_config_allows_only_explicit_compatibility_delta(self):
        from probes.a06_diagnosis.environment import validate_diagnostic_config
        validate_diagnostic_config({**CONFIG, "tool_choice_mode": "required_single_tool"}, CONFIG)
        validate_diagnostic_config({**CONFIG, "tool_choice_mode": "required_single_tool_prefill"}, CONFIG)
        for change in ({"temperature": 0.7}, {"max_tokens": 3072}, {"enable_thinking": True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_diagnostic_config({**CONFIG, "tool_choice_mode": "required_single_tool", **change}, CONFIG)

    def test_verifier_rejects_missing_prefill_or_leaked_continuation(self):
        from probes.a06_diagnosis.runner import run_live
        from probes.a06_diagnosis.stages import verify_run
        scene = {"id": "a06", "turns": [{"content": str(i)} for i in range(3)], "reference_material": []}
        for alteration in ("none", "missing_prefill", "leaked_continuation"):
            with self.subTest(alteration=alteration), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                replies = [raw(tool_call(), "tool_calls"), raw(), raw(), raw()]
                run_live(root / "A", scene, CORPUS,
                         {**CONFIG, "tool_choice_mode": "required_single_tool_prefill"}, "A",
                         transport=lambda *args: replies.pop(0))
                if alteration != "none":
                    from Benchmarks.support.common import write_json, file_hash
                    path = root / "A/api.jsonl"
                    records = read_rows(path)
                    requests = [e for e in records if e["event"] == "request"]
                    if alteration == "missing_prefill":
                        requests[0]["payload"]["messages"].pop()
                    else:
                        requests[1]["payload"]["continue_final_message"] = "content"
                    path.write_text("".join(json.dumps(e) + "\n" for e in records), encoding="utf-8")
                    hashes = root / "A/hashes.json"
                    data = json.loads(hashes.read_text(encoding="utf-8"))
                    data["api.jsonl"] = file_hash(path)
                    write_json(hashes, data)
                _, passed = verify_run(root / "verification", root)
                self.assertEqual(passed, alteration == "none")

    def test_unverified_launch_cannot_run_even_if_service_ready(self):
        from unittest.mock import patch
        from probes.a06_diagnosis.environment import load_environment
        env = {"hashes": {}, "raw_root": ".", "deployment": {"ready": True, "launch_configuration_verified": False}}
        materials = {"a06": {"frozen_sources": []}}
        with patch("probes.a06_diagnosis.environment.read_json", side_effect=[env, materials]):
            with self.assertRaisesRegex(ValueError, "launch"):
                load_environment("unused", require_service=True)

    def test_changed_frozen_source_is_rejected(self):
        from probes.a06_diagnosis.environment import verify_raw_sources
        from Benchmarks.support.common import file_hash
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "parsed").mkdir()
            source = root / "parsed/test.json"; source.write_text("{}", encoding="utf-8")
            expected = {"parsed/test.json": file_hash(source)}
            self.assertEqual(verify_raw_sources(root, expected), expected)
            source.write_text('{"changed":true}', encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_raw_sources(root, expected)

    def test_reuse_requires_all_identities_including_launch_verification(self):
        from probes.a06_diagnosis.environment import compare_environment
        historical = {"config": CONFIG, "hashes": {"candidate": "abc", "corpus": "def"},
                      "deployment": {"model_sha256": "model", "server_sha256": "server"}}
        current = {**deepcopy(historical), "deployment": {**historical["deployment"], "ready": True,
                   "launch_configuration_verified": True}}
        self.assertTrue(compare_environment(current, historical)["reusable"])
        for mutate in (
            lambda x: x["config"].update(seed=43),
            lambda x: x["hashes"].update(candidate="changed"),
            lambda x: x["hashes"].update(corpus="changed"),
            lambda x: x["deployment"].update(model_sha256="changed"),
            lambda x: x["deployment"].update(launch_configuration_verified=False),
            lambda x: x["deployment"].update(ready=False),
        ):
            with self.subTest(mutate=mutate):
                other = deepcopy(current); mutate(other)
                self.assertFalse(compare_environment(other, historical)["reusable"])

    def test_fixture_prefers_reviewed_top5_and_labels_direct_fallback(self):
        from probes.a06_diagnosis.stages import make_fixture
        scene = {"turns": [{"content": "温迪的神之心被谁夺走？"}]}
        target = deepcopy(CORPUS[0]); target["id"] = "fe665dfd7f6417b1aa8a9c5f9"
        distractor = {**deepcopy(CORPUS[0]), "id": "other"}
        rows = [{"query_id": "t1-oracle", "turn": 1, "kind": "oracle", "query": "oracle query",
                 "hits": [target, distractor], "necessary": {"all_covered": True}}]
        fixture = make_fixture(scene, [target, distractor], rows,
                               {"queries": {"t1-oracle": {"semantic_sufficiency": "sufficient"}}})
        self.assertEqual(fixture["selection"], "B_actual_top5")
        tool = json.loads(fixture["messages"][3]["content"])
        self.assertEqual(tool["result"]["evidence"], rows[0]["hits"])
        fallback = make_fixture(scene, [target], rows, {"queries": {}})
        self.assertEqual(fallback["selection"], "direct_corpus_selection")
        self.assertEqual(len(json.loads(fallback["messages"][3]["content"])["result"]["evidence"]), 1)
        self.assertNotIn("criteria", json.dumps(fixture["messages"]))

    def test_semantic_alternative_does_not_require_canonical_pointer_hit(self):
        from probes.a06_diagnosis.stages import make_fixture
        target = {**CORPUS[0], "id": "fe665dfd7f6417b1aa8a9c5f9"}
        alternative = {**CORPUS[0], "id": "alternative", "source_kind": "wiki_compilation"}
        rows = [{"query_id": "t1-oracle", "turn": 1, "kind": "oracle", "query": "oracle query",
                 "hits": [alternative], "necessary": {"all_covered": False}}]
        assessment = {"queries": {"t1-oracle": {"semantic_sufficiency": "sufficient", "supporting_ids": ["alternative"]}}}
        fixture = make_fixture({"turns": [{"content": "原问"}]}, [target, alternative], rows, assessment)
        self.assertEqual(fixture["selection"], "B_actual_top5")
        self.assertIn("[alternative]", fixture["messages"][-1]["content"])
        self.assertIn("Wiki", fixture["messages"][-1]["content"])


if __name__ == "__main__":
    unittest.main()
