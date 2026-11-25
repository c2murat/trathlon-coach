# Consolidacion integral del Coherent Weekly Planning Engine

Consolidacion autorizada sobre sprint-0.8a-authentication. Los seis commits estan completados y validados. El primer commit se conserva sin modificar. Los candidatos se validan aisladamente desde HEAD, sin depender de cambios posteriores del working tree.

## PostgreSQL: causa y solucion

La copia aislada buscaba .env dentro de su propio directorio y caia en una conexion por defecto no valida. Se reutiliza la configuracion local existente exclusivamente en variables del proceso, sin copiar .env ni registrar credenciales. Se verifica el servidor local y current_database()=postgres antes de los fixtures. Las migraciones usan una base desechable tricoach_0018_test_* creada y eliminada por el fixture; no migran la base real ni cambian passwords/autenticacion.

En el cierre global, TC_DATABASE_URL en el entorno interferia con una prueba de precedencia de Settings. Se interrumpio ese intento y se repitio toda la suite con un archivo de configuracion privado temporal dentro de la copia aislada, sin esa variable global. La salida se filtro para proteger secretos y el archivo se retiro al terminar. No se modificaron ni omitieron pruebas.

La prueba de migracion corregida pasa. El candidato 2 completo pasa 20 pruebas backend y 2 frontend; build, compileall y diff-check correctos.

## Commits y validacion individual

| N | Hash | Mensaje | Archivos / inserciones / eliminaciones | Validacion |
|---|---|---|---|---|
| 1 | a69f2db | fix(planning): reconcile training load and protect plan acceptance | 14 / +1526 / -10 | 74 backend, 18 frontend, build, compileall, diff-check |
| 2 | 9fc3722 | feat(planning): support training frequency configuration and migration | 10 / +157 / -3 | 20 backend, 2 frontend, build, compileall, diff-check |
| 3 | 4a06915 | feat(planning): support compatible double sessions and weekly distribution | 10 / +718 / -43 | 92 backend, compileall, diff-check |
| 4 | d6bf78b | feat(planning): introduce weekly intent and intent-based workout construction | 13 / +2000 / -56 | 169 backend, build, compileall, diff-check |
| 5 | e189492 | feat(planning): implement volume intent for endurance disciplines | 12 / +1108 / -17 | 149 backend, 390 frontend, build, compileall, diff-check |
| 6 | Este commit | feat(planning): complete strength timing shadow infrastructure and eligibility | 33 / +5269 / -0 | 167 fuerza, backend global y frontend global correctos; build, compileall, diff-check |

Se reservaron configuracion/migracion para 2 y generacion aplicada para 3 porque las pruebas de generacion necesitan dobles compatibles. No se eliminaron casos. La prueba de carga frente a frecuencia reaparece integra al consolidar 3. El mapeo de restricciones consumido por el preview y las aserciones preexistentes relativas al mes sintetico se consolidaron en 5; no cambian recetas ni calendario.

## Privacidad, preservacion y exclusiones

La recuperacion local del trabajo pendiente fue verificada por hashes antes de comenzar y permanece fuera de Git. Se preservan copias privadas de la documentacion previa al saneamiento. Se sustituyo una fixture historica por 50 casos sinteticos de la misma politica, conservando sus aserciones, y se renombro el test para reflejar su origen. Se anonimizan nombres, fechas, identificadores y rutas privadas de informes destinados al repositorio; contratos y resultados de validacion se conservan. Los auditores solo cambian leyendas documentales para omitir identidad.

Nunca se incorporan informe/, backups/, capturas privadas, bases de datos, .env, caches ni temporales. Se usan listas explicitas y blobs/hunks revisados, no git add . Los archivos de pruebas generados en candidatos tampoco se incluyen. No se ejecutan migraciones en datos reales ni se aceptan planes. Fuerza temporal permanece exclusivamente shadow.

Quedan fuera del alcance las mejoras previas de deteccion de objetivos/errores del generador de interfaz y las marcas de idioma/traduccion del calendario. Se mantienen en el working tree sin eliminarse ni atribuirse a fuerza. Tambien permanecen informes privados y auditores historicos no publicables; se identifican en el inventario local final.

## Validacion global y push

Resultado del contenido exacto consolidado: **2034 pruebas backend pasan, 8 warnings, en 358.26 s; 390 pruebas frontend pasan en 47 archivos; build TypeScript/Vite, compileall y diff-check correctos.** Los 167 casos de fuerza incluyen 147 temporales y forman parte de backend. Adicionalmente pasan 397 pruebas frontend del working tree con las mejoras de interfaz ajenas que permanecen sin commit; no se confunden ambos estados.

Se repitieron los cinco replays offline: 468 partial, cero elegibles, cero activaciones y cero cambios de duracion legacy. Los 15 reportes anteriores de artefacto/politica/elegibilidad siguen identicos byte a byte; workouts y fingerprints tambien. El backend del replay coincide con el comprometido. Los 19 archivos de backend/app que formaban parte del trabajo pendiente original conservan sus bytes en el working tree; no se ha cambiado comportamiento de producto para consolidar.

La correccion documental final se integra exclusivamente en el sexto commit local, antes de publicar. Se verifica que no cambia ningun blob de codigo respecto al contenido que paso las suites globales. Se mantienen exactamente seis commits; no se altera el primero ni se realiza rebase, merge, force push o cambio de rama.

El remoto se actualiza y debe seguir en el HEAD inicial esperado antes del envio normal. Este documento registra el cierre de validacion previo al push; el informe final de la intervencion proporciona el hash definitivo y la comprobacion observada de igualdad local/remoto, sin introducir un hash autorreferente en este commit.

## Continuacion

La preparacion del bloque 6 y el diseno original anonimizado se incorporan como documentacion. Bloque 5 conserva construccion lossless desde intents y fuerza legacy. Bloque 6 debe completar busqueda/semillas/poda/precedencia/explicabilidad y fronteras con identidades y recetas congeladas. Esta consolidacion no implementa ese bloque.

## Estado del working tree conservado

Permanecen cuatro archivos rastreados de interfaz ajenos al alcance: frontend/index.html, MonthlyCalendar.tsx, PlanningFlowPages.tsx y PlanningFlowPages.test.tsx. Conservan mejoras previas de idioma/traduccion y deteccion/carga de objetivos/preferencias; no se eliminaron ni se atribuyeron a fuerza. Permanecen tambien 9 auditores historicos ligados a evidencia local y 27 informes previos sin publicar, ademas de informe/, backups/ y temporales/caches. Su inventario exacto se conserva localmente; no se incluyen datos privados para dejar el arbol artificialmente limpio. No queda codigo pendiente de dominio/backend ni de los seis bloques consolidados.
