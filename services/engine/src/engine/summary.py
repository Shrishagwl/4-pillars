"""Optional: Gemini turns a verdict into a plain-English summary and a draft customer notice.

The LLM is only a writer. The cause, the confidence and the action are already decided by the
engine before this runs, and nothing here can change them: the function takes a finished
Verdict and returns text. If Gemini is switched off, not installed, slow or returns something
we cannot read, we fall back to a fixed template, so the dashboard card always has a summary.

To use Gemini: `uv sync --extra llm`, then set LLM_SUMMARY=true and GCP_PROJECT.
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass

from .config import Settings
from .contracts import Action, Cause, Verdict

log = logging.getLogger(__name__)

# Takes a prompt, returns the model's text. Lets tests pass in a fake instead of calling Google.
Generate = Callable[[str], str]

CAUSE_WORDS = {
    Cause.POWER: "a power outage",
    Cause.NETWORK: "a Telstra mobile network outage",
    Cause.METER_FAULT: "a faulty meter",
    Cause.TAMPER: "possible tampering with a meter",
}
ACTION_WORDS = {
    Action.DISPATCH_POWER_CREW: "A power crew has been sent.",
    Action.WAIT_FOR_NETWORK: "No one has been sent; the meters should reconnect when the "
    "network is back.",
    Action.DISPATCH_METER_TECH: "A meter technician has been sent.",
    Action.INVESTIGATE_TAMPER: "The meter has been flagged for a tamper investigation.",
    Action.MANUAL_REVIEW: "The engine is not sure enough to act, so an operator needs to "
    "review it.",
}


@dataclass(frozen=True, slots=True)
class IncidentSummary:
    summary: str  # for the operator, on the verdict card
    notice: str  # draft message for affected customers; empty when none should be sent
    source: str  # "gemini" or "template"


def template_summary(verdict: Verdict) -> IncidentSummary:
    meters = f"{verdict.meterCount} meter" + ("s" if verdict.meterCount != 1 else "")
    summary = (
        f"{meters} went silent. The most likely cause is {CAUSE_WORDS[verdict.cause]} "
        f"({verdict.confidence:.0%} confidence). {ACTION_WORDS[verdict.action]}"
    )
    notice = ""
    if verdict.cause is Cause.POWER and verdict.action is Action.DISPATCH_POWER_CREW:
        notice = (
            "We are aware of a power outage in your area and a crew is on the way. "
            "We will update you when power is restored."
        )
    return IncidentSummary(summary, notice, "template")


def build_prompt(verdict: Verdict) -> str:
    evidence = "\n".join(f"- {line}" for line in verdict.evidence)
    return f"""You write short incident notes for an electricity distributor's control room.

A monitoring engine has already analysed a group of smart meters that stopped reporting.
Its decision is final. Do not question it, change it, or suggest a different cause or action.

Decision:
- Cause: {verdict.cause} ({CAUSE_WORDS[verdict.cause]})
- Confidence: {verdict.confidence:.0%}
- Action: {verdict.action}
- Meters affected: {verdict.meterCount}

Evidence the engine used:
{evidence}

Write two things, using only the facts above:
1. "summary": two or three plain sentences for the control-room operator saying what
   happened, why the engine thinks so, and what is being done.
2. "notice": one or two sentences for affected customers. Use an empty string unless the
   cause is POWER, because customers do not need a message about the other causes.

Reply with JSON only, in this shape: {{"summary": "...", "notice": "..."}}"""


def _parse(text: str) -> tuple[str, str]:
    """Pull summary and notice out of the model's reply. Raises if it is not what we asked for."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in the reply")
    data = json.loads(text[start : end + 1])
    summary, notice = data["summary"], data.get("notice", "")
    if not isinstance(summary, str) or not isinstance(notice, str) or not summary.strip():
        raise ValueError("summary or notice is missing or not text")
    return summary.strip(), notice.strip()


def summarise(verdict: Verdict, generate: Generate | None = None) -> IncidentSummary:
    """Summary for one verdict. Uses `generate` when given, the template otherwise."""
    if generate is None:
        return template_summary(verdict)
    try:
        summary, notice = _parse(generate(build_prompt(verdict)))
    except Exception:  # noqa: BLE001  (any failure at all means: use the template)
        log.warning("LLM summary failed, using the template", exc_info=True)
        return template_summary(verdict)
    return IncidentSummary(summary, notice, "gemini")


def with_summary(verdict: Verdict, generate: Generate | None = None) -> Verdict:
    """The same verdict with `summary` and `notice` filled in, ready for the dashboard card.

    Only those two fields change. Cause, confidence, action and evidence are copied as they are.
    """
    written = summarise(verdict, generate)
    return verdict.model_copy(update={"summary": written.summary, "notice": written.notice})


def generator_from_settings(settings: Settings) -> Generate | None:
    """Gemini if it is switched on and set up, otherwise None (which means: use the template)."""
    if not settings.llm_summary:
        return None
    if not settings.gcp_project:
        log.warning("LLM_SUMMARY is on but GCP_PROJECT is empty, using the template")
        return None
    try:
        return gemini_generator(settings.gcp_project, settings.gcp_location, settings.gemini_model)
    except Exception:  # noqa: BLE001  (package missing or no credentials: use the template)
        log.warning("could not start Gemini, using the template", exc_info=True)
        return None


def gemini_generator(project: str, location: str, model: str) -> Generate:
    """A `generate` function that calls Gemini on Vertex AI.

    Needs the optional dependency (`uv sync --extra llm`) and Google Cloud credentials. On
    Cloud Run the service account provides them; locally run `gcloud auth application-default
    login`.
    """
    from google import genai  # imported here so the engine runs without the package

    client = genai.Client(vertexai=True, project=project, location=location)

    def generate(prompt: str) -> str:
        response = client.models.generate_content(model=model, contents=prompt)
        return response.text or ""

    return generate
