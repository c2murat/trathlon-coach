from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app.domains.competition_catalog.models import CatalogError,CatalogSearch
from app.integrations.competition_catalog.tavily import TavilyCompetitionProvider

def row(title="XII Carrera Popular Villa de X - RockTheSport",url="https://rockthesport.com/es/event/villa-x",content="Inscripciones para carrera 10 km el 18/10/2026 en Toledo.",score=.5):
 return {"title":title,"url":url,"content":content,"score":score}
def provider(rows):
 client=SimpleNamespace(search=Mock(return_value={"results":rows}),extract=Mock())
 return TavilyCompetitionProvider("secret",max_results=20,client=client),client
def test_capabilities_and_missing_key():
 item=TavilyCompetitionProvider(None);assert item.search_mode=="web" and item.supports_search_to_manual_goal and not item.supports_structured_import
 with pytest.raises(CatalogError) as exc:item.search_web(CatalogSearch(),"initial")
 assert exc.value.code=="provider_not_configured"
def test_search_first_accepts_candidate_without_date_or_distance():
 item,_=provider([row(content="Inscripción abierta para esta carrera popular.")]);results,more=item.search_web(CatalogSearch(category="running"),"initial")
 assert results[0].result_kind=="event_candidate" and results[0].hints.possible_date is None and results[0].hints.possible_distance is None
def test_listing_is_discoverable_but_not_candidate():
 item,_=provider([row(title="CarrerasCLM - Calendario de Carreras 2026",url="https://carrerasclm.es/carreras",content="Calendario de carreras populares con varias pruebas.")]);results,_=item.search_web(CatalogSearch(category="running"),"initial")
 assert results[0].result_kind=="event_listing"
def test_nominal_match_ranks_first():
 rows=[row(title="Calendario de carreras Toledo",url="https://carrerasclm.es/a"),row(title="10K Villa de Consuegra 2026",url="https://faclm.com/consuegra"),row(title="Carrera 10K Madrid",url="https://example.org/madrid")]
 item,_=provider(rows);results,_=item.search_web(CatalogSearch(text="10K Villa de Consuegra"),"initial")
 assert results[0].title=="10K Villa de Consuegra 2026"
def test_initial_and_more_each_cost_one_search_and_use_distinct_domains():
 item,client=provider([row()]);query=CatalogSearch(category="running",location="Castilla-La Mancha")
 item.search_web(query,"initial");assert client.search.call_count==1 and "include_domains" in client.search.call_args.kwargs
 item.search_web(query,"more");assert client.search.call_count==2 and "exclude_domains" in client.search.call_args.kwargs
 assert not client.extract.called
def test_social_results_are_excluded():
 item,_=provider([row(url="https://instagram.com/p/x")]);assert item.search_web(CatalogSearch(),"more")[0]==[]
def test_canonical_url_and_deduplication():
 item,_=provider([row(url="https://EXAMPLE.org/race/#x"),row(url="https://example.org/race/")]);results,_=item.search_web(CatalogSearch(),"more")
 assert len(results)==1 and results[0].url=="https://example.org/race"
def test_hints_are_optional_and_not_segments():
 item,_=provider([row(title="Carrera 10 km Toledo",content="Carrera 10 km Toledo el 18/10/2026.")]);result=item.search_web(CatalogSearch(),"more")[0][0]
 assert result.hints.possible_date==date(2026,10,18) and result.hints.possible_distance=="10 km" and "segments" not in result.model_dump()
def test_remote_error_is_normalized():
 client=SimpleNamespace(search=Mock(side_effect=TimeoutError()),extract=Mock());item=TavilyCompetitionProvider("secret",client=client)
 with pytest.raises(CatalogError) as exc:item.search_web(CatalogSearch(),"more")
 assert exc.value.code=="provider_timeout"

def test_ciudad_real_territory_dominates_tavily_and_trusted_source_scores():
 rows=[
  row(title="Carrera 10K Madrid",url="https://rockthesport.com/es/event/madrid",score=.99),
  row(title="10K Tomelloso",url="https://general.example/tomelloso",score=.01),
  row(title="Carrera sin ubicación",url="https://general.example/unknown",score=.9),
  row(title="Carrera Popular Puertollano",url="https://general.example/puertollano",score=.1),
  row(title="10K Tafalla",url="https://general.example/tafalla",score=.95),
  row(title="Carrera de Valdepeñas",url="https://general.example/valdepenas",score=.2),
 ]
 item,_=provider(rows);results,_=item.search_web(CatalogSearch(text="carreras 10km",location="ciudad real"),"more")
 top={result.title for result in results[:3]}
 assert top=={"10K Tomelloso","Carrera Popular Puertollano","Carrera de Valdepeñas"}
 assert results.index(next(x for x in results if x.title=="Carrera sin ubicación")) < results.index(next(x for x in results if x.title=="Carrera 10K Madrid"))

def test_nominal_and_territorial_signals_reinforce_each_other():
 rows=[row(title="10K Villa de Consuegra",url="https://general.example/consuegra",score=.1),row(title="Carrera Toledo",url="https://general.example/toledo",score=.9)]
 item,_=provider(rows);results,_=item.search_web(CatalogSearch(text="10K Villa de Consuegra",location="Toledo"),"more")
 assert results[0].title=="10K Villa de Consuegra"

def test_load_more_reranks_the_combined_deduplicated_results():
 initial=[row(title="Carrera 10K Madrid",url="https://rockthesport.com/es/event/madrid",score=.99),row(title="Carrera sin ubicación",url="https://rockthesport.com/es/event/unknown",score=.8)]
 more=[row(title="10K Tomelloso",url="https://general.example/tomelloso",score=.1),row(title="Carrera Popular Puertollano",url="https://general.example/puertollano",score=.1)]
 client=SimpleNamespace(search=Mock(side_effect=[{"results":initial},{"results":more}]),extract=Mock())
 item=TavilyCompetitionProvider("secret",max_results=20,client=client,web_search_cache={})
 query=CatalogSearch(location="Ciudad Real")
 first,has_more=item.search_web(query,"initial");combined,has_more_after=item.search_web(query,"more")
 assert len(first)==2 and has_more is True and has_more_after is False
 assert [result.title for result in combined[:2]]==["10K Tomelloso","Carrera Popular Puertollano"]
 assert len(combined)==4

def test_explicit_title_year_or_linked_date_outside_range_is_rejected_but_unknown_date_remains():
 rows=[row(title="XI San Silvestre Escariche 2025",url="https://example.org/old",content="Carrera popular"),row(title="Carrera Popular Escariche",url="https://example.org/unknown",content="Inscripción abierta")]
 item,_=provider(rows);results,_=item.search_web(CatalogSearch(start_date=date(2026,9,1),end_date=date(2026,12,31)),"more")
 assert [result.title for result in results]==["Carrera Popular Escariche"]
 assert TavilyCompetitionProvider.extract_date("10/04/2026") == date(2026,4,10)

def test_polluted_snippet_keeps_result_without_foreign_hints():
 item,_=provider([row(title="Altsasuko XLVII San Silvestre",url="https://rockthesport.com/altsasu",content="V 10 Km Ciudad Lineal 10/04/2026 Madrid ... otra carrera popular ...")])
 result=item.search_web(CatalogSearch(location="Ciudad Real"),"more")[0][0]
 assert result.title=="Altsasuko XLVII San Silvestre"
 assert result.hints.possible_date is None and result.hints.possible_distance is None and result.hints.possible_location is None

def test_polluted_talavera_snippet_does_not_affect_hints_or_title_geography():
 item,_=provider([row(title="XXX Vuelta al Casco Antiguo de Talavera de la Reina",url="https://example.org/talavera",content="Carrera 10 km Ciudad Lineal Madrid 10/04/2026 otros eventos")])
 result=item.search_web(CatalogSearch(location="Ciudad Real"),"more")[0][0]
 assert result.hints.possible_date is None and result.hints.possible_distance is None and result.hints.possible_location is None
 assert item.geography.territorial_match("Ciudad Real",result.title).relationship=="regional"

def test_coherent_individual_candidate_keeps_hints():
 item,_=provider([row(title="10K Tomelloso",url="https://example.org/tomelloso",content="Carrera 10K Tomelloso. 18/10/2026. 10 km. Tomelloso, Ciudad Real.")])
 result=item.search_web(CatalogSearch(location="Ciudad Real"),"more")[0][0]
 assert result.hints.possible_date==date(2026,10,18) and result.hints.possible_distance=="10k" and result.hints.possible_location=="Tomelloso" and result.hints.possible_category=="running"

def test_listing_never_exposes_arbitrary_event_hints():
 content="Calendario de eventos: Carrera Uno 01/09/2026 5 km; Duatlón Dos 02/10/2026 10 km; Carrera Tres 03/11/2026."
 item,_=provider([row(title="Conxip - Calendario de eventos",url="https://conxip.com/calendario",content=content)])
 result=item.search_web(CatalogSearch(),"more")[0][0]
 assert result.result_kind=="event_listing" and result.hints.possible_date is None and result.hints.possible_distance is None and result.hints.possible_category is None and result.hints.possible_location is None

def test_national_mismatches_rank_below_unknown_and_same_region():
 rows=[row(title="Cross Tafalla",url="https://example.org/tafalla",score=.99),row(title="10K Tres Cantos",url="https://example.org/trescantos",score=.99),row(title="Carrera Getxo",url="https://example.org/getxo",score=.99),row(title="Carrera Altsasuko",url="https://example.org/altsasu",score=.99),row(title="Carrera desconocida",url="https://example.org/unknown",score=.1),row(title="Carrera Talavera de la Reina",url="https://example.org/talavera",score=.1),row(title="10K Tomelloso",url="https://example.org/tomelloso",score=.01)]
 item,_=provider(rows);results,_=item.search_web(CatalogSearch(location="Ciudad Real"),"more")
 titles=[result.title for result in results]
 assert titles[0]=="10K Tomelloso"
 assert titles.index("Carrera desconocida") < titles.index("Carrera Talavera de la Reina") < titles.index("Cross Tafalla")
