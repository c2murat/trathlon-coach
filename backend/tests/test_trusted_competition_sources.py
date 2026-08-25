import pytest

from app.integrations.competition_catalog.trusted_sources import CompetitionSource, TrustedCompetitionSources


def test_clm_running_selects_regional_and_national_sources_in_priority_order():
    registry = TrustedCompetitionSources()
    assert registry.domains("running", "Castilla-La Mancha") == ["faclm.com", "carrerasclm.es", "conxip.com", "rockthesport.com"]


def test_general_search_uses_only_national_sources_and_category_filters():
    registry = TrustedCompetitionSources()
    assert registry.domains("running", None) == ["conxip.com", "rockthesport.com"]
    assert registry.domains("cycling", "España") == ["conxip.com", "rockthesport.com"]
    assert registry.domains("triathlon", "España") == ["triatlon.org", "conxip.com", "rockthesport.com"]


def test_regional_selection_is_normalized_and_does_not_leak_other_sports():
    registry = TrustedCompetitionSources()
    assert "carrerasclm.es" in registry.domains("running", "castilla la mancha")
    assert "carrerasclm.es" not in registry.domains("duathlon", "Castilla-La Mancha")
    assert "yosoyciclista.com" in registry.domains("cycling", "CASTILLA-LA MANCHA")


def test_registry_is_extensible_and_rejects_duplicate_domains():
    added = CompetitionSource("events.example", "specialized_calendar", ("running",), regions=("Madrid",), priority=80)
    registry = TrustedCompetitionSources((added,))
    assert registry.domains("running", "Madrid") == ["events.example"]
    with pytest.raises(ValueError, match="unique"):
        TrustedCompetitionSources((added, added))
