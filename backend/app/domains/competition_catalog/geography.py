from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATASET_PATH = Path(__file__).with_name("data") / "spain_municipalities_2026.csv"


def normalize_location(value: str) -> str:
    folded = "".join(c for c in unicodedata.normalize("NFKD", value).casefold() if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", folded))


@dataclass(frozen=True, slots=True)
class MunicipalityDefinition:
    code: str
    name: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProvinceDefinition:
    code: str
    name: str
    region: str
    municipalities: tuple[MunicipalityDefinition, ...]


@dataclass(frozen=True, slots=True)
class RegionDefinition:
    name: str
    country: str
    provinces: tuple[ProvinceDefinition, ...]
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TerritorialPlace:
    kind: str
    name: str
    province: str | None
    region: str
    country: str

    @property
    def identity(self) -> tuple[str, str | None, str, str]:
        return (self.name, self.province, self.region, self.country)


@dataclass(frozen=True, slots=True)
class LocationScope:
    kind: str
    names: frozenset[str]
    provinces: frozenset[str]
    regions: frozenset[str]


@dataclass(frozen=True, slots=True)
class TerritorialEvidence:
    relationship: str
    detected: bool
    specificity: int

    @property
    def compatible(self) -> bool:
        return self.relationship == "exact"

    @property
    def incompatible(self) -> bool:
        return self.relationship == "incompatible"


_PROVINCES: dict[str, tuple[str, str]] = {
    "01": ("Álava", "País Vasco"), "02": ("Albacete", "Castilla-La Mancha"),
    "03": ("Alicante", "Comunitat Valenciana"), "04": ("Almería", "Andalucía"),
    "05": ("Ávila", "Castilla y León"), "06": ("Badajoz", "Extremadura"),
    "07": ("Illes Balears", "Illes Balears"), "08": ("Barcelona", "Cataluña"),
    "09": ("Burgos", "Castilla y León"), "10": ("Cáceres", "Extremadura"),
    "11": ("Cádiz", "Andalucía"), "12": ("Castellón", "Comunitat Valenciana"),
    "13": ("Ciudad Real", "Castilla-La Mancha"), "14": ("Córdoba", "Andalucía"),
    "15": ("A Coruña", "Galicia"), "16": ("Cuenca", "Castilla-La Mancha"),
    "17": ("Girona", "Cataluña"), "18": ("Granada", "Andalucía"),
    "19": ("Guadalajara", "Castilla-La Mancha"), "20": ("Gipuzkoa", "País Vasco"),
    "21": ("Huelva", "Andalucía"), "22": ("Huesca", "Aragón"),
    "23": ("Jaén", "Andalucía"), "24": ("León", "Castilla y León"),
    "25": ("Lleida", "Cataluña"), "26": ("La Rioja", "La Rioja"),
    "27": ("Lugo", "Galicia"), "28": ("Madrid", "Comunidad de Madrid"),
    "29": ("Málaga", "Andalucía"), "30": ("Murcia", "Región de Murcia"),
    "31": ("Navarra", "Comunidad Foral de Navarra"), "32": ("Ourense", "Galicia"),
    "33": ("Asturias", "Principado de Asturias"), "34": ("Palencia", "Castilla y León"),
    "35": ("Las Palmas", "Canarias"), "36": ("Pontevedra", "Galicia"),
    "37": ("Salamanca", "Castilla y León"), "38": ("Santa Cruz de Tenerife", "Canarias"),
    "39": ("Cantabria", "Cantabria"), "40": ("Segovia", "Castilla y León"),
    "41": ("Sevilla", "Andalucía"), "42": ("Soria", "Castilla y León"),
    "43": ("Tarragona", "Cataluña"), "44": ("Teruel", "Aragón"),
    "45": ("Toledo", "Castilla-La Mancha"), "46": ("Valencia", "Comunitat Valenciana"),
    "47": ("Valladolid", "Castilla y León"), "48": ("Bizkaia", "País Vasco"),
    "49": ("Zamora", "Castilla y León"), "50": ("Zaragoza", "Aragón"),
    "51": ("Ceuta", "Ceuta"), "52": ("Melilla", "Melilla"),
}

_REGION_ALIASES = {
    "Comunidad Foral de Navarra": ("Navarra", "C. Foral de Navarra"),
    "Comunitat Valenciana": ("Comunidad Valenciana",),
    "Principado de Asturias": ("Asturias",), "Región de Murcia": ("Murcia",),
    "País Vasco": ("Euskadi",), "Cataluña": ("Catalunya",),
}
_MUNICIPALITY_ALIASES = {
    "Altsasu/Alsasua": ("Altsasu", "Alsasua", "Altsasuko"),
    "Estella-Lizarra": ("Estella", "Lizarra"),
    "Vitoria-Gasteiz": ("Vitoria", "Gasteiz"),
    "Donostia/San Sebastián": ("Donostia", "San Sebastián"),
    "Pamplona/Iruña": ("Pamplona", "Iruña"),
}


def _display_aliases(name: str) -> tuple[str, ...]:
    aliases = list(_MUNICIPALITY_ALIASES.get(name, ()))
    if "/" in name:
        aliases.extend(part.strip() for part in name.split("/") if part.strip())
    if ", " in name:
        main, article = name.rsplit(", ", 1)
        if article.casefold() in {"el", "la", "los", "las"}:
            aliases.append(f"{article} {main}")
    return tuple(dict.fromkeys(alias for alias in aliases if normalize_location(alias) != normalize_location(name)))


@lru_cache(maxsize=1)
def load_regions() -> tuple[RegionDefinition, ...]:
    municipalities: dict[str, list[MunicipalityDefinition]] = {code: [] for code in _PROVINCES}
    with DATASET_PATH.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            code = row["Codi"].strip()
            province_code = code[:2]
            name = row["Nom"].strip()
            if province_code in municipalities and name and code != "999999":
                municipalities[province_code].append(MunicipalityDefinition(code, name, _display_aliases(name)))
    grouped: dict[str, list[ProvinceDefinition]] = {}
    for code, (province_name, region_name) in _PROVINCES.items():
        grouped.setdefault(region_name, []).append(ProvinceDefinition(code, province_name, region_name, tuple(municipalities[code])))
    return tuple(RegionDefinition(region, "España", tuple(provinces), _REGION_ALIASES.get(region, ())) for region, provinces in grouped.items())


REGIONS = load_regions()
CASTILLA_LA_MANCHA = next(region for region in REGIONS if region.name == "Castilla-La Mancha")


class CompetitionGeography:
    def __init__(self, regions: tuple[RegionDefinition, ...] = REGIONS):
        self.regions = regions
        index: dict[str, dict[tuple[str, str, str | None, str, str], TerritorialPlace]] = {}
        for place, aliases in self._build_places():
            for alias in (place.name, *aliases):
                normalized = normalize_location(alias)
                if normalized:
                    index.setdefault(normalized, {})[(place.kind, *place.identity)] = place
        self._index = {name: tuple(places.values()) for name, places in index.items()}
        self._max_tokens = max(len(name.split()) for name in self._index)

    def _build_places(self):
        for region in self.regions:
            yield TerritorialPlace("region", region.name, None, region.name, region.country), region.aliases
            for province in region.provinces:
                yield TerritorialPlace("province", province.name, province.name, region.name, region.country), ()
                for municipality in province.municipalities:
                    yield TerritorialPlace("municipality", municipality.name, province.name, region.name, region.country), municipality.aliases

    def places_named(self, value: str) -> tuple[TerritorialPlace, ...]:
        return self._index.get(normalize_location(value), ())

    def resolve_location_scope(self, value: str | None) -> LocationScope | None:
        if not value:
            return None
        places = self.places_named(value)
        if not places:
            return None
        province_places = [place for place in places if place.kind == "province"]
        chosen = province_places or [place for place in places if place.kind == "region"] or list(places)
        kind = chosen[0].kind if len({place.kind for place in chosen}) == 1 else "ambiguous"
        return LocationScope(kind, frozenset(normalize_location(p.name) for p in chosen), frozenset(normalize_location(p.province) for p in chosen if p.province), frozenset(normalize_location(p.region) for p in chosen))

    def detect(self, text: str) -> tuple[TerritorialPlace, ...]:
        tokens = normalize_location(text).split()
        found: dict[tuple[str, str, str | None, str, str], TerritorialPlace] = {}
        for start in range(len(tokens)):
            for length in range(1, min(self._max_tokens, len(tokens) - start) + 1):
                for place in self._index.get(" ".join(tokens[start:start + length]), ()):
                    found[(place.kind, *place.identity)] = place
        return tuple(found.values())

    def territorial_match(self, search_location: str | None, candidate_text: str) -> TerritorialEvidence:
        scope = self.resolve_location_scope(search_location)
        places = self.detect(candidate_text)
        if scope is None or not places:
            return TerritorialEvidence("unknown", bool(places), 0)
        exact = [place for place in places if self._exact(scope, place)]
        regional = [place for place in places if self._regional(scope, place)]
        if exact:
            return TerritorialEvidence("exact", True, max({"region": 1, "province": 2, "municipality": 3}[p.kind] for p in exact))
        if regional:
            return TerritorialEvidence("regional", True, max({"region": 1, "province": 2, "municipality": 3}[p.kind] for p in regional))
        return TerritorialEvidence("incompatible", True, 0)

    @staticmethod
    def _exact(scope: LocationScope, place: TerritorialPlace) -> bool:
        name, province, region = normalize_location(place.name), normalize_location(place.province or ""), normalize_location(place.region)
        if scope.kind == "region": return region in scope.regions
        if scope.kind == "province": return province in scope.provinces
        return name in scope.names and (not scope.provinces or province in scope.provinces)

    @staticmethod
    def _regional(scope: LocationScope, place: TerritorialPlace) -> bool:
        province, region = normalize_location(place.province or ""), normalize_location(place.region)
        if scope.kind == "province": return region in scope.regions and province not in scope.provinces
        if scope.kind in {"municipality", "ambiguous"}: return province in scope.provinces or region in scope.regions
        return False

    def primary_location(self, text: str) -> TerritorialPlace | None:
        return max(self.detect(text), key=lambda p: {"region": 1, "province": 2, "municipality": 3}[p.kind], default=None)

    def territorial_score(self, search_location: str | None, title: str, snippet: str = "") -> float:
        if self.resolve_location_scope(search_location) is None: return 0.0
        title_evidence, snippet_evidence = self.territorial_match(search_location, title), self.territorial_match(search_location, snippet)
        if title_evidence.relationship == "exact": return {1: 18.0, 2: 24.0, 3: 28.0}[title_evidence.specificity]
        if title_evidence.relationship == "regional": return -10.0
        if title_evidence.relationship == "incompatible": return -30.0
        if snippet_evidence.relationship == "exact": return {1: 10.0, 2: 14.0, 3: 17.0}[snippet_evidence.specificity]
        if snippet_evidence.relationship == "regional": return -7.0
        if snippet_evidence.relationship == "incompatible": return -12.0
        return -1.0


@lru_cache(maxsize=1)
def default_competition_geography() -> CompetitionGeography:
    return CompetitionGeography()
