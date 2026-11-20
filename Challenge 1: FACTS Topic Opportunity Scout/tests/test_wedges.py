"""Tests for the wedge title creator (src/wedges.py). No network: the DeepSeek call is always mocked.

Run from the Challenge 1 folder:  python -m unittest discover -s tests -v
"""

import filecmp
import json
import os
import re
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

CHALLENGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CHALLENGE_DIR not in sys.path:
    sys.path.insert(0, CHALLENGE_DIR)

from src.data_loader import DataLoader  # noqa: E402
from src.generator import CardGenerator  # noqa: E402
from src import wedges  # noqa: E402
import generate_deliverables  # noqa: E402


def no_sleep(_seconds):
    return None


class WedgeTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loader = DataLoader(os.path.join(CHALLENGE_DIR, "data"))
        cls.generator = CardGenerator(cls.loader)
        cls.card_model = cls.generator.generate_card("heat_pumps")
        cls.card = cls.card_model.model_dump(mode="json")

    def setUp(self):
        # Guarantee no real gateway call can happen in tests.
        self._env = patch.dict(os.environ, {"FACTS_GATEWAY_API_KEY": ""})
        self._env.start()
        self._net = patch.object(wedges, "call_gateway", side_effect=AssertionError("network call in test"))
        self._net.start()

    def tearDown(self):
        self._net.stop()
        self._env.stop()

    def valid_wedge(self):
        # P045: "48000 SHK-Handwerksbetriebe ..." is in the heat_pumps card evidence.
        return {
            "title": "TOP SHK installers for heat pump retrofits in older houses",
            "entity_type": "SHK-Handwerksbetriebe",
            "decision_moment": "choosing an installer when replacing a fossil boiler",
            "region": None,
            "rationale": "Owners replacing a fossil heating system need orientation on installers [P045].",
            "evidence_ids": ["P045"],
            "first_validation_question": "Can the Handwerksrolle identify firms that actually install heat pumps?",
        }

    def check(self, w):
        return wedges.validate_wedges([w], self.card, self.loader)

    def assertRejected(self, w, fragment):
        res = self.check(w)
        self.assertEqual(res["valid"], [])
        self.assertEqual(len(res["rejected"]), 1)
        errs = res["rejected"][0]["errors"]
        self.assertTrue(any(fragment in e for e in errs), errs)


class TestValidation(WedgeTestBase):
    def test_accepts_well_formed_wedge(self):
        res = self.check(self.valid_wedge())
        self.assertEqual(len(res["valid"]), 1, res["rejected"])
        w = res["valid"][0]
        self.assertEqual(w["size_status"], "unvalidated")
        self.assertIn("portfolio_overlap", w)
        self.assertIsNone(w["region"])

    def test_top_prefix_is_not_a_superlative(self):
        self.assertTrue(self.valid_wedge()["title"].startswith("TOP "))
        self.assertEqual(len(self.check(self.valid_wedge())["valid"]), 1)

    def test_rejects_nonexistent_id(self):
        w = self.valid_wedge()
        w["evidence_ids"] = ["X9999"]
        self.assertRejected(w, "does not exist")

    def test_rejects_id_not_in_card(self):
        other = sorted(set(self.loader.by_id) - set(self.card["evidence"]))[0]
        w = self.valid_wedge()
        w["evidence_ids"] = [other]
        self.assertRejected(w, "not in card evidence")

    def test_rejects_invented_number(self):
        w = self.valid_wedge()
        w["rationale"] = "About 98765 installers lack transparent quality signals."
        self.assertRejected(w, "number in rationale")

    def test_accepts_number_from_cited_record(self):
        w = self.valid_wedge()
        w["rationale"] = "The Handwerksrolle lists 48,000 SHK businesses as a starting point [P045]."
        res = self.check(w)
        # "48,000" matches the cited record's 48000; no other rule should fire.
        self.assertEqual(len(res["valid"]), 1, res["rejected"])

    def test_rejects_size_claim(self):
        w = self.valid_wedge()
        w["rationale"] = "The population of specialised installers is large."
        self.assertRejected(w, "market-size/population claim")

    def test_rejects_superlative(self):
        w = self.valid_wedge()
        w["title"] = "Best SHK installers for heat pump retrofits"
        self.assertRejected(w, "superlative in title")

    def test_rejects_non_specific_title(self):
        w = self.valid_wedge()
        w["title"] = self.card["proposed_topic"]
        self.assertRejected(w, "not more specific")

    def test_rejects_overlong_title(self):
        w = self.valid_wedge()
        w["title"] = "SHK installers for heat pump retrofits in older detached houses across rural northern Germany"
        self.assertRejected(w, "longer than 12 words")

    def test_rejects_empty_required_field(self):
        w = self.valid_wedge()
        w["decision_moment"] = "  "
        self.assertRejected(w, "decision_moment is empty")

    def test_cap_of_three(self):
        base = self.valid_wedge()
        ws = []
        for extra in ("hybrid", "bivalent", "geothermal", "airsource"):
            w = dict(base)
            w["title"] = "SHK installers for %s heat pump retrofits" % extra
            ws.append(w)
        res = wedges.validate_wedges(ws, self.card, self.loader)
        self.assertEqual(len(res["valid"]), 3)
        self.assertTrue(any("cap of 3" in e for r in res["rejected"] for e in r["errors"]))

    def test_portfolio_overlap_is_flagged_not_rejected(self):
        products = [{"project_id": "F999", "title": "TOP Heat pump installers", "status": "current"}]
        w = self.valid_wedge()
        w["title"] = "TOP heat pump installers for older houses"
        with patch.object(wedges, "all_portfolio_products", return_value=products):
            res = self.check(w)
        self.assertEqual(len(res["valid"]), 1, res["rejected"])
        self.assertTrue(res["valid"][0]["portfolio_overlap"]["flag"])
        self.assertEqual(res["valid"][0]["portfolio_overlap"]["matched_portfolio_ids"], ["F999"])

    def test_overlap_checked_against_whole_portfolio(self):
        res = self.check(self.valid_wedge())
        compared = res["valid"][0]["portfolio_overlap"]["compared_portfolio_ids"]
        self.assertEqual(len(compared), len(self.loader.raw_data["portfolio"]))

    def test_german_best_prefix_words_are_not_superlatives(self):
        for title in ("SHK installers for Wärmepumpen im Bestand", "Bestatter for heat pump households"):
            self.assertIsNone(wedges.SUPERLATIVE_RE.search(title), title)
        for title in ("Beste SHK installers", "leading heat pump installers", "top-rated installers"):
            self.assertIsNotNone(wedges.SUPERLATIVE_RE.search(title), title)

    def test_plural_only_change_is_not_more_specific(self):
        w = self.valid_wedge()
        w["title"] = "TOP Provider for Heat pump & heating replacements"
        self.assertRejected(w, "not more specific")

    def test_garbage_input_never_raises(self):
        res = wedges.validate_wedges([None, 5, "x", {"title": 3, "evidence_ids": "P045"}], self.card, self.loader)
        self.assertEqual(res["valid"], [])
        self.assertEqual(len(res["rejected"]), 4)


class TestPropose(WedgeTestBase):
    def fake(self, *replies):
        calls = []
        replies = list(replies)

        def chat(model, messages, max_tokens):
            calls.append({"model": model, "messages": messages, "max_tokens": max_tokens})
            r = replies.pop(0) if replies else ("", "stop")
            if isinstance(r, Exception):
                raise r
            return r
        return chat, calls

    def test_valid_json_gives_validated_wedges_with_generated_by(self):
        chat, calls = self.fake((json.dumps([self.valid_wedge()]), "stop"))
        res = wedges.run_wedge_step(self.card_model, self.loader, chat_fn=chat, sleep=no_sleep)
        self.assertEqual(len(res["valid"]), 1, res["rejected"])
        self.assertEqual(res["valid"][0]["generated_by"], "DeepSeek-V4-Pro-0813")
        self.assertEqual(calls[0]["model"], wedges.DEFAULT_WEDGE_MODEL)
        self.assertGreaterEqual(calls[0]["max_tokens"], 12000)

    def test_model_id_configurable_by_env(self):
        chat, calls = self.fake((json.dumps([self.valid_wedge()]), "stop"))
        with patch.dict(os.environ, {"FACTS_WEDGE_MODEL": "tesseracted-labs-gmbh/deepseek-ai/Other"}):
            wedges.propose_wedges(self.card, self.loader, chat_fn=chat, sleep=no_sleep)
        self.assertEqual(calls[0]["model"], "tesseracted-labs-gmbh/deepseek-ai/Other")

    def test_prompt_contains_only_card_content(self):
        chat, calls = self.fake(("[]", "stop"))
        wedges.propose_wedges(self.card, self.loader, chat_fn=chat, sleep=no_sleep)
        user = calls[0]["messages"][1]["content"]
        payload = json.loads(user.split("Opportunity card:\n", 1)[1].split("\n\nReturn", 1)[0])
        self.assertEqual(set(payload), {"parent_title", "consumer_problem", "target_user", "entity_type",
                                        "fact_atoms", "overlapping_portfolio_products"})
        self.assertNotIn("overall_score", user)
        self.assertNotIn("recommended_status", user)

    def test_empty_reply_retries_once_then_returns_empty(self):
        chat, calls = self.fake(("", "stop"), ("   ", "stop"))
        self.assertEqual(wedges.propose_wedges(self.card, self.loader, chat_fn=chat, sleep=no_sleep), [])
        self.assertEqual(len(calls), 2)

    def test_empty_then_valid_reply_succeeds(self):
        chat, calls = self.fake(("", "length"), (json.dumps([self.valid_wedge()]), "stop"))
        self.assertEqual(len(wedges.propose_wedges(self.card, self.loader, chat_fn=chat, sleep=no_sleep)), 1)

    def test_truncated_json_returns_empty(self):
        cut = json.dumps([self.valid_wedge()])[:-40]
        chat, _ = self.fake((cut, "length"))
        self.assertEqual(wedges.propose_wedges(self.card, self.loader, chat_fn=chat, sleep=no_sleep), [])

    def test_error_text_returns_empty(self):
        for text in ("[ERROR 429] rate limited", "⚠️ Tesseracted AI Gateway error: boom"):
            chat, _ = self.fake((text, "stop"))
            self.assertEqual(wedges.propose_wedges(self.card, self.loader, chat_fn=chat, sleep=no_sleep), [])

    def test_garbage_and_none_return_empty(self):
        for reply in (("not json at all", "stop"), (None, None), ('{"title": "x"}', "stop")):
            chat, _ = self.fake(reply)
            self.assertEqual(wedges.propose_wedges(self.card, self.loader, chat_fn=chat, sleep=no_sleep), [])

    def test_http_429_backs_off_then_succeeds(self):
        class HTTPError(Exception):
            status_code = 429
        slept = []
        chat, calls = self.fake(HTTPError(), (json.dumps([self.valid_wedge()]), "stop"))
        out = wedges.propose_wedges(self.card, self.loader, chat_fn=chat, sleep=slept.append)
        self.assertEqual(len(out), 1)
        self.assertEqual(slept, [2])

    def test_http_500_persistent_returns_empty(self):
        class HTTPError(Exception):
            status_code = 503
        chat, calls = self.fake(HTTPError(), HTTPError(), HTTPError(), HTTPError())
        self.assertEqual(wedges.propose_wedges(self.card, self.loader, chat_fn=chat, sleep=no_sleep), [])
        self.assertEqual(len(calls), wedges.MAX_HTTP_ATTEMPTS)

    def test_no_key_returns_empty_without_network(self):
        # FACTS_GATEWAY_API_KEY is blank and call_gateway raises if touched.
        self.assertEqual(wedges.propose_wedges(self.card, self.loader), [])
        self.assertEqual(wedges.run_wedge_step(self.card, self.loader), {"valid": [], "rejected": []})

    def test_call_gateway_streams_content_and_ignores_reasoning(self):
        self._net.stop()  # exercise the real call_gateway with a fake client (still no network)
        try:
            def ch(content=None, finish=None, reasoning=None, empty=False):
                if empty:
                    return SimpleNamespace(choices=[])
                delta = SimpleNamespace(content=content, reasoning_content=reasoning)
                return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish)])
            chunks = [ch(empty=True), ch(reasoning="thinking..."), ch("[{"), ch('"a": 1}'), ch("]", finish="length")]
            seen = {}

            def create(**kw):
                seen.update(kw)
                return iter(chunks)
            fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
            with patch.object(wedges, "_get_client", return_value=fake):
                content, finish = wedges.call_gateway("m", [], 12000)
        finally:
            self._net.start()
        self.assertEqual(content, '[{"a": 1}]')
        self.assertEqual(finish, "length")
        self.assertTrue(seen["stream"])
        self.assertGreaterEqual(seen["max_tokens"], 12000)

    def test_code_path_references_no_other_model(self):
        with open(wedges.__file__, encoding="utf-8") as f:
            src = f.read()
        for name in ("kimi", "glm", "gemma", "qwen", "available_models", r"default_model\b"):
            self.assertIsNone(re.search(name, src, re.IGNORECASE), name)
        self.assertEqual(src.count("DeepSeek-V4-Pro-0813"), 1)


class TestPipelineDefaultOff(unittest.TestCase):
    def test_default_off_output_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            generate_deliverables.main(["--out-dir", tmp])
            for name in ("cards.json", "cards.md", "LOGIC.md"):
                self.assertTrue(filecmp.cmp(os.path.join(tmp, name), os.path.join(CHALLENGE_DIR, name),
                                            shallow=False), name)
            self.assertFalse(os.path.exists(os.path.join(tmp, "wedge_validation_report.json")))

    def test_wedges_on_without_llm_keeps_cards_and_scores(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"FACTS_GATEWAY_API_KEY": ""}):
            generate_deliverables.main(["--wedges", "--out-dir", tmp])
            with open(os.path.join(tmp, "cards.json"), encoding="utf-8") as f:
                on = json.load(f)
            with open(os.path.join(CHALLENGE_DIR, "cards.json"), encoding="utf-8") as f:
                off = json.load(f)
            for a, b in zip(on, off):
                self.assertEqual(a["wedges"], [])
                self.assertEqual(a["parent_title"], b["proposed_topic"])
                a = {k: v for k, v in a.items() if k not in ("wedges", "parent_title")}
                self.assertEqual(a, b)
            with open(os.path.join(tmp, "cards.md"), encoding="utf-8") as f:
                self.assertIn("Narrower wedges (hypotheses, unscored)", f.read())


if __name__ == "__main__":
    unittest.main()
