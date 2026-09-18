# D.2 Q — auditoría de cumplimiento después de sincronizar

Alcance recibido: apartado Q de D.2, integrado en Inicio existente.

`StravaSummaryImportManager` persiste páginas y conserva `affected_activity_ids`
de actividades nuevas/modificadas. `_complete_import` procesa carga, agregados
y Training Status, confirma esa transacción y solo entonces marca succeeded.
Antes de Q no invocaba `PlannedSessionActivityMatching`: el vínculo se creaba
desde endpoints manuales o auto-match explícito.

Se conecta el enlazador existente al final de ese procesamiento, sobre sesiones
del mismo atleta en las fechas candidatas de las actividades afectadas. El GET
del overview nunca crea vínculos ni recalcula estados persistidos.

## Reglas conservadas

Deporte compatible; fecha local de actividad ±1 día; puntuación por fecha,
duración y distancia (esta última no aplica a fuerza). Umbral alto 0,85,
margen mínimo 0,12 y hasta cinco candidatos. Otra sesión relevante del mismo
deporte en ±1 día, candidatos cercanos o vínculos existentes impiden una nueva
asignación automática. Sesiones futuras no se enlazan automáticamente.
Este score preexistente es exclusivamente matching, nunca cumplimiento.

Auto-match conserva vínculos manuales válidos, relaciones N:M y provenance.
Scope y locks del enlazador exigen sesión y actividad del mismo atleta.

## Evaluación reutilizada

`PrescribedCompletedEvidenceAssembler` construye C.1 desde sesiones, workouts,
vínculos, actividades y laps persistidos. Ventana existente: 84 días, fechas
planificadas estrictamente anteriores al cutoff. Se conserva SessionExecutionEvidence,
TargetAdherenceEvidence y LinkProvenance, sin duplicar algoritmos ni reconstruir
intervalos. UNMATCHED no significa que el atleta no haya entrenado.

El overview expresa una fecha inclusiva: la traduce al límite exclusivo de C.1
del día siguiente. Así el último entrenamiento vinculado de hoy también recibe
evidencia C.1. La lista compacta solo contiene fechas anteriores, evitando tratar
sesiones todavía pendientes de hoy como ya ocurridas. No se modifica C.1.

## Calendario

El calendario anual consume TrainingPlanSession sin evidencia C.1 y cubre rangos
fuera de los 84 días. Badges para todo el año exigirían lectura por rango y reglas
de cutoff propias del contrato. Se difieren a un subbloque posterior como permite
Q7; esta entrega se centra en Inicio y cinco sesiones recientes.
