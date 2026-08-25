from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime, timezone
from time import monotonic
from urllib.parse import urlsplit, urlunsplit

from pydantic import ValidationError
from tavily import TavilyClient

from app.domains.competition_catalog.geography import default_competition_geography
from app.domains.competition_catalog.models import CatalogError, CatalogEvent, CatalogSearch, WebCompetitionSearchResult
from app.integrations.competition_catalog.trusted_sources import TrustedCompetitionSources


_CATEGORIES = ("running", "cycling", "swimming", "triathlon", "duathlon", "aquathlon")
_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_MONTH_NAMES = {value: key for key, value in _MONTHS.items() if key != "setiembre"}
_CATEGORY_TERMS = (
    ("duathlon", ("duatlon", "duathlon")),
    ("aquathlon", ("acuatlon", "aquathlon")),
    ("triathlon", ("triatlon", "triathlon")),
    ("swimming", ("natacion", "swimming", "travesia a nado")),
    ("cycling", ("ciclismo", "cycling", "cicloturista")),
    ("running", ("carrera", "running", "10k", "media maraton", "maraton", "race")),
)
_COMPETITION_TERMS = (
    "carrera", "competicion", "prueba", "inscripcion", "calendario", "triatlon",
    "duatlon", "acuatlon", "maraton", "travesia a nado", "cicloturista", "race",
    "triathlon", "duathlon", "aquathlon", "championship",
)
_AGGREGATE_TITLE_TERMS = (
    "listado", "calendario", "agenda", "directorio", "recopilacion", "resultados",
    "buscador de eventos", "proximos eventos", "eventos deportivos", "carreras 2026",
    "event listing", "events listing", "events calendar", "race calendar",
    "upcoming events", "sports events", "event directory", "event finder", "search results",
)
_AGGREGATE_CONTENT_PHRASES = (
    "listado de eventos", "listado de carreras", "calendario de carreras",
    "calendario de eventos", "agenda deportiva", "buscador de eventos",
    "proximos eventos", "event listing", "events calendar", "race calendar",
    "upcoming events", "event directory", "event finder",
)
_GENERIC_NAME_TOKENS = {
    "listado", "calendario", "agenda", "directorio", "recopilacion", "resultados",
    "proximos", "eventos", "evento", "deportivos", "deportivo", "carreras", "carrera",
    "popular", "populares", "competicion", "prueba", "inscripcion", "search", "results",
    "upcoming", "events", "event", "sports", "calendar", "listing", "directory", "finder",
    "race", "running", "run", "de", "del", "la", "el", "y", "en", "the", "of",
}
_SOCIAL_DOMAINS = ("instagram.com", "facebook.com", "tiktok.com", "x.com", "twitter.com", "threads.net", "pinterest.com")
_CAPTION_TITLE_TERMS = ("un ano mas", "nos ponemos en la linea de salida", "save the date", "we are back")
_SOURCE_KIND = {
    "official_federation": "official",
    "official_circuit": "official",
    "registration_platform": "registration",
    "timing_platform": "timing",
    "specialized_calendar": "specialized_calendar",
}
_SPORT_TERMS = {
    "swim": ("natacion", "nado", "swim", "swimming"),
    "bike": ("ciclismo", "bicicleta", "bike", "cycling"),
    "run": ("carrera", "correr", "run", "running"),
}
_CACHE_TTL_SECONDS = 15 * 60
_CACHE_MAX_EVENTS = 200
_CACHE: dict[str, tuple[float, CatalogEvent]] = {}
_WEB_SEARCH_CACHE: dict[str, tuple[float, list[tuple[float, WebCompetitionSearchResult]]]] = {}


class TavilyCompetitionProvider:
    name = "tavily"
    label = "Búsqueda web · Tavily"
    supported_categories = _CATEGORIES
    search_mode = "web"
    supports_structured_detail = False
    supports_structured_import = False
    supports_search_to_manual_goal = True

    def __init__(
        self,
        api_key: str | None,
        search_depth: str = "basic",
        timeout: float = 15,
        max_results: int = 10,
        use_extract: bool = True,
        client=None,
        cache=None,
        sources=None,
        geography=None,
        web_search_cache=None,
    ):
        self.api_key = api_key
        self.search_depth = search_depth
        self.timeout = timeout
        self.max_results = max_results
        self.use_extract = use_extract
        self.client = client
        self.cache = _CACHE if cache is None else cache
        self.sources = sources or TrustedCompetitionSources()
        self.geography = geography or default_competition_geography()
        self.web_search_cache = _WEB_SEARCH_CACHE if web_search_cache is None else web_search_cache

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def search(self, query: CatalogSearch) -> list[CatalogEvent]:
        raise CatalogError("provider_search_mode_invalid")

    def search_web(self, query: CatalogSearch, phase: str = "initial"):
        client = self._client()
        limit = min(query.limit, self.max_results)
        trusted_domains = self.sources.domains(query.category, query.location)
        if phase == "initial" and trusted_domains:
            rows = self._search_rows(client, query, limit, include_domains=trusted_domains)
        else:
            excluded = list(_SOCIAL_DOMAINS) + (trusted_domains if phase == "more" else [])
            rows = self._search_rows(client, query, limit, exclude_domains=excluded)
        scored = [value for row in rows if (value := self._web_result(row, query)) is not None]
        cache_key = self._web_cache_key(query)
        self._expire_web_cache()
        if phase == "initial":
            self.web_search_cache[cache_key] = (monotonic(), scored)
        else:
            scored = self.web_search_cache.pop(cache_key, (0.0, []))[1] + scored
        results = [item for _, item in self._deduplicate_web(scored)]
        # Tavily has no page/offset. The initial trusted search always offers one
        # explicit general-web expansion; the second phase is terminal.
        return results[: limit if phase == "initial" else limit * 2], phase == "initial"

    def _web_result(self, row, query):
        if not isinstance(row, dict) or not isinstance(row.get("title"), str):return None
        try: url=self.canonical_url(row.get("url", ""))
        except ValueError:return None
        if self._is_social_url(url) or self._is_results_url(url):return None
        title=row["title"].strip();content=row.get("content") if isinstance(row.get("content"),str) else ""
        if self._title_temporally_contradicts(title, query):return None
        folded=self._fold(f"{title} {content}")
        if not any(term in folded for term in _COMPETITION_TERMS):return None
        listing=self._is_aggregate_page(title,content)
        coherent=not listing and self._snippet_is_coherent(title,content)
        hint_text=title if not coherent else f"{title} {content}"
        hint_date=self.extract_date(hint_text)
        if hint_date and ((query.start_date and hint_date < query.start_date) or (query.end_date and hint_date > query.end_date)):return None
        category=None if listing else self.extract_category(self._fold(hint_text))
        source=self.sources.source_for_url(url);domain=(urlsplit(url).hostname or "").removeprefix("www.")
        distance=None if listing else re.search(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(km|k|m)\b",self._fold(hint_text))
        normalized_title=self._fold(title)
        location=None if listing or not coherent else self.geography.primary_location(hint_text)
        result=WebCompetitionSearchResult(id=hashlib.sha256(url.encode()).hexdigest(),title=title,url=url,snippet=re.sub(r"\s+"," ",content).strip()[:500],source_domain=domain,source_label=source.label if source else domain,source_kind=source.kind if source else "web",result_kind="event_listing" if listing else "event_candidate",hints={"possible_date":None if listing else hint_date,"possible_location":location.name if location else None,"possible_category":category,"possible_distance":distance.group(0) if distance else None})
        score=float(row.get("score",0) or 0)+self._source_priority(url)/100
        query_text=self._fold(query.text or "").strip()
        if query_text:
            if normalized_title==query_text:score+=10
            elif normalized_title.startswith(query_text):score+=7
            elif query_text in normalized_title:score+=5
            else:score+=2*len(set(query_text.split())&set(normalized_title.split()))/max(1,len(set(query_text.split())))
        if query.category and category==query.category:score+=2
        territorial_score = self.geography.territorial_score(query.location, title, content if coherent else "")
        score += territorial_score
        if query.location and self.geography.resolve_location_scope(query.location) is None and self._fold(query.location) in folded:
            score += 2
        return score,result

    @classmethod
    def _title_temporally_contradicts(cls, title: str, query: CatalogSearch) -> bool:
        if not query.start_date and not query.end_date:
            return False
        title_dates = {value for value, _, _ in cls._date_matches(title)}
        if len(title_dates) == 1:
            value = next(iter(title_dates))
            if (query.start_date and value < query.start_date) or (query.end_date and value > query.end_date):
                return True
        years = {int(value) for value in re.findall(r"(?<!\d)(20\d{2})(?!\d)", title)}
        minimum = query.start_date.year if query.start_date else 1
        maximum = query.end_date.year if query.end_date else 9999
        return bool(years) and not any(minimum <= year <= maximum for year in years)

    @classmethod
    def _snippet_is_coherent(cls, title: str, content: str) -> bool:
        if not content.strip() or cls._snippet_is_multi_event(content):
            return False
        title_tokens = cls._specific_name_tokens(title)
        content_tokens = set(re.findall(r"[a-z0-9]+", cls._fold(content)))
        return bool(title_tokens & content_tokens)

    @classmethod
    def _snippet_is_multi_event(cls, content: str) -> bool:
        folded = cls._fold(content)
        if any(term in folded for term in (*_AGGREGATE_CONTENT_PHRASES, "otros eventos", "eventos relacionados", "related events")):
            return True
        if len({value for value, _, _ in cls._date_matches(content)}) > 1:
            return True
        return len(re.findall(r"(?:\||•|·|\s[-–—]\s)", content)) >= 4 and sum(folded.count(term) for term in _COMPETITION_TERMS) >= 3

    @staticmethod
    def _deduplicate_web(scored):
        selected={};aliases=set()
        for score,item in sorted(scored,key=lambda value:-value[0]):
            alias=(TavilyCompetitionProvider._fold(item.title),item.source_domain)
            if item.url in selected or alias in aliases:continue
            selected[item.url]=(score,item);aliases.add(alias)
        return list(selected.values())

    @staticmethod
    def _web_cache_key(query: CatalogSearch) -> str:
        return hashlib.sha256(query.model_dump_json().encode()).hexdigest()

    def _expire_web_cache(self) -> None:
        expired = [key for key, (created, _) in self.web_search_cache.items() if monotonic() - created > _CACHE_TTL_SECONDS]
        for key in expired:
            self.web_search_cache.pop(key, None)
        while len(self.web_search_cache) > 200:
            self.web_search_cache.pop(next(iter(self.web_search_cache)))

    def _search_rows(self, client, query: CatalogSearch, limit: int, include_domains=None, exclude_domains=None):
        domain_filters = {}
        if include_domains:
            domain_filters["include_domains"] = include_domains
        if exclude_domains:
            domain_filters["exclude_domains"] = exclude_domains
        try:
            payload = client.search(
                query=self.build_query(query),
                search_depth=self.search_depth,
                max_results=limit,
                topic="general",
                include_answer=False,
                include_raw_content=False,
                timeout=self.timeout,
                **domain_filters,
            )
        except Exception as exc:
            self._raise_provider_error(exc)
        rows = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise CatalogError("provider_invalid_response")
        return rows

    def _normalize_rows(self, rows, query: CatalogSearch) -> list[CatalogEvent]:
        events = []
        for row in rows:
            event = self._normalize_result(row, query)
            if event is not None:
                self._remember(event)
                events.append(event)
        return events

    def detail(self, external_id: str) -> CatalogEvent:
        cached_entry = self.cache.get(external_id)
        if cached_entry is None:
            raise CatalogError("competition_not_found")
        cached_at, cached = cached_entry
        if monotonic() - cached_at > _CACHE_TTL_SECONDS:
            self.cache.pop(external_id, None)
            raise CatalogError("competition_not_found")
        if not self.use_extract:
            return cached
        client = self._client()
        try:
            payload = client.extract(
                urls=[cached.source_url],
                extract_depth="basic",
                format="text",
                timeout=self.timeout,
            )
        except Exception as exc:
            self._raise_provider_error(exc, extract=True)
        rows = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or not rows:
            raise CatalogError("provider_extract_failed")
        row = rows[0]
        if not isinstance(row, dict) or self.canonical_url(row.get("url", "")) != cached.source_url:
            raise CatalogError("provider_extract_failed")
        content = row.get("raw_content")
        if not isinstance(content, str) or not content.strip():
            raise CatalogError("provider_extract_failed")
        refreshed = self._event_from_text(cached.name, cached.source_url, content, cached.category)
        if refreshed is None or refreshed.start_date != cached.start_date or refreshed.external_id != external_id:
            raise CatalogError("provider_evidence_insufficient")
        self._remember(refreshed)
        return refreshed

    def _remember(self, event: CatalogEvent) -> None:
        self.cache[event.external_id] = (monotonic(), event)
        while len(self.cache) > _CACHE_MAX_EVENTS:
            self.cache.pop(next(iter(self.cache)))

    def _client(self):
        if not self.configured:
            raise CatalogError("provider_not_configured")
        return self.client or TavilyClient(api_key=self.api_key)

    @classmethod
    def build_query(cls, query: CatalogSearch) -> str:
        parts = [cls._query_text(query.text), cls._category_query(query.category), query.location]
        if query.start_date and query.end_date and query.start_date.year == query.end_date.year:
            parts.append(str(query.start_date.year))
            parts.extend(_MONTH_NAMES[month] for month in range(query.start_date.month, query.end_date.month + 1))
        else:
            if query.start_date:
                parts.append(query.start_date.isoformat())
            if query.end_date:
                parts.append(query.end_date.isoformat())
        parts.extend(("competición", "inscripción"))
        return " ".join(str(item).strip() for item in parts if item).strip()

    @staticmethod
    def _query_text(value: str | None) -> str | None:
        if not value:
            return value
        normalized = re.sub(r"(\d+(?:[.,]\d+)?)\s*km\b", r"\1 km", value, flags=re.IGNORECASE)
        return re.sub(r"(\d+(?:[.,]\d+)?)\s*k\b", r"\1 km", normalized, flags=re.IGNORECASE)

    @staticmethod
    def _category_query(category: str | None) -> str | None:
        return {
            "running": "carrera running", "cycling": "ciclismo", "swimming": "natación",
            "triathlon": "triatlón", "duathlon": "duatlón", "aquathlon": "acuatlón",
        }.get(category)

    def _normalize_result(self, row, query: CatalogSearch) -> CatalogEvent | None:
        if not isinstance(row, dict) or not isinstance(row.get("title"), str):
            return None
        try:
            source = self.canonical_url(row.get("url", ""))
        except ValueError:
            return None
        if self._is_social_url(source) or self._is_results_url(source):
            return None
        content = row.get("content") if isinstance(row.get("content"), str) else ""
        event = self._event_from_text(row["title"], source, content, query.category)
        if event is None:
            return None
        if query.start_date and event.start_date < query.start_date:
            return None
        if query.end_date and event.start_date > query.end_date:
            return None
        return event

    def _event_from_text(self, title: str, source: str, content: str, requested_category: str | None) -> CatalogEvent | None:
        text = f"{title}\n{content}"
        folded = self._fold(text)
        if self._is_aggregate_page(title, content) or not any(term in folded for term in _COMPETITION_TERMS):
            return None
        event_date = self._linked_event_date(title, content)
        category = self.extract_category(folded)
        if event_date is None or category is None or (requested_category and category != requested_category):
            return None
        segments = self.extract_segments(text, category)
        city, region = self.extract_location(text)
        external_id = self.external_id(source, event_date.isoformat(), title)
        source_info = self.sources.source_for_url(source)
        source_kind = _SOURCE_KIND.get(source_info.kind, "web") if source_info else "web"
        confidence = "high" if source_kind == "official" else "medium" if source_kind != "web" else "low"
        try:
            return CatalogEvent(
                provider=self.name,
                external_id=external_id,
                name=title.strip(),
                start_date=event_date,
                category=category,
                city=city,
                region=region,
                source_url=source,
                segments=segments,
                confidence=confidence,
                evidence=[{"url": source, "title": title.strip(), "official": source_kind == "official", "source_kind": source_kind}],
                retrieved_at=datetime.now(timezone.utc),
            )
        except ValidationError:
            return None

    @classmethod
    def _is_aggregate_page(cls, title: str, content: str) -> bool:
        folded_title = cls._fold(title)
        folded_content = cls._fold(content)
        if any(term in folded_title for term in (*_AGGREGATE_TITLE_TERMS, *_CAPTION_TITLE_TERMS)):
            return True
        if any(term in folded_content for term in _AGGREGATE_CONTENT_PHRASES):
            return True
        return len({value for value, _, _ in cls._date_matches(content)}) > 1

    def _deduplicate(self, events: list[CatalogEvent]) -> list[CatalogEvent]:
        selected = {}
        order = []
        for event in events:
            strong_location = self._fold(" ".join(filter(None, (event.city, event.region))))
            key = (self._fold(event.name), event.start_date, strong_location) if strong_location else (event.external_id,)
            existing = selected.get(key)
            if existing is None:
                selected[key] = event
                order.append(key)
            elif self._source_priority(event.source_url) > self._source_priority(existing.source_url):
                selected[key] = event
        return sorted((selected[key] for key in order), key=lambda event: -self._source_priority(event.source_url))

    def _source_priority(self, url: str | None) -> int:
        source = self.sources.source_for_url(url or "")
        return source.priority if source else 0

    @staticmethod
    def _is_social_url(url: str) -> bool:
        host = (urlsplit(url).hostname or "").casefold().removeprefix("www.")
        return any(host == domain or host.endswith("." + domain) for domain in _SOCIAL_DOMAINS)

    @staticmethod
    def _is_results_url(url: str) -> bool:
        path = urlsplit(url).path.casefold()
        return any(part in path for part in ("/resultados/", "/results/", "/clasificacion", "/classification"))

    @classmethod
    def _linked_event_date(cls, title: str, content: str) -> date | None:
        name_tokens = cls._specific_name_tokens(title)
        if not name_tokens:
            return None
        title_dates = cls._date_matches(title)
        if len({value for value, _, _ in title_dates}) == 1:
            return title_dates[0][0]
        content_dates = cls._date_matches(content)
        distinct = {value for value, _, _ in content_dates}
        if len(distinct) != 1:
            return None
        folded_content = cls._fold(content)
        for value, start, end in content_dates:
            nearby = folded_content[max(0, start - 180):min(len(folded_content), end + 180)]
            if any(re.search(r"\b" + re.escape(token) + r"\b", nearby) for token in name_tokens):
                return value
        return None

    @classmethod
    def _specific_name_tokens(cls, title: str) -> set[str]:
        tokens = set(re.findall(r"[a-z0-9]+", cls._fold(title)))
        return {token for token in tokens if len(token) >= 3 and token not in _GENERIC_NAME_TOKENS and not token.isdigit() and not re.fullmatch(r"\d+k", token)}

    @classmethod
    def _date_matches(cls, text: str) -> list[tuple[date, int, int]]:
        found = []
        for pattern, order in (
            (r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)", (1, 2, 3)),
            (r"(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?!\d)", (3, 2, 1)),
        ):
            for match in re.finditer(pattern, text):
                try:
                    found.append((date(*(int(match.group(index)) for index in order)), match.start(), match.end()))
                except ValueError:
                    pass
        folded = cls._fold(text)
        pattern = r"(?<!\d)(\d{1,2})\s+(?:de\s+)?(" + "|".join(_MONTHS) + r")(?:\s+de)?\s+(\d{4})(?!\d)"
        for match in re.finditer(pattern, folded):
            try:
                found.append((date(int(match.group(3)), _MONTHS[match.group(2)], int(match.group(1))), match.start(), match.end()))
            except ValueError:
                pass
        return sorted(found, key=lambda item: item[1])

    @classmethod
    def extract_date(cls, text: str) -> date | None:
        matches = cls._date_matches(text)
        return matches[0][0] if matches else None

    @staticmethod
    def extract_category(folded: str) -> str | None:
        for category, terms in _CATEGORY_TERMS:
            if any(term in folded for term in terms):
                return category
        return None

    @classmethod
    def extract_segments(cls, text: str, category: str) -> list[dict]:
        folded = cls._fold(text)
        matches = list(re.finditer(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(km|k|m)\b", folded))
        single_sport = {"running": "run", "cycling": "bike", "swimming": "swim"}.get(category)
        segments = []
        for match in matches:
            nearby = []
            for sport_name, terms in _SPORT_TERMS.items():
                for term in terms:
                    for sport_match in re.finditer(r"\b" + re.escape(term) + r"\b", folded):
                        distance_to_value = min(abs(sport_match.start() - match.end()), abs(match.start() - sport_match.end()))
                        if distance_to_value <= 24:
                            nearby.append((distance_to_value, sport_name))
            nearby.sort()
            sport = nearby[0][1] if nearby and (len(nearby) == 1 or nearby[0][0] < nearby[1][0]) else single_sport
            if sport is None:
                continue
            value = float(match.group(1).replace(",", "."))
            distance = round(value * 1000) if match.group(2) in {"km", "k"} else round(value)
            if distance > 0:
                segments.append({"position": len(segments) + 1, "sport": sport, "distance_m": distance, "label": None, "elevation_gain_m": None})
        return segments

    @classmethod
    def extract_location(cls, text: str) -> tuple[str | None, str | None]:
        match = re.search(r"(?:\ben\b|\blugar\s*:)\s+([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ -]{1,50}),\s*([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ -]{1,50}?)(?=\s+(?:el|del|fecha)\b|[.;\n]|$)", text, re.IGNORECASE)
        return (match.group(1).strip(), match.group(2).strip()) if match else (None, None)

    @staticmethod
    def _fold(value: str) -> str:
        return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()

    @staticmethod
    def canonical_url(url: str) -> str:
        parts = urlsplit(str(url))
        if parts.scheme not in {"http", "https"} or not parts.netloc or parts.username or parts.password:
            raise ValueError("unsafe URL")
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", parts.query, ""))

    @classmethod
    def external_id(cls, source_url: str, event_date: str, name: str) -> str:
        normalized_name = re.sub(r"\W+", " ", cls._fold(name)).strip()
        identity = f"tavily\n{cls.canonical_url(source_url)}\n{event_date}\n{normalized_name}"
        return hashlib.sha256(identity.encode()).hexdigest()

    def _raise_provider_error(self, exc: Exception, extract: bool = False):
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if isinstance(exc, TimeoutError) or "timeout" in exc.__class__.__name__.casefold():
            raise CatalogError("provider_timeout") from None
        if status == 429:
            raise CatalogError("provider_rate_limited") from None
        if status in {401, 403}:
            raise CatalogError("provider_authentication_failed") from None
        if status is not None and status >= 500:
            raise CatalogError("provider_temporarily_unavailable") from None
        raise CatalogError("provider_extract_failed" if extract else "provider_request_rejected") from None
