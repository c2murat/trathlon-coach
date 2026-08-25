from app.domains.competition_catalog.geography import CompetitionGeography, REGIONS, normalize_location


geo = CompetitionGeography()


def test_normalization_handles_case_accents_hyphens_and_punctuation():
    assert {normalize_location(value) for value in ("Ciudad Real", "ciudad real", "CIUDAD REAL")} == {"ciudad real"}
    assert {normalize_location(value) for value in ("Castilla-La Mancha", "castilla la mancha", "Castilla La Mancha")} == {"castilla la mancha"}
    assert normalize_location("Alcázar de San Juan") == normalize_location("alcazar de san juan")


def test_hierarchy_and_duplicate_safe_identity():
    consuegra = geo.places_named("Consuegra")[0]
    assert consuegra.province == "Toledo" and consuegra.region == "Castilla-La Mancha" and consuegra.country == "España"
    assert consuegra.identity == ("Consuegra", "Toledo", "Castilla-La Mancha", "España")
    assert geo.resolve_location_scope("Ciudad Real").kind == "province"


def test_ciudad_real_province_scope():
    for place in ("Tomelloso", "Puertollano", "Valdepeñas", "Manzanares", "Ciudad Real"):
        assert geo.territorial_match("Ciudad Real", place).compatible
    for place in ("Madrid", "Toledo", "Tafalla"):
        assert not geo.territorial_match("Ciudad Real", place).compatible


def test_castilla_la_mancha_region_scope():
    for place in ("Albacete", "Ciudad Real", "Cuenca", "Guadalajara", "Toledo", "Tomelloso"):
        assert geo.territorial_match("Castilla-La Mancha", place).compatible
    for place in ("Madrid", "Valencia", "Jaén"):
        assert not geo.territorial_match("Castilla-La Mancha", place).compatible


def test_toledo_scope_and_territorial_scoring():
    for place in ("Consuegra", "Madridejos", "Toledo"):
        assert geo.territorial_match("Toledo", place).compatible
    for place in ("Tomelloso", "Madrid"):
        assert not geo.territorial_match("Toledo", place).compatible
    assert geo.territorial_score("Ciudad Real", "10K Tomelloso") > geo.territorial_score("Ciudad Real", "Carrera Popular", "Valdepeñas, Ciudad Real") > 0
    assert geo.territorial_score("Ciudad Real", "Carrera sin ubicación") < 0
    assert geo.territorial_score("Ciudad Real", "10K Madrid") < -20


def test_offline_dataset_covers_all_spanish_territories_and_municipalities():
    assert len(REGIONS) == 19
    assert sum(len(region.provinces) for region in REGIONS) == 52
    assert sum(len(province.municipalities) for region in REGIONS for province in region.provinces) == 8132


def test_national_hierarchy_and_official_bilingual_aliases():
    expected = {
        "Tres Cantos": ("Madrid", "Comunidad de Madrid"),
        "Tafalla": ("Navarra", "Comunidad Foral de Navarra"),
        "Getxo": ("Bizkaia", "País Vasco"),
        "Altsasu": ("Navarra", "Comunidad Foral de Navarra"),
        "Alsasua": ("Navarra", "Comunidad Foral de Navarra"),
        "Altsasuko": ("Navarra", "Comunidad Foral de Navarra"),
        "Estella": ("Navarra", "Comunidad Foral de Navarra"),
        "Lizarra": ("Navarra", "Comunidad Foral de Navarra"),
    }
    for alias, hierarchy in expected.items():
        place = geo.places_named(alias)[0]
        assert (place.province, place.region) == hierarchy


def test_exact_regional_unknown_and_incompatible_relationships():
    assert geo.territorial_match("Ciudad Real", "10K Tomelloso").relationship == "exact"
    assert geo.territorial_match("Ciudad Real", "Carrera sin lugar").relationship == "unknown"
    assert geo.territorial_match("Ciudad Real", "Vuelta de Talavera de la Reina").relationship == "regional"
    for title in ("Carrera Tres Cantos", "Cross Tafalla", "10K Getxo", "San Silvestre Altsasuko"):
        assert geo.territorial_match("Ciudad Real", title).relationship == "incompatible"
    assert geo.territorial_match("Castilla-La Mancha", "Talavera de la Reina").compatible


def test_municipality_scope_is_concrete():
    assert geo.resolve_location_scope("Tomelloso").kind == "municipality"
    assert geo.territorial_match("Tomelloso", "10K Tomelloso").relationship == "exact"
    assert geo.territorial_match("Tomelloso", "Carrera Puertollano").relationship == "regional"
