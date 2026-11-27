import json

from test_pipeline import NOW, TOPOLOGY, network_outage_in_carlton, power_outage_on

from engine.contracts import Action, Cause
from engine.evidence import to_verdict
from engine.pipeline import assess
from engine.summary import build_prompt, summarise, template_summary


def verdict_for(events, **kwargs):
    [a] = assess(events, TOPOLOGY, NOW, **kwargs)
    return to_verdict("inc-0001", a.cluster, a.clues, a.result, a.decision, NOW)


POWER = verdict_for(power_outage_on("T5"))
NETWORK = verdict_for(network_outage_in_carlton(), outage_suburbs={"Carlton"})
UNSURE = verdict_for(network_outage_in_carlton(), outage_suburbs=set())


def test_template_says_what_happened_and_what_is_being_done():
    result = template_summary(POWER)
    assert result.source == "template"
    assert result.summary == (
        "20 meters went silent. The most likely cause is a power outage (90% confidence). "
        "A power crew has been sent."
    )
    assert "crew is on the way" in result.notice


def test_customers_only_get_a_notice_for_a_power_outage():
    assert template_summary(NETWORK).notice == ""
    assert "Telstra mobile network outage" in template_summary(NETWORK).summary
    assert UNSURE.action is Action.MANUAL_REVIEW
    assert "operator needs to review" in template_summary(UNSURE).summary


def test_without_a_generator_the_template_is_used():
    assert summarise(POWER) == template_summary(POWER)


def test_prompt_states_the_decision_as_final_and_lists_the_evidence():
    prompt = build_prompt(POWER)
    assert "Its decision is final" in prompt
    assert "- Cause: POWER" in prompt
    assert "- Action: DISPATCH_POWER_CREW" in prompt
    for line in POWER.evidence:
        assert f"- {line}" in prompt


def test_gemini_reply_is_used_when_it_is_valid_json():
    def fake(prompt: str) -> str:
        reply = {"summary": "Twenty meters on T5 lost power at once.", "notice": "Crew coming."}
        return "```json\n" + json.dumps(reply) + "\n```"  # models often wrap JSON like this

    result = summarise(POWER, fake)
    assert result.source == "gemini"
    assert result.summary == "Twenty meters on T5 lost power at once."
    assert result.notice == "Crew coming."


def test_any_failure_falls_back_to_the_template():
    def crashes(prompt: str) -> str:
        raise TimeoutError("Vertex AI did not answer")

    for bad in (crashes, lambda p: "Sorry, I cannot help.", lambda p: '{"summary": ""}',
                lambda p: '{"notice": "x"}', lambda p: '{"summary": 5}'):  # fmt: skip
        assert summarise(POWER, bad) == template_summary(POWER)


def test_the_llm_cannot_change_the_verdict():
    def argues(prompt: str) -> str:
        return json.dumps({"summary": "Actually this is a NETWORK outage.", "notice": ""})

    before = POWER.model_copy(deep=True)
    summarise(POWER, argues)
    assert before == POWER
    assert POWER.cause is Cause.POWER and POWER.action is Action.DISPATCH_POWER_CREW
