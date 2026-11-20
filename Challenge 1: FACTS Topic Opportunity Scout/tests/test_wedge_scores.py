"""Tests for the wedge validity score (src/wedge_scores.py). No network: the Kimi call is always mocked.

Run from the Challenge 1 folder:  python -m unittest discover -s tests -v
"""

import contextlib
import filecmp
import io
import json
import os
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

CHALLENGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CHALLENGE_DIR not in sys.path:
    sys.path.insert(0, CHALLENGE_DIR)

from src.data_loader import DataLoader  # noqa: E402
from src.generator import CardGenerator  # noqa: E402
from src import wedges, wedge_scores as WS  # noqa: E402
import generate_deliverables  # noqa: E402


def no_sleep(_s):
    return None


def crit(**scores):
    """Kimi-style criteria object. Values: int score, None, or (score, reason)."""
    out = {}
    for name in WS.CRITERIA:
        v = scores.get(name, 4)
        if isinstance(v, tuple):
            out[name] = {"score": v[0], "reason": v[1]}
        else:
            out[name] = {"score": v, "reason": "Supported by the cited record [P045]." if v is not None else None}
    return out


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loader = DataLoader(os.path.join(CHALLENGE_DIR, "data"))
        cls.card_model = CardGenerator(cls.loader).generate_card("heat_pumps")
        cls.card = cls.card_model.model_dump(mode="json")

    def setUp(self):
        self._env = patch.dict(os.environ, {"FACTS_GATEWAY_API_KEY": ""})
        self._env.start()
        self._net = patch.object(wedges, "call_gateway", side_effect=AssertionError("network call in test"))
        self._net.start()

    def tearDown(self):
        self._net.stop()
        self._env.stop()

    def wedge(self, title="TOP SHK installers for heat pump retrofits in older houses"):
        w = {
            "title": title,
            "entity_type": "SHK-Handwerksbetriebe",
            "decision_moment": "choosing an installer when replacing a fossil boiler",
            "region": None,
            "rationale": "Owners replacing a fossil heating system need orientation on installers [P045].",
            "evidence_ids": ["P045"],
            "first_validation_question": "Can the Handwerksrolle identify heat pump installers?",
        }
        res = wedges.validate_wedges([w], self.card, self.loader)
        self.assertEqual(len(res["valid"]), 1, res["rejected"])
        return res["valid"][0]

    def kimi(self, *replies):
        calls = []
        replies = list(replies)

        def chat(model, messages, max_tokens):
            calls.append({"model": model, "messages": messages, "max_tokens": max_tokens})
            r = replies.pop(0) if replies else ("", "stop")
            if isinstance(r, Exception):
                raise r
            if isinstance(r, dict):
                return json.dumps(r), "stop"
            return r
        return chat, calls

    def score_one(self, reply, wedge=None):
        chat, calls = self.kimi(reply, reply)
        out = WS.score_wedges(self.card, [wedge or self.wedge()], self.loader, chat_fn=chat, sleep=no_sleep)
        return out[0]["validity"], calls


class TestScoring(Base):
    def test_weighting_all_known(self):
        c = {n: {"score": s, "reason": "x"} for n, s in zip(WS.CRITERIA, (4, 2, 4, 0, 4))}
        expected = round(25 * (0.30 * 4 + 0.25 * 2 + 0.15 * 4 + 0.15 * 0 + 0.15 * 4))
        self.assertEqual(WS.compute_score(c), expected)

    def test_renormalisation_with_one_unknown(self):
        c = {n: {"score": 4, "reason": "x"} for n in WS.CRITERIA}
        c["evidence_support"] = {"score": None, "reason": None}
        c["entity_grounding"]["score"] = 0
        # known weights: 0.25*0 + 0.15*4*3 = 1.8 over 0.70 -> 2.571.. * 25 = 64.3
        self.assertEqual(WS.compute_score(c), round(25 * 1.8 / 0.70))

    def test_unknown_is_never_zero(self):
        c = {n: {"score": 4, "reason": "x"} for n in WS.CRITERIA}
        c["distinctiveness"] = {"score": None, "reason": None}
        self.assertEqual(WS.compute_score(c), 100)

    def test_two_unknown_is_unscored(self):
        v, _ = self.score_one({"criteria": crit(specificity=None, decision_clarity=None)})
        self.assertIsNone(v["score"])
        self.assertEqual(v["label"], "unscored")
        self.assertTrue(v["needs_human_review"])
        self.assertTrue(v["review_reasons"])

    def test_inflated_overall_is_ignored(self):
        v, _ = self.score_one({"criteria": crit(evidence_support=2, entity_grounding=2, specificity=2,
                                                decision_clarity=2, distinctiveness=2), "overall": 100, "score": 99})
        self.assertEqual(v["score"], 50)
        self.assertEqual(v["label"], "medium")

    def test_invented_id_nulls_only_that_criterion(self):
        v, _ = self.score_one({"criteria": crit(evidence_support=(4, "See record [X9999]."))})
        self.assertIsNone(v["criteria"]["evidence_support"]["score"])
        self.assertTrue(any("non-existent id" in n for n in v["notes"]))
        self.assertIsNotNone(v["score"])  # one unknown -> still scored, renormalised
        self.assertEqual(v["criteria"]["specificity"]["score"], 4)

    def test_id_outside_evidence_nulls_criterion(self):
        other = sorted(set(self.loader.by_id) - set(self.card["evidence"]))[0]
        v, _ = self.score_one({"criteria": crit(entity_grounding=(4, "Seen in [%s]." % other))})
        self.assertIsNone(v["criteria"]["entity_grounding"]["score"])
        self.assertTrue(any("outside wedge/card evidence" in n for n in v["notes"]))

    def test_invented_number_nulls_criterion(self):
        v, _ = self.score_one({"criteria": crit(decision_clarity=(3, "About 98765 owners decide each year."))})
        self.assertIsNone(v["criteria"]["decision_clarity"]["score"])
        self.assertTrue(any("number not in cited records" in n for n in v["notes"]))

    def test_number_from_cited_record_is_allowed(self):
        v, _ = self.score_one({"criteria": crit(evidence_support=(4, "[P045] lists 48,000 SHK businesses."))})
        self.assertEqual(v["criteria"]["evidence_support"]["score"], 4)

    def test_non_integer_score_nulls_criterion(self):
        v, _ = self.score_one({"criteria": crit(specificity=(5, "x"), decision_clarity=(2.5, "x"))})
        self.assertIsNone(v["criteria"]["specificity"]["score"])
        self.assertIsNone(v["criteria"]["decision_clarity"]["score"])
        self.assertEqual(v["label"], "unscored")

    def test_label_thresholds(self):
        self.assertEqual(WS.label_for(75), "high")
        self.assertEqual(WS.label_for(74), "medium")
        self.assertEqual(WS.label_for(50), "medium")
        self.assertEqual(WS.label_for(49), "low")
        self.assertEqual(WS.label_for(None), "unscored")

    def test_low_needs_human_review(self):
        v, _ = self.score_one({"criteria": crit(evidence_support=1, entity_grounding=1, specificity=1,
                                                decision_clarity=1, distinctiveness=1)})
        self.assertEqual(v["label"], "low")
        self.assertTrue(v["needs_human_review"])

    def test_label_capped_when_entity_not_in_cited_text(self):
        w = self.wedge()
        w["entity_type"] = "Zauberer Gilde"
        v, _ = self.score_one({"criteria": crit()}, wedge=w)
        self.assertEqual(v["score"], 100)
        self.assertFalse(v["data_checks"]["entity_in_cited_text"])
        self.assertEqual(v["label"], "medium")
        self.assertTrue(any("capped" in r for r in v["review_reasons"]))

    def test_data_checks_pass_for_good_wedge(self):
        v, _ = self.score_one({"criteria": crit()})
        dc = v["data_checks"]
        self.assertTrue(dc["ids_exist"] and dc["ids_in_card_evidence"] and dc["cites_beyond_parent_space"])
        self.assertTrue(dc["entity_in_cited_text"])
        self.assertEqual(dc["checks_passed"], dc["checks_total"])
        self.assertEqual(v["label"], "high")
        self.assertEqual(v["basis"], "llm_assessed")
        self.assertEqual(v["scored_by"], "Kimi-K3.1-Pro")

    def test_sibling_duplicate_flag(self):
        a = self.wedge("TOP SHK installers for heat pump retrofits in older houses")
        b = self.wedge("SHK installers for heat pump retrofits in old houses")
        c = self.wedge("SHK installers advising on hybrid systems")
        checks = [WS.data_checks(self.card, w, [a, b, c], self.loader) for w in (a, b, c)]
        self.assertFalse(checks[0]["no_sibling_duplicate"])
        self.assertFalse(checks[1]["no_sibling_duplicate"])
        self.assertTrue(checks[2]["no_sibling_duplicate"])

    def test_ordering_by_score_unscored_last_stable(self):
        ws = [{"t": "a", "validity": {"score": None}}, {"t": "b", "validity": {"score": 60}},
              {"t": "c", "validity": {"score": 90}}, {"t": "d", "validity": {"score": 60}}]
        self.assertEqual([w["t"] for w in WS.order_by_validity(ws)], ["c", "b", "d", "a"])

    def test_score_wedges_keeps_order(self):
        a, b = self.wedge(), self.wedge("SHK installers advising on hybrid systems")
        chat, _ = self.kimi({"criteria": crit(evidence_support=1)}, {"criteria": crit()})
        out = WS.score_wedges(self.card, [a, b], self.loader, chat_fn=chat, sleep=no_sleep)
        self.assertEqual([w["title"] for w in out], [a["title"], b["title"]])
        self.assertLess(out[0]["validity"]["score"], out[1]["validity"]["score"])

    def test_failure_replies_give_unscored_and_never_raise(self):
        cut = json.dumps({"criteria": crit()})[:-30]
        for reply in (("", "stop"), (cut, "length"), ("[ERROR 429] rate limited", "stop"),
                      (None, None), ("not json", "stop")):
            v, _ = self.score_one(reply)
            self.assertIsNone(v["score"], reply)
            self.assertEqual(v["label"], "unscored")
            self.assertTrue(v["needs_human_review"])
            self.assertTrue(v["notes"])

    def test_http_error_gives_unscored(self):
        class HTTPError(Exception):
            status_code = 503
        chat, calls = self.kimi(HTTPError(), HTTPError(), HTTPError())
        out = WS.score_wedges(self.card, [self.wedge()], self.loader, chat_fn=chat, sleep=no_sleep)
        self.assertEqual(out[0]["validity"]["label"], "unscored")
        self.assertEqual(len(calls), wedges.MAX_HTTP_ATTEMPTS)

    def test_no_key_gives_unscored_without_network(self):
        out = WS.score_wedges(self.card, [self.wedge()], self.loader)
        self.assertEqual(out[0]["validity"]["label"], "unscored")
        self.assertTrue(any("gateway unavailable" in n for n in out[0]["validity"]["notes"]))

    def test_nothing_cached(self):
        chat, calls = self.kimi({"criteria": crit()}, {"criteria": crit()})
        w = self.wedge()
        WS.score_wedges(self.card, [w], self.loader, chat_fn=chat, sleep=no_sleep)
        WS.score_wedges(self.card, [w], self.loader, chat_fn=chat, sleep=no_sleep)
        self.assertEqual(len(calls), 2)
        self.assertNotIn("validity", w)  # input wedge not mutated

    def test_kimi_model_and_tokens(self):
        _, calls = self.score_one({"criteria": crit()})
        self.assertEqual(calls[0]["model"], WS.DEFAULT_SCORE_MODEL)
        self.assertGreaterEqual(calls[0]["max_tokens"], 12000)
        with patch.dict(os.environ, {"FACTS_SCORE_MODEL": "tesseracted-labs-gmbh/moonshotai/Other"}):
            _, calls = self.score_one({"criteria": crit()})
        self.assertEqual(calls[0]["model"], "tesseracted-labs-gmbh/moonshotai/Other")

    def test_prompt_contains_wedge_atoms_and_cited_records_only(self):
        _, calls = self.score_one({"criteria": crit()})
        user = calls[0]["messages"][1]["content"]
        payload = json.loads(user.split("Review input:\n", 1)[1].split("\n\nReturn", 1)[0])
        self.assertEqual(set(payload), {"parent_title", "fact_atoms", "wedge", "sibling_wedge_titles", "cited_records"})
        self.assertEqual(list(payload["cited_records"]), ["P045"])
        self.assertNotIn("overall_score", user)
        self.assertNotIn("recommended_status", user)

    def test_model_ids_referenced(self):
        ids = set()
        for mod in (wedges, WS):
            with open(mod.__file__, encoding="utf-8") as f:
                src = f.read()
            for name in ("glm", "gemma", "qwen", "available_models", r"default_model\b"):
                self.assertIsNone(re.search(name, src, re.IGNORECASE), (mod.__name__, name))
            ids |= set(re.findall(r'"(tesseracted-labs-gmbh/[^"]+)"', src))
        self.assertEqual(ids, {"tesseracted-labs-gmbh/deepseek-ai/DeepSeek-V4-Pro-0813",
                               "tesseracted-labs-gmbh/moonshotai/Kimi-K3.1-Pro"})
        with open(wedges.__file__, encoding="utf-8") as f:
            self.assertNotIn("kimi", f.read().lower())


class TestPipeline(Base):
    def run_main(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            generate_deliverables.main(argv)
        return buf.getvalue()

    def test_default_off_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_main(["--out-dir", tmp])
            for name in ("cards.json", "cards.md", "LOGIC.md"):
                self.assertTrue(filecmp.cmp(os.path.join(tmp, name), os.path.join(CHALLENGE_DIR, name),
                                            shallow=False), name)

    def test_wedge_scores_without_wedges_errors(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            generate_deliverables.main(["--wedge-scores"])
        self.assertIn("--wedge-scores requires --wedges", err.getvalue())

    def test_missing_key_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self.run_main(["--wedges", "--wedge-scores", "--out-dir", tmp])
        self.assertIn("FACTS_GATEWAY_API_KEY not set - skipping wedge generation", out)
        self.assertIn("FACTS_GATEWAY_API_KEY not set - skipping wedge validity scoring", out)

    def end_to_end(self, kimi_reply):
        good = {
            "title": "TOP SHK installers for heat pump retrofits in older houses",
            "entity_type": "SHK-Handwerksbetriebe", "decision_moment": "replacing a fossil boiler",
            "region": None, "rationale": "Owners need orientation on installers [P045].",
            "evidence_ids": ["P045"], "first_validation_question": "Which register lists heat pump installers?",
        }
        good2 = dict(good, title="SHK installers advising on hybrid heating systems")
        ds = lambda m, x, t: (json.dumps([good, good2]), "stop")  # noqa: E731
        replies = list(kimi_reply)
        kimi = lambda m, x, t: replies.pop(0) if replies else ("", "stop")  # noqa: E731
        real_run, real_score = generate_deliverables.run_wedge_step, generate_deliverables.score_wedges
        tmp = tempfile.mkdtemp()
        with patch.object(generate_deliverables, "run_wedge_step", lambda c, l: real_run(c, l, chat_fn=ds)), \
                patch.object(generate_deliverables, "score_wedges",
                             lambda c, w, l: real_score(c, w, l, chat_fn=kimi, sleep=no_sleep)):
            self.run_main(["--wedges", "--wedge-scores", "--out-dir", tmp])
        return tmp

    def test_end_to_end_mocked_scores_do_not_change_cards(self):
        low = json.dumps({"criteria": crit(evidence_support=1, entity_grounding=1, specificity=1,
                                           decision_clarity=1, distinctiveness=1)})
        high = json.dumps({"criteria": crit()})
        tmp = self.end_to_end([(low, "stop"), (high, "stop")])
        with open(os.path.join(tmp, "cards.json"), encoding="utf-8") as f:
            on = json.load(f)
        with open(os.path.join(CHALLENGE_DIR, "cards.json"), encoding="utf-8") as f:
            off = json.load(f)
        for a, b in zip(on, off):
            self.assertEqual({k: v for k, v in a.items() if k not in ("wedges", "parent_title")}, b)
        hp = next(c for c in on if c["topic_key"] == "heat_pumps")
        self.assertEqual([w["validity"]["label"] for w in hp["wedges"]], ["high", "low"])  # re-ordered by score
        for w in hp["wedges"]:
            self.assertEqual(w["size_status"], "unvalidated")
        with open(os.path.join(tmp, "cards.md"), encoding="utf-8") as f:
            md = f.read()
        self.assertIn("model-assessed by `Kimi-K3.1-Pro`, not data-validated", md)
        self.assertIn("data checks 5/5 passed", md)
        with open(os.path.join(tmp, "wedge_validation_report.json"), encoding="utf-8") as f:
            report = json.load(f)
        self.assertTrue(all("scoring" in e for e in report))

    def test_end_to_end_scoring_failure_continues(self):
        tmp = self.end_to_end([("", "stop"), ("", "stop"), ("[ERROR 500]", "stop")])
        with open(os.path.join(tmp, "wedge_validation_report.json"), encoding="utf-8") as f:
            report = json.load(f)
        hp = next(e for e in report if e["topic_key"] == "heat_pumps")
        self.assertEqual([s["label"] for s in hp["scoring"]], ["unscored", "unscored"])


if __name__ == "__main__":
    unittest.main()
