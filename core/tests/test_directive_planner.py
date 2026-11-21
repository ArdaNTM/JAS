from aura_core.application.directive_planner import DirectivePlanner
from aura_core.kernel.permissions import RiskLevel


def test_research_directive_generates_governed_search_plan():
    plan = DirectivePlanner().plan(
        "Yapay zeka hakkında araştırma yap."
    )

    assert plan.resource_scope == "public-web"
    assert len(plan.steps) == 1

    step = plan.steps[0]

    assert step.capability_id == "internet.search"
    assert step.operation_id == "internet.search"
    assert step.tool_name == "search"
    assert step.risk_level is RiskLevel.LOW
    assert step.arguments["query"] == (
        "Yapay zeka hakkında araştırma yap."
    )


def test_empty_directive_is_rejected():
    try:
        DirectivePlanner().plan(" ")
    except ValueError as exc:
        assert "Directive is required" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_unknown_directive_is_rejected():
    try:
        DirectivePlanner().plan("Kahvemi hazırla.")
    except ValueError as exc:
        assert "No governed capability" in str(exc)
    else:
        raise AssertionError("Expected ValueError")

def test_conversational_voice_request_routes_to_non_executable_assistant():
    for phrase in ("AURA tell me a short joke.", "Tell me a short joke",
                   "AURA, explain why the sky is blue", "Merhaba AURA"):
        plan = DirectivePlanner().plan(phrase)
        assert plan.resource_scope == "local-assistant"
        assert plan.steps == ()


def test_instructions_to_operate_computer_are_not_conversation_tools():
    for phrase in ("AURA delete the backups", "Run arbitrary Python",
                   "Kahvemi hazırla."):
        try:
            DirectivePlanner().plan(phrase)
        except ValueError as exc:
            assert "No governed capability" in str(exc)
        else:
            raise AssertionError("Unsupported commands must fail closed")


def test_capability_questions_are_conversation_not_synthesize_or_search():
    for text in (
        "Neler yapabilirsin?", "Hangi araçların var?", "Hangi yeteneklerin var?",
        "Which features do you have?", "What can you do?", "Bana kendini tanıt",
        "Sohbet etmek ister misin?",
    ):
        result = DirectivePlanner().plan(text)
        assert result.resource_scope == "local-assistant"
        assert result.steps == ()


def test_questions_do_not_implicitly_authorize_tools():
    plan = DirectivePlanner().plan("Bilgisayarımı silebilir misin?")
    assert plan.resource_scope == "local-assistant"
    assert plan.steps == ()


def test_discovery_directives_are_explicit_and_never_research_tasks():
    for phrase in (
        "Kendini geliştir",
        "Yeni ücretsiz özellikler araştır",
        "GitHub'dan kendine katabileceğin araçlar bul",
    ):
        plan = DirectivePlanner().plan(phrase)
        assert plan.resource_scope == "local-discovery"
        assert plan.steps == ()


def test_explicit_inflected_turkish_research_still_routes_to_gateway():
    phrase = "Bana yapay zeka alanında bu haftanın en son gelişmelerini araştırıp özetler misin?"
    plan = DirectivePlanner().plan(phrase)
    assert plan.resource_scope == "public-web"
    assert plan.steps[0].capability_id == "internet.search"


def test_compound_turkish_discovery_intents_never_trigger_general_research():
    variants = (
        "Kendini geliştir, GitHub'dan ücretsiz özellikler araştır",
        "KENDİNİ GELİŞTİR",
        "KENDİNİ GELİŞTİR, GitHub’dan ücretsiz özellikler araştır",
        "kendini gelistir",
        "ÖZELLİK ARAŞTIR",
        "ozellik arastir",
        "yetenek araştır",
        "yetenek keşfet",
        "Github'dan",
        "githubdan",
        "yeni araç bul",
        "mcp araştır",
        "self discovery",
        "İSTİYORUM: Github'dan AURA'ya yeni araç bul!",
        "Lütfen yeni ücretsiz özellikler araştır",
    )
    from aura_core.application.directive_planner import is_self_discovery_intent
    for message in variants:
        assert is_self_discovery_intent(message), message
        plan = DirectivePlanner().plan(message)
        assert plan.resource_scope == "local-discovery", message
        assert not plan.steps


def test_unrelated_github_substrings_not_automatically_discovery():
    from aura_core.application.directive_planner import is_self_discovery_intent
    for message in ("githubdashboard", "superself discoverytool", "aracbulucu"):
        assert not is_self_discovery_intent(message)
