import type { PlanningPreferences } from "../../types/planning";
const days = [
  "Lunes",
  "Martes",
  "Miércoles",
  "Jueves",
  "Viernes",
  "Sábado",
  "Domingo",
];
export const emptyPreferences = (): PlanningPreferences => ({
  availability_slots: days.map((_, weekday) => ({
    weekday,
    available_minutes: 0,
    max_sessions: 0,
  })),
  max_sessions_per_day: 0,
  max_sessions_per_week: 0,
  preferred_rest_days: [],
  preferred_long_run_day: null,
  preferred_long_bike_day: null,
  strength_sessions_per_week: 0,
});
export function PlanningPreferencesForm({
  value,
  onChange,
  disabled,
}: {
  value: PlanningPreferences;
  onChange(value: PlanningPreferences): void;
  disabled: boolean;
}) {
  const slots = new Map(value.availability_slots.map((x) => [x.weekday, x]));
  const patch = (
    weekday: number,
    part: { available_minutes?: number; max_sessions?: number },
  ) => {
    const current = slots.get(weekday) ?? {
      weekday,
      available_minutes: 0,
      max_sessions: 0,
    };
    const next = { ...current, ...part };
    onChange({
      ...value,
      availability_slots: days.map((_, day) =>
        day === weekday
          ? next
          : (slots.get(day) ?? {
              weekday: day,
              available_minutes: 0,
              max_sessions: 0,
            }),
      ),
    });
  };
  const selectDay = (
    key: "preferred_long_run_day" | "preferred_long_bike_day",
    raw: string,
  ) => onChange({ ...value, [key]: raw === "" ? null : Number(raw) });
  return (
    <fieldset className="planning-preferences" disabled={disabled}>
      <legend>Disponibilidad y preferencias</legend>
      <div className="availability-grid">
        <span className="sr-only">Días disponibles</span>
        {days.map((name, weekday) => {
          const slot = slots.get(weekday),
            enabled = Boolean(
              slot && slot.available_minutes > 0 && slot.max_sessions > 0,
            );
          return (
            <div className="availability-row" key={name}>
            <label>
              <input
                aria-label={`Disponibilidad ${name}`}
                type="checkbox"
                  checked={enabled}
                  onChange={(e) =>
                    patch(
                      weekday,
                      e.target.checked
                        ? { available_minutes: 60, max_sessions: 1 }
                        : { available_minutes: 0, max_sessions: 0 },
                    )
                  }
                />
                {name}
              </label>
              <label>
                Minutos
                <input
                  aria-label={`Minutos ${name}`}
                  type="number"
                  min="0"
                  max="1440"
                  value={slot?.available_minutes ?? 0}
                  onChange={(e) =>
                    patch(weekday, {
                      available_minutes: Number(e.target.value),
                      max_sessions:
                        Number(e.target.value) > 0
                          ? Math.max(slot?.max_sessions ?? 1, 1)
                          : 0,
                    })
                  }
                />
              </label>
              <label>
                Sesiones
                <input
                  aria-label={`Sesiones ${name}`}
                  type="number"
                  min="0"
                  max="4"
                  value={slot?.max_sessions ?? 0}
                  onChange={(e) =>
                    patch(weekday, { max_sessions: Number(e.target.value) })
                  }
                />
              </label>
            </div>
          );
        })}
      </div>
      <div className="planning-preferences__summary">
        <label>
          Máximo por día
          <input
            type="number"
            min="0"
            max="4"
            value={value.max_sessions_per_day}
            onChange={(e) =>
              onChange({
                ...value,
                max_sessions_per_day: Number(e.target.value),
              })
            }
          />
        </label>
        <label>
          Máximo por semana
          <input
            type="number"
            min="0"
            max="28"
            value={value.max_sessions_per_week}
            onChange={(e) =>
              onChange({
                ...value,
                max_sessions_per_week: Number(e.target.value),
              })
            }
          />
        </label>
        <label>
          Sesiones de fuerza
          <input
            type="number"
            min="0"
            max="7"
            value={value.strength_sessions_per_week}
            onChange={(e) =>
              onChange({
                ...value,
                strength_sessions_per_week: Number(e.target.value),
              })
            }
          />
        </label>
        <label>
          Día de tirada larga
          <select
            value={value.preferred_long_run_day ?? ""}
            onChange={(e) =>
              selectDay("preferred_long_run_day", e.target.value)
            }
          >
            <option value="">Sin preferencia</option>
            {days.map((x, i) => (
              <option value={i} key={x}>
                {x}
              </option>
            ))}
          </select>
        </label>
        <label>
          Día de bici larga
          <select
            value={value.preferred_long_bike_day ?? ""}
            onChange={(e) =>
              selectDay("preferred_long_bike_day", e.target.value)
            }
          >
            <option value="">Sin preferencia</option>
            {days.map((x, i) => (
              <option value={i} key={x}>
                {x}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div>
        <strong>Días preferidos de descanso</strong>
        {days.map((name, day) => (
          <label className="inline-check" key={name}>
            <input
              type="checkbox"
              checked={value.preferred_rest_days.includes(day)}
              onChange={(e) =>
                onChange({
                  ...value,
                  preferred_rest_days: e.target.checked
                    ? [...value.preferred_rest_days, day].sort()
                    : value.preferred_rest_days.filter((x) => x !== day),
                })
              }
            />
            {name}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
