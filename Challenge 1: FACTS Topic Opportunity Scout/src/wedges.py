"""
Wedge Title Creator (optional pipeline step, default OFF).

For each finished OpportunityCard, asks DeepSeek V4 Pro (via the Tesseracted Labs
gateway) for up to 3 narrower TOP-list "wedge" titles and validates them in code.

Guarantees:
- Wedges are hypotheses: never scored, never change the card's status or score.
- Validation fails closed: invalid wedges are rejected with reasons, nothing raises.
- If the LLM is unavailable (no key, no `openai` package, HTTP error, empty or
  truncated reply), the step returns [] and the pipeline keeps working.
- Nothing is cached.

Configuration (environment variables, never hard-coded keys):
- FACTS_GATEWAY_API_KEY   gateway API key (required for a real call)
- FACTS_GATEWAY_BASE_URL  gateway base URL (falls back to src.ai_gateway.GATEWAY_BASE_URL)
- FACTS_WEDGE_MODEL       model id (default: DEFAULT_WEDGE_MODEL below)
"""

import json
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

DEFAULT_WEDGE_MODEL = "tesseracted-labs-gmbh/deepseek-ai/DeepSeek-V4-Pro-0813"
MAX_WEDGES = 3
MAX_TITLE_WORDS = 12
MAX_TOKENS = 12000  # reasoning model: hidden reasoning consumes the budget
MAX_HTTP_ATTEMPTS = 3
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

REQUIRED_FIELDS = ("title", "entity_type", "decision_moment", "rationale", "first_validation_question")
ID_RE = re.compile(r"\[([A-Z]{1,3}\d{3,4})\]")
NUM_RE = re.compile(r"\d(?:[\d.,]*\d)?")

# Words ignored when checking that a wedge is narrower than the parent title.
# "TOP" is the FACTS list brand prefix, not a superlative.
TITLE_STOPWORDS = {
    "top", "provider", "for", "the", "and", "with", "der", "die", "das",
    "und", "für", "fuer", "von", "list", "liste",
}

SUPERLATIVE_RE = re.compile(
    r"(\bbest\b|\bbeste[nrs]?\b|\bleading\b|\bführend\w*|\bfuehrend\w*|\btop[- ](?:rated|ranked|notch|tier)\b"
    r"|#\s*1\b|\bnumber\s+one\b|\bno\.\s*1\b|\bnr\.\s*1\b|\bgreatest\b|\bfinest\b|\bpremier\b"
    r"|\bunbeatable\b|\bworld[- ]class\b|\bmarktführer\w*)",
    re.IGNORECASE,
)
SIZE_CLAIM_RE = re.compile(
    r"\b(population|market\s+size|market\s+volume|total\s+number|number\s+of|count\s+of|how\s+many"
    r"|millions?|thousands?|hundreds\s+of|marktgröße|marktvolumen|anzahl|tausende|millionen)\b",
    re.IGNORECASE,
)

SYSTEM_PROMPT = (
    "You are a FACTS topic strategist for Hubert Burda Media TOP-lists. Read the opportunity card. "
    "Propose 1 to 3 concrete NARROWER TOP-list wedges. A wedge is ONE entity type plus ONE decision "
    "moment (plus an optional region). Each wedge title must be more specific than the parent title "
    "and at most 12 words. A wedge is a hypothesis, not a scored recommendation.\n"
    "Rules:\n"
    "- Use only record IDs listed in the card's fact atoms. Do not invent record IDs or numbers.\n"
    "- Do not make market-size or population claims for the narrower group.\n"
    "- No superlatives such as best, leading, top-rated.\n"
    "- Return STRICT JSON only: a list of objects with exactly these keys:\n"
    '{"title": string, "entity_type": string, "decision_moment": string, "region": string or null, '
    '"rationale": string, "evidence_ids": [record ids], "first_validation_question": string}'
)


# --------------------------------------------------------------------------- helpers

def _card_dict(card: Any) -> Dict[str, Any]:
    if hasattr(card, "model_dump"):
        return card.model_dump(mode="json")
    return dict(card or {})


def _tokens(text: str) -> set:
    """Lower-case word tokens (>= 3 letters), with a trailing plural 's' stripped."""
    out = set()
    for t in re.findall(r"[a-zäöüß]{3,}", (text or "").lower()):
        out.add(t[:-1] if len(t) > 3 and t.endswith("s") else t)
    return out


def _content_tokens(text: str) -> set:
    return _tokens(text) - TITLE_STOPWORDS


def _norm_num(n: str) -> str:
    return re.sub(r"[.,]", "", n)


RECORD_ID_RE = re.compile(r"\b[A-Z]{1,3}\d{3,4}\b")


def _nums_in(text: str) -> set:
    """Numbers in text, ignoring record IDs such as [P045] and thousands separators."""
    return {_norm_num(m) for m in NUM_RE.findall(RECORD_ID_RE.sub(" ", text or ""))}


def model_label(model: str) -> str:
    return (model or "").split("/")[-1]


def fact_atoms(card: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Numbered evidence atoms from the card: facts plus dated why-now drivers, each with its IDs."""
    texts = list(card.get("facts") or [])
    texts += [s.strip() for s in (card.get("why_now") or "").split(" | ") if s.strip()]
    atoms = []
    for text in texts:
        ids = ID_RE.findall(text)
        if ids:
            atoms.append({"n": len(atoms) + 1, "text": text, "record_ids": ids})
    return atoms


def _product(p: Dict[str, str]) -> Dict[str, str]:
    return {
        "project_id": p.get("project_id", ""),
        "title": p.get("project_name_en") or p.get("project_name") or "",
        "status": p.get("status", ""),
    }


def portfolio_products(card: Dict[str, Any], loader) -> List[Dict[str, str]]:
    """Portfolio products related to the card: same topic, plus those its opportunity space names."""
    dossier = loader.get_topic_dossier(card.get("topic_key", "")) or {}
    ids = [p.get("project_id", "") for p in dossier.get("portfolio", [])]
    for space in dossier.get("spaces", []):
        ids += [x.strip() for x in (space.get("portfolio_ids") or "").split("|") if x.strip()]
    out, seen = [], set()
    for pid in ids:
        rec = loader.by_id.get(pid)
        if pid and pid not in seen and rec:
            seen.add(pid)
            out.append(_product(rec))
    return out


def all_portfolio_products(loader) -> List[Dict[str, str]]:
    return [_product(p) for p in getattr(loader, "raw_data", {}).get("portfolio", [])]


def build_messages(card: Any, loader) -> List[Dict[str, str]]:
    """LLM input = only the validated card's content (no scores, status or hypotheses)."""
    c = _card_dict(card)
    payload = {
        "parent_title": c.get("proposed_topic", ""),
        "consumer_problem": c.get("consumer_problem", ""),
        "target_user": c.get("target_user", ""),
        "entity_type": c.get("target_entity", ""),
        "fact_atoms": fact_atoms(c),
        "overlapping_portfolio_products": portfolio_products(c, loader),
    }
    user = "Opportunity card:\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n\nReturn the STRICT JSON list."
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


# --------------------------------------------------------------------------- LLM access

def _get_client():
    api_key = os.environ.get("FACTS_GATEWAY_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None
    base_url = os.environ.get("FACTS_GATEWAY_BASE_URL", "").strip()
    if not base_url:
        from .ai_gateway import GATEWAY_BASE_URL  # non-secret URL constant only
        base_url = GATEWAY_BASE_URL
    return OpenAI(base_url=base_url, api_key=api_key, max_retries=0)  # retries handled in ask_text


def call_gateway(model: str, messages: List[Dict[str, str]], max_tokens: int = MAX_TOKENS) -> Tuple[str, Optional[str]]:
    """Single network call (streamed). Returns (content, finish_reason). May raise; callers handle it.

    This is the only function that touches the network; tests patch it.
    """
    client = _get_client()
    if client is None:
        raise RuntimeError("gateway unavailable (FACTS_GATEWAY_API_KEY unset or openai missing)")
    stream = client.chat.completions.create(
        model=model, messages=messages, temperature=0.2, max_tokens=max_tokens, stream=True,
    )
    parts, finish = [], None
    for chunk in stream:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        delta = getattr(choices[0], "delta", None)
        piece = getattr(delta, "content", None) if delta is not None else None
        if piece:
            parts.append(piece)  # reasoning_content is ignored on purpose
        if getattr(choices[0], "finish_reason", None):
            finish = choices[0].finish_reason
    return "".join(parts), finish


def _looks_like_error(text: str) -> bool:
    t = (text or "").strip()
    return t.startswith("[ERROR") or t.startswith("⚠️") or bool(re.match(r"^(error|http\s*\d{3})\b", t, re.IGNORECASE))


def _extract_json_list(text: str) -> Optional[list]:
    if not text:
        return None
    t = re.sub(r"```(?:json)?", "", text).strip()
    start, end = t.find("["), t.rfind("]")
    if start == -1 or end <= start:
        return None
    try:
        out = json.loads(t[start:end + 1])
    except (ValueError, TypeError):
        return None
    return out if isinstance(out, list) else None


def gateway_key_present() -> bool:
    return bool(os.environ.get("FACTS_GATEWAY_API_KEY", "").strip())


def ask_text(model: str, messages, chat_fn: Callable, sleep: Callable) -> Optional[str]:
    """Shared, model-agnostic call with retries (used by the wedge and wedge-score steps).

    Retries once on an empty reply and backs off exponentially on HTTP 429/5xx.
    Returns the reply text, or None on any failure (HTTP error, empty reply, error text).
    Never raises and never caches.
    """
    empty_retries = 1
    http_attempt = 0
    while True:
        try:
            content, _finish = chat_fn(model, messages, MAX_TOKENS)
        except Exception as exc:  # network / HTTP / client errors
            status = getattr(exc, "status_code", None)
            http_attempt += 1
            if status in RETRYABLE_STATUS and http_attempt < MAX_HTTP_ATTEMPTS:
                sleep(2 ** http_attempt)
                continue
            return None
        if not isinstance(content, str) or not content.strip():
            if empty_retries > 0:
                empty_retries -= 1
                continue
            return None
        if _looks_like_error(content):
            return None
        return content


def _ask_model(model: str, messages, chat_fn: Callable, sleep: Callable) -> Optional[list]:
    """Call with retries. Returns a parsed JSON list, or None on any failure."""
    # Truncated replies (finish_reason == "length" with cut-off JSON) fail to parse -> None.
    return _extract_json_list(ask_text(model, messages, chat_fn, sleep))


def _normalise(raw: Any, model: str) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    w = {f: (raw.get(f) if isinstance(raw.get(f), str) else "") for f in REQUIRED_FIELDS}
    region = raw.get("region")
    w["region"] = region.strip() if isinstance(region, str) and region.strip() else None
    ids = raw.get("evidence_ids")
    w["evidence_ids"] = [x.strip() for x in ids if isinstance(x, str)] if isinstance(ids, list) else []
    w["size_status"] = "unvalidated"
    w["generated_by"] = model_label(model)
    return w


def propose_wedges(card: Any, loader, chat_fn: Optional[Callable] = None, model: Optional[str] = None,
                   sleep: Callable = time.sleep) -> List[Dict[str, Any]]:
    """Ask DeepSeek for wedges. Returns normalised (unvalidated) wedges, or [] on any failure."""
    try:
        model = model or os.environ.get("FACTS_WEDGE_MODEL", "").strip() or DEFAULT_WEDGE_MODEL
        if chat_fn is None:
            if _get_client() is None:
                return []
            chat_fn = call_gateway
        parsed = _ask_model(model, build_messages(card, loader), chat_fn, sleep)
        if not parsed:
            return []
        out = []
        for raw in parsed:
            w = _normalise(raw, model)
            if w is not None:
                out.append(w)
        return out
    except Exception:
        return []


# --------------------------------------------------------------------------- validation

def _portfolio_overlap(title: str, products: List[Dict[str, str]]) -> Dict[str, Any]:
    wt = _content_tokens(title)
    matched = []
    for p in products:
        pt = _content_tokens(p["title"])
        if wt and pt and len(wt & pt) / len(pt) >= 0.5:
            matched.append(p["project_id"])
    return {
        "checked": True,
        "compared_portfolio_ids": [p["project_id"] for p in products],
        "flag": bool(matched),
        "matched_portfolio_ids": matched,
    }


def validate_wedges(wedges: Any, card: Any, loader) -> Dict[str, List[Dict[str, Any]]]:
    """Validate wedges against the card and record registry. Never raises.

    Returns {"valid": [...], "rejected": [{"wedge": ..., "errors": [...]}]}.
    """
    c = _card_dict(card)
    if not isinstance(wedges, list):
        wedges = [wedges] if isinstance(wedges, dict) else []
    registry = getattr(loader, "by_id", {}) or {}
    card_ids = set(c.get("evidence") or [])
    parent = c.get("proposed_topic") or ""
    products = all_portfolio_products(loader)  # near-duplicate check against every existing product
    valid, rejected = [], []

    for wedge in wedges:
        try:
            errors = []
            if not isinstance(wedge, dict):
                rejected.append({"wedge": wedge, "errors": ["wedge is not an object"]})
                continue
            for f in REQUIRED_FIELDS:
                v = wedge.get(f)
                if not isinstance(v, str) or not v.strip():
                    errors.append("%s is empty" % f)
            title = wedge.get("title") if isinstance(wedge.get("title"), str) else ""
            rationale = wedge.get("rationale") if isinstance(wedge.get("rationale"), str) else ""
            ids = wedge.get("evidence_ids")
            if not isinstance(ids, list) or not ids:
                errors.append("evidence_ids must be a non-empty list")
                ids = []
            if wedge.get("size_status", "unvalidated") != "unvalidated":
                errors.append("size_status must be 'unvalidated'")

            cited_text = []
            for eid in ids:
                if not isinstance(eid, str) or eid not in registry:
                    errors.append("evidence id does not exist: %s" % eid)
                elif eid not in card_ids:
                    errors.append("evidence id not in card evidence: %s" % eid)
                else:
                    cited_text.append(" ".join(str(v) for v in registry[eid].values()))

            if title:
                if len(title.split()) > MAX_TITLE_WORDS:
                    errors.append("title longer than %d words" % MAX_TITLE_WORDS)
                if not (_content_tokens(title) - _tokens(parent)):
                    errors.append("title is not more specific than parent title")

            allowed = _nums_in(" ".join(cited_text))
            for label, text in (("title", title), ("rationale", rationale)):
                missing = _nums_in(text) - allowed
                if missing:
                    errors.append("number in %s not found in cited records: %s" % (label, ", ".join(sorted(missing))))
                if SUPERLATIVE_RE.search(text):
                    errors.append("superlative in %s" % label)
                if SIZE_CLAIM_RE.search(text):
                    errors.append("market-size/population claim in %s" % label)

            if not errors and len(valid) >= MAX_WEDGES:
                errors.append("cap of %d wedges reached" % MAX_WEDGES)

            if errors:
                rejected.append({"wedge": wedge, "errors": errors})
            else:
                out = dict(wedge)
                out["size_status"] = "unvalidated"
                out.setdefault("region", None)
                out["portfolio_overlap"] = _portfolio_overlap(title, products)
                valid.append(out)
        except Exception as exc:  # fail closed
            rejected.append({"wedge": wedge, "errors": ["validation error: %s" % type(exc).__name__]})

    return {"valid": valid, "rejected": rejected}


def run_wedge_step(card: Any, loader, chat_fn: Optional[Callable] = None, model: Optional[str] = None,
                   sleep: Callable = time.sleep) -> Dict[str, List[Dict[str, Any]]]:
    """Propose + validate. Never raises; returns {"valid": [], "rejected": []} when the LLM is unavailable."""
    try:
        proposed = propose_wedges(card, loader, chat_fn=chat_fn, model=model, sleep=sleep)
        return validate_wedges(proposed, card, loader)
    except Exception:
        return {"valid": [], "rejected": []}
