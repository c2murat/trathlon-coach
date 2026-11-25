# Consolidación Git de 4B — revisión y propuesta de separación

Propuesta historica aprobada para consolidacion integral. Su estado operativo actualizado se encuentra en integral-consolidation-status.md; las referencias a ausencia de commits describen exclusivamente la revision inicial.

Version publicable: identidad y fechas de capturas omitidas; originales y evidencias detalladas se conservan solo localmente, fuera de Git. Los enlaces a informe/ designan evidencia local no distribuida.

Revisión del [fecha omitida]. **No se ha hecho staging, commit ni push.** Se aplica la condición explícita del encargo: detener la consolidación cuando haya cambios anteriores que deban separarse. No se eliminó ni revirtió trabajo.

## Estado Git verificado

- Rama local: `sprint-0.8a-authentication`.
- Upstream: `origin/sprint-0.8a-authentication`.
- HEAD local, referencia upstream local y HEAD remoto consultado mediante `git ls-remote`: `75a8142040c4377fd45f0287730ea4f1fef2caef`.
- Último commit: `feat(calendar): add execution status and weekly session rescheduling`.
- El índice está vacío; no hay cambios staged. No se cambia de rama, no hay merge ni force push.
- La consulta remota se realizó sin fetch ni modificación de referencias. El primer acceso falló por el proxy del sandbox; la consulta read-only fuera del sandbox tuvo éxito.

En el inventario inicial hay 18 archivos rastreados modificados, con 589 inserciones y 93 eliminaciones en conjunto. Ese número excluye los archivos nuevos y **no es el tamaño de un commit de 4B**. Se enumeraron 562 archivos no rastreados accesibles en ese momento, incluidos cientos de evidencias locales. Los temporales de pytest con ACL restringidas emiten avisos de permisos; no se intentó borrarlos ni incorporarlos.

## Por qué no procede un commit aislado todavía

HEAD no contiene `weekly_intent.py`, `intent_workouts.py`, `volume_intent.py`, `weekly_distribution.py`, `session_compatibility.py` ni `prescribed_load.py`, entre otros cambios anteriores. 4B importa esos módulos o utiliza sus fixtures/auditores. Incorporar solo sus archivos de fuerza dejaría dependencias ausentes.

`backend/app/application/planning_preview.py` combina cambios de reconciliación/aceptación, Weekly Intent, construcción desde intents, Volume Intent/4A y sidecars de fuerza. Un staging completo de ese archivo atribuiría todos esos cambios a 4B. Se identificó un parche exclusivamente 4B comparando la captura de aplicación previa a 4B con el archivo actual: 13 líneas añadidas, sin eliminaciones. Contiene tres imports, tres propiedades efímeras, tres resets y cuatro líneas de llamadas finales. No se aplicó al índice.

También quedan pendientes una migración de frecuencia, contratos y preferencias, composición/compatibilidad/dobles, cambios de frontend y un cambio independiente de idioma HTML. Las pruebas del workspace completo no demuestran por sí solas que cada commit intermedio propuesto compile; deberán verificarse al preparar los cortes.

## Inventario exacto candidato de 4B

28 archivos nuevos, más los hunks exclusivos de aplicación. En conjunto esos archivos nuevos tienen 4695 líneas en el estado inspeccionado; tampoco es una estadística de commit aprobado, porque la documentación requiere revisión de privacidad.

| Grupo | Archivos |
|---|---|
| Dominio | `backend/app/domains/planning/strength_intent.py`, `strength_timing.py`, `strength_timing_inputs.py`, `strength_timing_policy.py`, `strength_timing_eligibility.py` |
| Pruebas | `backend/tests/test_strength_intent_shadow.py`, `test_strength_timing.py`, `test_strength_timing_inputs.py`, `test_strength_timing_policy.py`, `test_strength_temporal_completion.py`, `test_strength_timing_eligibility.py` |
| Auditores | `backend/scripts/audit_structured_strength.py`, `audit_strength_timing.py`, `audit_strength_timing_inputs.py`, `audit_strength_temporal_policy.py`, `audit_strength_temporal_completion.py`, `audit_strength_timing_eligibility.py` |
| Documentación | `docs/block4b-delivery.md`, `block4b-current-target6-horizon.md`, `block4b-reference-target6-horizon.md`, `block4b1-delivery.md`, `block4b2-delivery.md`, `block4b3-delivery.md`, `block4b3-shadow-matrix.md`, `block4b4-delivery.md`, `block4b4-shadow-matrix.md`, `block4b5-delivery.md`, `block4b-final-summary.md` |
| Archivo mixto | Solo los hunks 4B de `backend/app/application/planning_preview.py`, después de consolidar sus prerrequisitos |

Las rutas abreviadas de cada fila comparten el directorio indicado en su primer archivo. Este informe de consolidación y la preparación del bloque 6 son documentación nueva de esta revisión, no implementación de fuerza ni del calendario.

## Propuesta de commits, pendiente de aprobación

La numeración siguiente es exclusivamente un orden de commits propuesto, no una nueva numeración de bloques de producto. Los ficheros mixtos requieren selección por hunks; no se propone `git add .`.

| Orden | Corte y mensaje propuesto | Archivos / hunks principales |
|---|---|---|
| 1 | `feat(planning): reconcile prescribed load and protect preview acceptance` | `prescribed_load.py`; tests de prescribed load, reconciliación baseline y guard; `LoadReconciliationSummary.tsx`; hunks relacionados de preview, aplicación, API, páginas/tipos y tests frontend; fixture solo tras revisar que sea publicable |
| 2 | `feat(planning): model total weekly session frequency` | Migración `0028_frequency_intent.py`; preferencias de aplicación/BD/contratos; frecuencia en session planning y tipos; formulario/labels/tests de frecuencia/migración |
| 3 | `feat(planning): preserve compatible doubles and weekly distribution` | `session_compatibility.py`, `weekly_distribution.py`; hunks de session planning, preservación de ancla en workout builder; tests de distribución y dobles |
| 4 | `feat(planning): build weekly structure and content from intents` | `weekly_intent.py`, `intent_workouts.py`; hunks de composición, adaptación numérica, preview y aplicación; tests shadow/estructurales y `test_numeric_adaptation.py`; auditores necesarios reutilizables |
| 5 | `feat(planning): apply endurance volume intent authority` | `volume_intent.py`; hunks de integración de volumen, `coherent_volume=True` y su proyección en Weekly Intent; tests de volumen y autoridad de resistencia; documentación publicable de 3/4A |
| 6 | `feat(planning): complete strength timing shadow infrastructure and eligibility` | Los candidatos 4B anteriores, documentación saneada y únicamente los hunks 4B de aplicación |

Antes de cada commit: revisar el patch staged completo, imports, privacidad, dependencias y pruebas de ese estado intermedio. El importe diferido de Volume Intent en Weekly Intent y los modelos de preview deben recortarse junto a su introducción; no se debe copiar sin cambios el archivo final al commit 4. Si un corte intermedio exige una dependencia del siguiente, ajustar el límite de hunks antes de aprobarlo, sin modificar la conducta final validada.

Los cambios de presentación ajenos a esos cortes, como `frontend/index.html` (`lang=en` a `lang=es`) y ajustes de calendario, deben quedar pendientes o ir en un commit independiente de interfaz, identificado y autorizado por separado. Los documentos/auditores anteriores se asignarán al corte correspondiente tras su revisión; no se incorporan automáticamente carpetas completas. No se propone convertir un arreglo de detección de objetivos en un cambio de fuerza.

## Privacidad y seguridad

La búsqueda de patrones de claves privadas, tokens comunes, URLs con credenciales y correos en los candidatos 4B y archivos rastreados modificados no produjo coincidencias. Es una comprobación de patrones, no una certificación universal de ausencia de secretos.

Hay evidencia privada real: 154 JSON locales en `informe/` contienen campos de atleta/contexto. `backups/`, `informe/`, `.env*`, bases de datos y todos los temporales quedan fuera de la propuesta de staging. No se muestran sus valores ni se trasladan a documentación publicable. Los auditores dependen de esas capturas locales; para reproducibilidad distribuida harán falta fixtures anonimizados, no publicar las capturas originales.

`docs/block4b-delivery.md` identifica al atleta en dos pasajes y contiene datos concretos de su historial. Las tablas de horizonte y otros informes derivados también requieren una revisión de minimización de datos antes de incorporarse. Los UUID detectados en dos tests son fixtures sintéticos, no razón para publicar identificadores reales. No se reescribieron los informes existentes ni sus evidencias: el saneamiento debe conservar los originales de forma privada y producir documentación publicable revisada. Los enlaces actuales a evidencias locales deberán marcarse como locales o sustituirse por evidencia sintética segura.

Por tanto, no se declara listo para publicación todo el conjunto de 28 candidatos, aunque no haya coincidencias de tokens. El índice vacío garantiza que no se ha incorporado ninguno de esos materiales en esta revisión.

## Validación y continuación

Se repite la suite backend completa, compileall y diff-check. Se comprueban las capturas y checks finales existentes: 167 casos de fuerza, incluidos 147 temporales, 468 partial, cero elegibles/activaciones y cinco escenarios con identidad completa. El resultado nuevo de backend y las verificaciones finales se registran en el cierre de este documento.

La [preparación del bloque 6](block6-planning-preparation.md) recupera la hoja de ruta, distingue el estado del bloque 5 y propone cortes de trabajo sin implementarlos. Ningún cambio de duración legacy, carga, distribución, base de datos real ni aceptación de planes forma parte de esta revisión.

La decisión pendiente es aprobar o ajustar la separación propuesta y el saneamiento de documentación antes de cualquier staging. El commit solicitado y su push quedan pendientes de esa decisión, por la condición del propio encargo.

## Cierre de la validación repetida

**2034 pruebas backend pasan, 8 warnings, en 357,76 s.** Los 167 casos de fuerza incluyen 147 temporales y forman parte de ese total. Compileall de `backend/app` y `backend/scripts` termina con código 0; `git diff --check` también. Los cinco escenarios guardados conservan identidad byte a byte de artefactos y reportes protegidos, workouts y fingerprints; 468 partial, cero elegibles/activaciones y duración legacy sin cambios. Se verificaron de nuevo los bytes guardados; no se generaron ni aceptaron planes reales. Los 358 archivos preexistentes protegidos siguen idénticos.

No hay commit nuevo: cero archivos incorporados, cero inserciones/eliminaciones comprometidas, sin push. El HEAD y upstream permanecen en `75a8142040c4377fd45f0287730ea4f1fef2caef`, coincidente con la rama remota consultada. El working tree continúa con los cambios previos y estos dos documentos nuevos; el índice sigue vacío. No se declara limpio ni consolidado.

Evidencias locales no destinadas a publicación: `informe/block4b-git-consolidation-final-checks.json`, `-inventory.json`, `-security.json`, `-identity.json`, `-backend.log`, `-strength-collection.log`, `-git-status.txt`, `-diff-check.txt` y `-only-4b-application.patch` (comparten el prefijo `block4b-git-consolidation`). No se añaden a Git automáticamente.
