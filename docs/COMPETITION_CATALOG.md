# Catálogo de competiciones y objetivos multideporte

## Modelo

Hay tres conceptos distintos:

- Un provider estructurado devuelve un `CatalogEvent` normalizado y revalidable. World Triathlon y AI Web conservan el flujo Search → Detail → Import con snapshot.
- Un provider de búsqueda web devuelve `WebCompetitionSearchResult`: una página útil para descubrir una prueba, no un evento confirmado. Tavily usa este modo.
- `CompetitionGoal` contiene los datos confirmados o editados por el atleta.

Por tanto, resultado web ≠ objetivo. Con Tavily el flujo es resultado web → formulario manual → `CompetitionGoal`. Sólo se conservan `source_provider=tavily` y la URL HTTP(S); no hay `source_external_id` ni snapshot fingido.

Los segmentos persistidos (`swim`, `bike`, `run`) son la fuente de verdad editable. Los presets solo precargan una secuencia y no imponen reglas rígidas. Los campos de distancia anteriores permanecen como resúmenes compatibles y la migración 0023 los convierte en segmentos para objetivos existentes.

El snapshot es histórico: editar nombre, fecha, categoría, ubicación o segmentos no lo modifica, y mostrar un objetivo importado no requiere consultar de nuevo al proveedor. La clave única `(athlete_profile_id, source_provider, source_external_id)` evita importaciones duplicadas concurrentes sin afectar a objetivos manuales.

## API

- `GET /competition-catalog/providers`: providers y estado de configuración.
- `GET /competition-catalog/search`: búsqueda neutral por texto, categoría, fechas, localización y provider opcional.
- `GET /competition-catalog/web-search`: búsqueda web discriminada por provider y fase `initial|more`.
- `GET /competition-catalog/{provider}/events/{external_id}`: detalle normalizado.
- `POST /competition-catalog/import`: importación athlete-scoped; requiere `manage_competition_goals`.

La consulta global requiere autenticación. El CRUD y la importación reutilizan `CurrentAthleteContext` y capabilities: un Coach puede consultar objetivos y catálogo, pero no crear/importar/editar/eliminar si carece de la capability.

## Tavily Search-first

La búsqueda inicial realiza una única Search restringida a fuentes trusted. “Cargar más resultados” realiza una segunda Search explícita sobre web general, excluyendo redes sociales y las fuentes ya consultadas. La API Tavily admite hasta 20 resultados, pero no ofrece `page` u `offset`; no se simula paginación.

Las fuentes trusted elevan el ranking. También se puntúan coincidencia nominal exacta/parcial, categoría, distancia, localización y fechas detectables; el score remoto es sólo una señal secundaria y no se muestra. Los calendarios/listados se muestran como recursos con “Abrir fuente”, sin alta de objetivo. Un candidato individual abre el formulario manual y no ejecuta Extract ni importación estructurada.

La localización se normaliza y resuelve contra una jerarquía territorial española local y versionada: 19 comunidades/ciudades autónomas, 52 provincias y 8.132 municipios. Una provincia escrita en el buscador actúa como alcance provincial (por ejemplo, `Ciudad Real` incluye Tomelloso), mientras un municipio mantiene alcance municipal. El motor distingue coincidencia exacta, relación regional, ubicación desconocida e incompatibilidad nacional. La evidencia compatible en el título tiene el mayor bonus; la del snippet sólo puntúa si es coherente con el título; una contradicción explícita se penaliza sin excluir el resultado. Al cargar más, backend combina, deduplica y vuelve a ordenar ambos lotes antes de devolver la lista completa.

El dataset municipal offline procede de la Generalitat de Catalunya, utiliza códigos provinciales INE y fue descargado el 25/08/2026. Fuente, licencia y actualización están documentadas junto al CSV en `backend/app/domains/competition_catalog/data/README.md`. No se realiza ninguna descarga ni geocodificación en runtime.

Los hints de un candidato priorizan el título y sólo incorporan el snippet cuando comparte tokens específicos del nombre y no presenta señales de listado o múltiples eventos. Los listings nunca publican fecha, distancia, categoría o ubicación tomadas de sus elementos internos. Un año explícito en el título o una fecha inequívoca y coherente fuera del rango solicitado descartan el resultado; la ausencia de fecha sigue siendo válida para discovery.

## Limitaciones conocidas de Tavily Search-first

Tavily proporciona búsqueda web orientada al descubrimiento de competiciones. La ubicación, categoría, distancia y rango temporal mejoran la consulta y el ranking, pero no constituyen garantías estrictas sobre todos los resultados devueltos.

En particular:

- pueden aparecer competiciones de otros territorios;
- algunas páginas pueden contener información agregada o snippets imperfectos;
- los hints web son orientativos y pueden estar ausentes por prudencia;
- el atleta debe verificar siempre la fuente original antes de añadir la prueba;
- los datos definitivos de `CompetitionGoal` son los confirmados manualmente por el atleta.

Esta es una limitación conocida del proveedor y de la búsqueda web, no un flujo de importación estructurada ni un bloqueo de la versión.

Coste esperado con Search basic: Buscar = una Search; Cargar más = una Search adicional; Añadir como objetivo = cero llamadas Tavily.

## World Triathlon

El adapter inicial usa exclusivamente la API oficial, con el header `apikey`, `httpx`, timeout explícito y errores normalizados. No realiza scraping. Configuración:

```env
TC_WORLD_TRIATHLON_ENABLED=true
TC_WORLD_TRIATHLON_API_KEY=replace_with_world_triathlon_api_key
TC_WORLD_TRIATHLON_API_BASE_URL=https://api.triathlon.org/v1
TC_COMPETITION_CATALOG_TIMEOUT_SECONDS=10
```

La clave solo se lee en backend y nunca forma parte de DTOs o logs. Sin clave o con el provider deshabilitado, la aplicación arranca normalmente y la UI muestra “Catálogo no configurado”. Los tests usan `httpx.MockTransport`, no Internet.

## Añadir otro provider

Implementar el protocolo `CompetitionCatalogProvider` (`search`, `detail`, metadatos y `configured`), normalizar a `CatalogEvent` y registrarlo en `build_catalog_registry`. No exponer el payload propietario fuera del adapter.

## Limitaciones actuales

World Triathlon cubre principalmente triatlón, duatlón y acuatlón. Los segmentos solo se importan cuando la respuesta ofrece distancia explícita; TriCoach no inventa distancias ausentes. Para catálogos amplios de carrera, ciclismo y natación se necesitarán adapters oficiales adicionales. No hay sincronización posterior ni scraping.

## AIWebCompetitionProvider

`ai_web` amplía el catálogo a Carrera, Ciclismo, Natación, Triatlón, Duatlón y Acuatlón cuando no existe un adapter de API deportiva específica. World Triathlon sigue siendo el adapter determinista de su API oficial; AI Web es un motor de descubrimiento y extracción estructurada sobre páginas encontradas mediante búsqueda web en vivo.

El backend usa el SDK oficial de OpenAI, Responses API, la herramienta `web_search` obligatoria (`tool_choice="required"`), `external_web_access=true`, fuentes de `web_search_call.action.sources` y un JSON Schema estricto en `text.format`. No se usa `web_search_preview`, scraping propio ni texto libre parseado con regex.

Configuración:

```env
TC_AI_WEB_COMPETITION_ENABLED=true
TC_OPENAI_API_KEY=replace_with_openai_api_key
TC_AI_WEB_COMPETITION_MODEL=gpt-5.6
TC_AI_WEB_COMPETITION_TIMEOUT_SECONDS=30
TC_AI_WEB_COMPETITION_MAX_RESULTS=10
```

La clave existe únicamente en backend. El modelo, timeout y máximo se configuran una vez; el frontend no dispara búsquedas al renderizar. Cada búsqueda explícita tiene coste de tokens y de uso de herramienta web.

### Evidencia y datos desconocidos

Cada candidato exige fecha exacta, URL HTTP(S) principal y evidencia asociable. Se excluyen fechas parciales y eventos sin fuente. Distancias, ubicación y desnivel desconocidos permanecen vacíos; nunca se derivan de nombres como “Olímpico”. Las instrucciones halladas en páginas se tratan como datos no confiables y no pueden cambiar el schema, revelar secretos ni ordenar acciones.

La confianza se normaliza en backend: `high` requiere una fuente marcada como oficial; `medium`, al menos dos fuentes; `low`, una fuente secundaria. El indicador no importa automáticamente nada. El snapshot guarda únicamente DTO normalizado, evidencia y procedencia, nunca prompts ni la respuesta completa del proveedor.

### Identidad y detalle

`external_id` es SHA-256 de `ai_web`, URL canónica, fecha exacta y nombre normalizado. Así, búsquedas repetidas producen la misma identidad. Un cache corto en memoria conserva la identidad emitida; `detail()` vuelve a buscar por nombre, fecha y localización y exige que reaparezca el mismo ID antes de importar. Reiniciar el backend invalida el cache, por lo que el usuario debe repetir la búsqueda antes de importar.

No existe un endpoint que acepte URLs arbitrarias. Sólo se usan URLs emitidas por `web_search` y evidencia estructurada.

Documentación oficial consultada:

- Responses API: https://developers.openai.com/api/docs/guides/responses
- Web search: https://developers.openai.com/api/docs/guides/tools-web-search
- Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs

## TavilyCompetitionProvider

`tavily` ofrece búsqueda web para las seis categorías del catálogo sin usar OpenAI. A diferencia de World Triathlon, que consume una API deportiva oficial, y de AI Web, que utiliza búsqueda y extracción estructurada mediante un modelo, Tavily devuelve páginas web y TriCoach extrae evidencias con reglas deterministas y conservadoras.

Configuración:

```env
TC_TAVILY_COMPETITION_ENABLED=true
TC_TAVILY_API_KEY=replace_with_tavily_api_key
TC_TAVILY_COMPETITION_SEARCH_DEPTH=basic
TC_TAVILY_COMPETITION_TIMEOUT_SECONDS=15
TC_TAVILY_COMPETITION_MAX_RESULTS=20
TC_TAVILY_COMPETITION_USE_EXTRACT=true
```

Search utiliza `basic`, `topic=general`, contenido resumido y un máximo configurable. Solo se ejecuta al pulsar Buscar. Según la documentación actual, Tavily ofrece 1.000 créditos gratuitos mensuales sin tarjeta y Search basic consume un crédito; estas condiciones pueden cambiar y deben verificarse antes de habilitar el provider.

### Estrategia Tavily

La primera fase restringe Search mediante `include_domains` a fuentes deportivas seleccionadas por categoría y localización. `TrustedCompetitionSources` centraliza dominio, categorías, país, regiones, tipo y prioridad. Las semillas verificadas son:

- `triatlon.org`: federación oficial nacional para triatlón, duatlón y acuatlón.
- `faclm.com`: federación regional de atletismo de Castilla-La Mancha.
- `yosoyciclista.com`: plataforma federativa de ciclismo, regional para Castilla-La Mancha.
- `carrerasclm.es`: calendario deportivo regional especializado en running.
- `rockthesport.com`: plataforma nacional de inscripción deportiva.
- `conxip.com`: plataforma nacional de cronometraje y eventos.

Las fuentes nacionales compatibles se seleccionan siempre; las regionales sólo cuando el filtro de localización coincide. Añadir otra región o plataforma requiere incorporar una entrada al registry, no modificar el parser.

Si Trusted Search produce al menos un candidato válido, no hay segunda búsqueda. Si produce cero, se ejecuta un único fallback web con `exclude_domains` para Instagram, Facebook, TikTok, X/Twitter, Threads y Pinterest. Por tanto, Buscar consume normalmente una llamada Search y como máximo dos; Extract sigue reservado a detail/import sobre una única URL.

Una página índice puede ayudar a Tavily a descubrir fichas individuales, pero `listado ≠ competición`: calendarios, agendas, directorios, resultados, páginas genéricas de plataformas y captions sociales nunca se transforman directamente en `CatalogEvent`. No se rastrean sus enlaces ni se implementa crawling propio.

Los snippets se convierten en candidatos únicamente cuando contienen nombre específico, fecha completa inequívocamente ligada a ese nombre, categoría y URL HTTP(S). Las fechas parciales se descartan. Las distancias se convierten a metros sólo cuando aparecen explícitamente y sólo producen segmentos cuando el deporte es demostrable. La ubicación escrita en el filtro nunca se persiste si no aparece en la página. El score de relevancia Tavily no se usa como confianza factual ni para inventar información.

La confianza depende del tipo configurado: federación/circuito oficial = `high`; inscripción, cronometraje o calendario especializado = `medium`; fallback web = `low`. Evidence conserva el `source_kind` neutral (`official`, `registration`, `timing`, `specialized_calendar` o `web`). Una prioridad mayor sólo resuelve duplicados fuertes de mismo nombre, fecha y ubicación; no mezcla páginas contradictorias.

`external_id` es SHA-256 de `tavily`, URL canónica, fecha exacta y nombre normalizado. Search guarda temporalmente la identidad emitida. `detail()` sólo acepta ese ID y, si Extract está habilitado, extrae exclusivamente su URL, vuelve a ejecutar el parser y exige la misma fecha, URL e identidad antes de importar. Extract no se ejecuta sobre todos los resultados. Reiniciar el proceso invalida la memoria temporal y exige repetir Search.

La API key permanece en backend y los errores se normalizan sin incluir headers, payloads ni secretos. No existe un endpoint de extracción de URLs arbitrarias, crawling, Research ni búsqueda en background.

Documentación oficial consultada:

- SDK Python: https://docs.tavily.com/sdk/python/quick-start
- Search: https://docs.tavily.com/documentation/api-reference/endpoint/search
- Extract: https://docs.tavily.com/documentation/api-reference/endpoint/extract
- Créditos: https://docs.tavily.com/documentation/api-credits
- Rate limits: https://docs.tavily.com/documentation/rate-limits
