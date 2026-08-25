from __future__ import annotations

from dataclasses import dataclass
import unicodedata
import re


SOURCE_KINDS = (
    "official_federation",
    "official_circuit",
    "registration_platform",
    "timing_platform",
    "specialized_calendar",
)


@dataclass(frozen=True)
class CompetitionSource:
    domain: str
    kind: str
    categories: tuple[str, ...]
    countries: tuple[str, ...] = ("ES",)
    regions: tuple[str, ...] = ()
    priority: int = 50
    @property
    def label(self) -> str:
        return self.domain


DEFAULT_COMPETITION_SOURCES = (
    CompetitionSource("triatlon.org", "official_federation", ("triathlon", "duathlon", "aquathlon"), priority=100),
    CompetitionSource("faclm.com", "official_federation", ("running",), regions=("castilla-la mancha",), priority=100),
    CompetitionSource("yosoyciclista.com", "official_federation", ("cycling",), regions=("castilla-la mancha",), priority=100),
    CompetitionSource("carrerasclm.es", "specialized_calendar", ("running",), regions=("castilla-la mancha",), priority=70),
    CompetitionSource("rockthesport.com", "registration_platform", ("running", "cycling", "swimming", "triathlon", "duathlon", "aquathlon"), priority=60),
    CompetitionSource("conxip.com", "timing_platform", ("running", "cycling", "swimming", "triathlon", "duathlon", "aquathlon"), priority=60),
)


class TrustedCompetitionSources:
    def __init__(self, sources=DEFAULT_COMPETITION_SOURCES):
        self.sources = tuple(sources)
        domains = [source.domain for source in self.sources]
        if len(domains) != len(set(domains)):
            raise ValueError("competition source domains must be unique")
        if any(source.kind not in SOURCE_KINDS for source in self.sources):
            raise ValueError("unsupported competition source kind")

    def select(self, category: str | None, location: str | None) -> tuple[CompetitionSource, ...]:
        folded_location = self._fold(location or "")
        selected = []
        for source in self.sources:
            if category and category not in source.categories:
                continue
            if source.regions and not any(self._fold(region) in folded_location for region in source.regions):
                continue
            selected.append(source)
        return tuple(sorted(selected, key=lambda source: (-source.priority, source.domain)))

    def domains(self, category: str | None, location: str | None) -> list[str]:
        return [source.domain for source in self.select(category, location)]

    def source_for_url(self, url: str) -> CompetitionSource | None:
        from urllib.parse import urlsplit

        host = (urlsplit(url).hostname or "").casefold().removeprefix("www.")
        matches = [source for source in self.sources if host == source.domain or host.endswith("." + source.domain)]
        return max(matches, key=lambda source: source.priority, default=None)

    @staticmethod
    def _fold(value: str) -> str:
        folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
        return re.sub(r"\W+", " ", folded).strip()
