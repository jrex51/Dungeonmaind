"""Local-LLM analysis for high-quality timeline events.

The existing Ollama model acts as a second-stage judge after the cheap semantic
filter. Bounded batches decide importance, classify events, and extract exact
evidence and location/temporal spans using the same validator as single-event
analysis. If Ollama is unavailable,
callers use semantic filtering with conservative source-derived titles.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from time import perf_counter

import requests

from app.core.config import settings


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
TIMELINE_AI_ENABLED = os.getenv("TIMELINE_AI_ENABLED", "true").strip().lower() not in {
    "0", "false", "no", "off"
}
TIMELINE_AI_TIMEOUT = float(os.getenv("TIMELINE_AI_TIMEOUT", "45"))

VALID_CATEGORIES = {
    "travel",
    "combat",
    "dialogue",
    "discovery",
    "rest",
    "quest",
    "item",
    "other",
}


@dataclass(frozen=True)
class TimelineAIAnalysis:
    keep: bool
    importance: float
    category: str
    title: str | None
    locations: tuple[str, ...]
    temporal_entities: tuple[str, ...]
    reason: str | None
    evidence: str | None = None


NON_OCCURRENCE = re.compile(
    r"\b(?:going to|gonna|will|would|can|could|should|must|might|may|if|unless|"
    r"(?:want|hope|plan|intend|need|try|decide|expect)(?:s|ed)? to|"
    r"planned to|planning to|tried to|trying to|decided to|supposed to|about to|let['’]s|"
    r"propos(?:e[ds]?|ing)|suggest(?:s|ed|ing)?|consider(?:s|ed|ing)?|"
    r"tomorrow|next session|"
    r"not|never|no|nobody|\w+n['’]t|cannot)\b",
    re.IGNORECASE,
)
_TRAVEL_DESTINATION = (
    r"(?:(?-i:[A-Z])\w*|(?:the |a |an )?(?:[\w-]+ ){0,2}"
    r"(?:town|village|city|bridge|road|forest|cave|cellar|tower|camp|gate|"
    r"dungeon|tavern|inn|castle|temple|keep|river|chamber|room|home|valley)\b)"
)
TRAVEL_ACTION = re.compile(
    r"\b(?:arrive[ds]? (?:at|in)|made it to|(?:go(?:es)?|went) (?:back )?to|"
    r"travel(?:s|l?ed)? (?:to|from|through)|return(?:s|ed)? (?:to|from)|"
    r"(?:walk|head)(?:s|ed)? (?:to|towards?|into|through)|"
    rf"(?:reach|enter|cross)(?:es|s|ed)?)\s+{_TRAVEL_DESTINATION}",
    re.IGNORECASE,
)
TRAVEL_DESCRIPTION = re.compile(
    r"^(?:it|(?:the|a|an) (?:\w+ )?(?:road|path|bridge|passage|stairs|staircase|tunnel)) "
    r"(?:leads?|runs?|connects?)\b",
    re.IGNORECASE,
)
COMBAT_ACTION = re.compile(
    r"\b(?:ambush(?:es|ed)?|attack(?:s|ed)?|defeat(?:s|ed)?|kill(?:s|ed)?)\s+"
    r"(?:the |a |an |us\b|you\b|him\b|her\b|them\b|(?-i:[A-Z]))"
    r"|\b(?:fight|battle|combat) (?:is over|ends?|ended|starts?|started|begins?|began)\b",
    re.IGNORECASE,
)
REST_ACTION = re.compile(r"\b(?:takes?|took) (?:a |the )?(?:short|long) rest\b", re.IGNORECASE)
ITEM_ACQUISITION = re.compile(
    r"\b(?:obtain(?:s|ed)?|acquir(?:e[ds]?)|receiv(?:e[ds]?)|found|finds?|"
    r"pick(?:s|ed)? up|takes?|took|grab(?:s|bed)?|pull(?:s|ed)? out|"
    r"bought|purchas(?:e[ds]?)|loot(?:s|ed)?|gave|gives?|hand(?:s|ed)?)\s+"
    r"(?!(?:(?:a |the )?(?:look|glance|location|picture)|out|that|where|how)\b)"
    r"[^.!?;]{0,70}\b(?:keys?|potions?|scrolls?|amulets?|rings?|swords?|shields?|"
    r"daggers?|coins?|treasure|loot|relics?|artifacts?|items?)\b",
    re.IGNORECASE,
)
ITEM_MECHANICS = re.compile(
    r"\b(?:attacks?|great weapon master|dice|rolls?|modifier|damage|"
    r"spell slots?|actions?|saving throws?|proficiency bonus|advantage|"
    r"disadvantage|d\d+|rerolls?|ability checks?)\b",
    re.IGNORECASE,
)
ITEM_ACTION = re.compile(
    r"\b(?:obtained|acquired|received|picked up|took|bought|purchased|"
    r"looted|stole|sold|gave|handed|lost|destroyed|used|identified|"
    r"obtain|obtains|acquire|acquires|receive|receives|pick up|picks up|"
    r"take|takes|buy|buys|give|gives|use|uses)\s+\S+",
    re.IGNORECASE,
)
ITEM_ACTION_OR_ACQUISITION = re.compile(
    rf"{ITEM_ACTION.pattern}|{ITEM_ACQUISITION.pattern}", re.IGNORECASE
)


def transcript_sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.!?])\s+", text.strip()) if text.strip() else []


def _occurring_clauses(sentence: str) -> list[str]:
    if sentence.endswith("?") or re.match(r"\s*(?:if|unless|before)\b", sentence, re.IGNORECASE):
        return []
    clauses = re.split(
        r"[,;]?\s+\b(?:but|and|so)\s+(?=(?:I|we|you|they|he|she|the|"
        r"eventually (?:arrived|reached|entered|returned|travell?ed|went|made))\b)",
        sentence, flags=re.IGNORECASE,
    )
    return [clause for clause in clauses if not NON_OCCURRENCE.search(clause)]


def _action_sentences(text: str, action: re.Pattern, *, item: bool = False) -> list[str]:
    """Keep the whole sentence, including qualifiers outside the action clause."""
    return [
        sentence for sentence in transcript_sentences(text)
        if any(action.search(clause) and not (item and ITEM_MECHANICS.search(clause))
               for clause in _occurring_clauses(sentence))
    ]


def item_event_sentences(text: str) -> list[str]:
    """Return sentences with item-action evidence for AI and offline validation."""
    return _action_sentences(text, ITEM_ACTION_OR_ACQUISITION, item=True)


def travel_event_sentences(text: str) -> list[str]:
    return _action_sentences(text, TRAVEL_ACTION)


def explicit_event_evidence(text: str) -> tuple[str, str] | None:
    """Recognize clear in-world actions independently of embedding scores."""
    for category, pattern in (("travel", TRAVEL_ACTION), ("combat", COMBAT_ACTION),
                              ("item", ITEM_ACQUISITION), ("rest", REST_ACTION)):
        sentences = _action_sentences(text, pattern, item=category == "item")
        if sentences:
            return category, sentences[0]
    return None


def travel_evidence_allowed(evidence: str) -> bool:
    if travel_event_sentences(evidence):
        return True
    return (bool(_occurring_clauses(evidence)) and not NON_OCCURRENCE.search(evidence)
            and not TRAVEL_DESCRIPTION.match(evidence))


def travel_location_evidence(evidence: str) -> str:
    return " ".join(_occurring_clauses(evidence))


def _grounded_evidence(text: str, evidence: object) -> str | None:
    """Match a whole source sentence without removing surrounding qualifiers."""
    if not isinstance(evidence, str) or not evidence.strip():
        return None
    source = " ".join(text.split()).strip()
    candidate = " ".join(evidence.split()).strip()
    return next((sentence for sentence in transcript_sentences(source)
                 if sentence.casefold() == candidate.casefold()), None)


def grounded_event_title(text: str, category: str, evidence: object = None) -> str | None:
    """Ground wording, not event semantics; keep/occurred decide AI validity.

    Long evidence stays intact in the analysis. Its title is explicitly marked
    as a transcript excerpt, rather than presenting a truncated assertion as a
    complete sentence. Category selection belongs to the fallback caller.
    """
    sentence = _grounded_evidence(text, evidence if evidence is not None else text)
    if sentence is None:
        return None
    if len(sentence) <= 120:
        return sentence
    prefix = sentence[:107].rsplit(" ", 1)[0]
    return f'Excerpt: “{prefix}…”'


def _extract_json_object(value: str) -> dict | None:
    value = value.strip()
    if not value:
        return None

    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    # Tolerate models wrapping JSON in markdown or a short explanation.
    match = re.search(r"\{.*\}", value, flags=re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _exact_spans(values: object, source_text: str) -> tuple[str, ...]:
    """Accept only values that really occur in the transcript.

    This prevents an LLM from inventing a fantasy location or time expression.
    Matching is case-insensitive and the returned text uses the original source
    casing.
    """
    if not isinstance(values, list):
        return ()

    output: list[str] = []
    seen: set[str] = set()
    for raw in values:
        if not isinstance(raw, str):
            continue
        candidate = " ".join(raw.split()).strip(" \t\n\r.,;:!?\"'()[]{}")
        if len(candidate) < 2:
            continue
        match = re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", source_text, re.IGNORECASE)
        if match is None:
            continue
        original = source_text[match.start():match.end()].strip()
        key = original.casefold()
        if key and key not in seen:
            seen.add(key)
            output.append(original)

    return tuple(output)


def _safe_importance(value: object) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score))


SYSTEM_PROMPT = """You are the campaign-event extractor for a Dungeons & Dragons timeline.
Decide whether the supplied transcript describes a MAIN IN-WORLD EVENT worth remembering.

KEEP events that change campaign state, including: travel/arrival/departure; combat start/result; danger/traps; discoveries/clues/secrets/lore; quest acceptance/progress/failure/completion; important items gained/lost/used; important NPC information, promises, threats or deals; major decisions that are committed to; rest/recovery; character injury/death/rescue/status changes; puzzles solved/failed; faction/relationship/world-state changes; important trade/rewards/resources; major magic/environment changes.

REJECT: jokes, laughter, banter, greetings, filler, repeated statements, real-life discussion, food/phone/work talk, technical/audio discussion, pure rules/mechanics talk with no in-world consequence, hypothetical plans not acted upon, trivial dialogue, and ordinary conversation that reveals nothing important.

Dialogue is a timeline event ONLY when the conversation itself creates an important story change or reveals information the party should remember.

Extract locations and temporal expressions automatically from meaning/context. Fantasy names are valid locations. Return ONLY exact text spans that appear in the transcript; never invent a place or time. If none is explicitly stated, use an empty list.

Return JSON only with this schema:
{"keep":true,"occurred":true,"importance":0.0,"category":"travel|combat|dialogue|discovery|rest|quest|item|other","evidence":"complete exact transcript sentence","locations":[],"temporal_entities":[],"reason":"short reason"}

Evidence must describe the actual event, including its subject, action and any qualifiers.
Copy a complete sentence exactly; do not remove negation, conditions or intentions.
Set occurred to true ONLY when the evidence establishes an actual in-world event.
An item mention is not an acquisition. "I am going to take all three attacks at
Great Weapon Master at him" is mechanics/intent, not obtaining an item.
If no suitable evidence exists, set keep and occurred to false. The evidence itself
will supply the title (long evidence is displayed as an excerpt); do not generate
a paraphrase or invented outcome. Evidence length does not determine event validity.

Use importance >= 0.55 only for events that genuinely deserve a timeline entry. If keep is false, evidence/locations/temporal_entities may be empty."""


@lru_cache(maxsize=512)
def analyze_timeline_event(text: str, speakers_key: str = "") -> TimelineAIAnalysis | None:
    if not TIMELINE_AI_ENABLED:
        return None

    cleaned = " ".join(text.split()).strip()
    if not cleaned:
        return None

    user_prompt = f"Speakers: {speakers_key or 'unknown'}\nTranscript: {cleaned}"

    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.0,
        },
    }

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json=payload,
            timeout=TIMELINE_AI_TIMEOUT,
        )
        response.raise_for_status()
        response_data = response.json()
        content = response_data.get("message", {}).get("content", "")
        data = _extract_json_object(content)
        if not data:
            return None
    except (requests.RequestException, ValueError, TypeError):
        return None

    return _validate_analysis(cleaned, data)


def _validate_analysis(cleaned: str, data: dict) -> TimelineAIAnalysis:
    keep = data.get("keep") is True and data.get("occurred") is True
    importance = _safe_importance(data.get("importance"))
    category = str(data.get("category", "other")).strip().lower()
    if category not in VALID_CATEGORIES:
        category = "other"

    # The keep flag and minimum importance jointly prevent chatty output.
    keep = keep and importance >= 0.55

    raw_evidence = data.get("evidence")
    evidence = _grounded_evidence(cleaned, raw_evidence)
    title = grounded_event_title(cleaned, category, evidence) if evidence else None
    keep = keep and evidence is not None
    # Exact quotation alone cannot turn mechanics or an item mention into
    # an item event, even if the model incorrectly confirms occurrence.
    if keep and category == "item":
        keep = bool(item_event_sentences(evidence))
    if keep and category == "travel":
        keep = travel_evidence_allowed(evidence)
    if keep and category == "discovery":
        keep = not evidence.endswith("?")

    reason = data.get("reason")
    if isinstance(reason, str):
        reason = " ".join(reason.split()).strip()[:240] or None
    else:
        reason = None

    return TimelineAIAnalysis(
        keep=keep,
        importance=importance,
        category=category,
        title=title,
        locations=_exact_spans(
            data.get("locations"),
            travel_location_evidence(evidence) if evidence and category == "travel" else evidence or "",
        ),
        temporal_entities=_exact_spans(data.get("temporal_entities"), cleaned),
        reason=reason,
        evidence=evidence,
    )


logger = logging.getLogger(__name__)
TIMELINE_AI_BATCH_SIZE = 3
TIMELINE_AI_BATCH_CHARS = 3000
TIMELINE_AI_CONTEXT_CHARS = 240
TIMELINE_AI_OUTPUT_TOKENS = 384

BATCH_SYSTEM_PROMPT = """For each input candidate, identify its main completed D&D event.
Return JSON {"results":[{"id":42,"evidence":3,"category":"travel","locations":["Stonebridge"],
"temporal_entities":["at noon"]}]} with one result per candidate. Copy each id.
Evidence is the key of the sentence in CURRENT transcript that proves the event happened.
Use evidence -1 and category other for chatter, plans, negations or mechanics such as Great Weapon Master.
Use PREVIOUS and FOLLOWING only as context. Copy places from the selected sentence
and times from CURRENT transcript."""


def _batch_response_format(batch: list[dict]) -> dict:
    string_array = {"type": "array", "items": {"type": "string"}}
    return {
        "type": "object",
        "required": ["results"],
        "properties": {
            "results": {
                "type": "array", "minItems": len(batch), "maxItems": len(batch),
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["id", "category", "evidence", "locations", "temporal_entities"],
                    "properties": {
                        "id": {"type": "integer", "enum": [item["id"] for item in batch]},
                        "category": {"enum": sorted(VALID_CATEGORIES)},
                        "evidence": {"type": "integer", "minimum": -1},
                        "locations": string_array,
                        "temporal_entities": string_array,
                    },
                },
            },
        },
    }


def analyze_timeline_events(
    candidates: list[tuple[str, str]],
    *,
    contexts: list[tuple[str, str, str]] | None = None,
) -> list[TimelineAIAnalysis | None]:
    """Validate bounded batches against each candidate's own source.

    None selects local fallback. Missing/duplicate IDs never shift results.
    Transport failures stop AI work for this run. Oversized candidates use
    local fallback rather than truncating evidence.

    Previous/following groups help resolve the current transcript's meaning.
    They never supply evidence or entities to its validator. Context is bounded
    and included in the batch size limit; the current source stays complete.
    """
    if contexts is not None and len(contexts) != len(candidates):
        raise ValueError("Each candidate must have exactly one context tuple")
    results: list[TimelineAIAnalysis | None] = [None] * len(candidates)
    if not TIMELINE_AI_ENABLED:
        return results
    batches: list[list[dict]] = []
    batch: list[dict] = []
    size = 2  # JSON array brackets
    for index, (text, speakers) in enumerate(candidates):
        cleaned = " ".join(text.split()).strip()
        item = dict(id=index, transcript=dict(enumerate(transcript_sentences(cleaned))), speakers=speakers)
        if contexts is not None:
            previous, _, following = contexts[index]
            item["previous"] = " ".join(previous.split())[-TIMELINE_AI_CONTEXT_CHARS:]
            item["following"] = " ".join(following.split())[:TIMELINE_AI_CONTEXT_CHARS]
        item_size = len(json.dumps(item, separators=(",", ":")))
        if not cleaned or item_size + 2 > TIMELINE_AI_BATCH_CHARS:
            continue
        if batch and (len(batch) >= TIMELINE_AI_BATCH_SIZE
                      or size + 1 + item_size > TIMELINE_AI_BATCH_CHARS):
            batches.append(batch)
            batch, size = [], 2
        size += item_size + (1 if batch else 0)
        batch.append(item)
    if batch:
        batches.append(batch)

    for number, batch in enumerate(batches, 1):
        prompt = json.dumps(batch, separators=(",", ":"))
        started = perf_counter()
        try:
            response = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": settings.llm_model,
                    "messages": [
                        {"role": "system", "content": BATCH_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False, "format": _batch_response_format(batch),
                    "options": {"temperature": 0.0, "num_predict": TIMELINE_AI_OUTPUT_TOKENS},
                },
                timeout=TIMELINE_AI_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            logger.warning(
                "Timeline AI batch %d/%d failed after %.2fs; using local fallback for remaining candidates: %s",
                number, len(batches), perf_counter() - started, error,
            )
            break
        try:
            reply = response.json()
            content = reply["message"]["content"]
            logger.info(
                "Timeline AI batch %d/%d (%d candidates, %d chars) took %.2fs "
                "(load/prompt/generation ns: %s/%s/%s, output tokens: %s)",
                number, len(batches), len(batch), len(prompt), perf_counter() - started,
                reply.get("load_duration"), reply.get("prompt_eval_duration"),
                reply.get("eval_duration"), reply.get("eval_count"),
            )
            data = _extract_json_object(content) if isinstance(content, str) else None
            rows = data.get("results") if data else None
            if not isinstance(rows, list):
                raise ValueError("missing results list")
        except (ValueError, TypeError, KeyError):
            logger.warning("Timeline AI batch %d malformed; using local fallback", number)
            continue
        by_id: dict[int, list[dict]] = {}
        for row in rows:
            if isinstance(row, dict) and type(row.get("id")) is int:
                by_id.setdefault(row["id"], []).append(row)
        for item in batch:
            matches = by_id.get(item["id"], [])
            if len(matches) == 1:
                row = matches[0]
                evidence = row.get("evidence")
                sentences = item["transcript"]
                if type(evidence) is int:
                    if evidence != -1 and evidence not in sentences:
                        continue
                    row = {"keep": evidence != -1, "occurred": evidence != -1, "importance": 1.0,
                           **row, "evidence": sentences.get(evidence)}
                analysis = _validate_analysis(" ".join(sentences.values()), row)
                if row.get("keep") is True and row.get("occurred") is True and not analysis.evidence:
                    continue
                results[item["id"]] = analysis
    return results
