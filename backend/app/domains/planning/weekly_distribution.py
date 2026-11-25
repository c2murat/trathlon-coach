"""Bounded deterministic date-only optimization of already prescribed sessions."""
from collections import Counter
from datetime import timedelta
from app.domains.planning.session_compatibility import explicit_doubles, daily_capacity, pair_cost


MAX_SEARCH_NODES = 12000
LONG_TYPES = {"RUN_LONG", "BIKE_LONG"}


def distribute_week(week, context, config, other_sessions=()):
    from app.domains.planning.session_planning import SessionPlacementDecision

    movable = tuple(s for s in week.sessions if s.flexible and s.discipline != "competition")
    fixed = tuple(s for s in week.sessions if s not in movable)
    if not movable:
        return week
    slots = {s.weekday: s for s in context.preferences.availability_slots}
    days = tuple(week.week_start + timedelta(days=i) for i in range((week.week_end - week.week_start).days + 1))
    events = {g.event_date for g in context.goals}
    primary_rest = {g.event_date - timedelta(days=1) for g in context.goals if g.priority == "A"}
    compatible_doubles = explicit_doubles(context)
    pairing = tuple(tuple(pair_cost(a,b,context) for b in movable) for a in movable) if compatible_doubles else ()
    fixed_dates = {s.date for s in fixed} | events

    def preferred(s):
        return (context.preferences.preferred_long_run_day if s.session_type.value == "RUN_LONG"
                else context.preferences.preferred_long_bike_day if s.session_type.value == "BIKE_LONG" else None)

    def valid(s, day):
        slot = slots.get(day.weekday())
        if day in fixed_dates or slot is None or slot.max_sessions <= 0:
            return False
        if (s.target_duration_minutes or 0) > slot.available_minutes:
            return False
        if s.discipline == "strength" and any(0 < (e - day).days <= 2 for e in events):
            return False
        if s.session_type.value in LONG_TYPES and any(
            t.session_type == s.session_type and abs((day - t.date).days) < config.minimum_same_long_spacing_days
            for t in other_sessions
        ):
            return False
        return True

    candidates = tuple(tuple(d for d in days if valid(s, d)) for s in movable)

    def score(dates):
        strength_adj = type_adj = long_adj = sport_adj = similar_adj = spacing = concentration = 0
        pairing_cost = double_count = 0
        for i, (s, d) in enumerate(zip(movable, dates)):
            for j, (t, e) in enumerate(zip(movable[:i], dates[:i])):
                gap = abs((d - e).days)
                if compatible_doubles and gap == 0:
                    cost = pairing[i][j]
                    pairing_cost += cost if cost is not None else 100
                    double_count += 1
                adjacent = gap <= 1
                same_type = s.session_type == t.session_type
                strength_adj += adjacent and s.discipline == t.discipline == "strength"
                type_adj += adjacent and same_type
                long_adj += adjacent and s.session_type.value in LONG_TYPES and t.session_type.value in LONG_TYPES
                sport_adj += adjacent and s.discipline == t.discipline
                similar_adj += adjacent and s.purpose == t.purpose and s.intensity == t.intensity
                spacing += (len(days) - gap) ** 2 if same_type else 0
                concentration += (len(days) - gap) ** 2
        rest = sum(d in primary_rest or d.weekday() in context.preferences.preferred_rest_days for d in dates)
        long_pref = sum(preferred(s) is not None and preferred(s) != d.weekday() for s, d in zip(movable, dates))
        key_conflicts = sum(
            abs((d - e).days) < config.minimum_gap_between_key_sessions_days
            for i, (s, d) in enumerate(zip(movable, dates)) if s.key_session
            for t, e in zip(movable[:i], dates[:i]) if t.key_session
        )
        prefix = (strength_adj, rest, long_pref, key_conflicts, type_adj, long_adj)
        # A compatible double can win on rest/long/key spacing. When those
        # outcomes tie, prefer fewer doubles rather than filling daily capacity.
        return (prefix + ((pairing_cost,) if compatible_doubles else ())
                + (spacing, sport_adj, similar_adj)
                + ((double_count,) if compatible_doubles else ()) + (concentration, tuple(dates)))

    original = tuple(s.date for s in movable)
    best = original
    def feasible(dates):
        for day in set(dates):
            group = [s for s, d in zip(movable, dates) if d == day]
            slot = slots.get(day.weekday())
            if slot is None or len(group) > daily_capacity(context, slot, config) or sum(s.target_duration_minutes or 0 for s in group) > slot.available_minutes:
                return False
            if compatible_doubles and any(pair_cost(a,b,context) is None for i,a in enumerate(group) for b in group[:i]):
                return False
        return all(d in options for d, options in zip(dates, candidates))
    best_score = score(best) if feasible(original) else None
    nodes = 0
    counts = Counter()
    minutes = Counter()
    order = sorted(range(len(movable)), key=lambda i: (len(candidates[i]), i))
    if compatible_doubles:
        order = sorted(order, key=lambda i: (len(candidates[i]), preferred(movable[i]) is None, not movable[i].key_session, i))
        candidates = tuple(tuple(sorted(options, key=lambda day: (
            preferred(s) is not None and preferred(s) != day.weekday(),
            day in primary_rest or day.weekday() in context.preferences.preferred_rest_days,
            day != s.date, day))) for s, options in zip(movable, candidates))
    assigned = list(original)
    occupants = {day: [] for day in days}
    capacities = {day: daily_capacity(context,slots[day.weekday()],config) for day in days if day.weekday() in slots}

    def search(depth):
        nonlocal nodes, best, best_score
        if nodes >= MAX_SEARCH_NODES:
            return
        nodes += 1
        if depth == len(order):
            value = score(assigned)
            if best_score is None or value < best_score:
                best, best_score = tuple(assigned), value
            return
        i = order[depth]
        s = movable[i]
        for day in candidates[i]:
            slot = slots[day.weekday()]
            capacity = capacities[day]
            duration = s.target_duration_minutes or 0
            if counts[day] >= capacity or minutes[day] + duration > slot.available_minutes:
                continue
            if compatible_doubles and any(pairing[i][j] is None for j in occupants[day]):
                continue
            assigned[i] = day
            counts[day] += 1
            minutes[day] += duration
            occupants[day].append(i)
            search(depth + 1)
            occupants[day].pop()
            counts[day] -= 1
            minutes[day] -= duration

    search(0)
    if best == original:
        return week
    updated = tuple(s.model_copy(update={
        "date": day,
        "placement": SessionPlacementDecision(
            code="WEEKLY_STRUCTURAL_DISTRIBUTION", preferred_date_used=preferred(s) == day.weekday(),
            context={"search_nodes": nodes, "search_limit_reached": nodes >= MAX_SEARCH_NODES,
                     "strength_adjacencies": best_score[0], "same_type_adjacencies": best_score[4],
                     "reason": "improves_weekly_spacing", "original_date": (
                         s.placement.context.get("original_date", s.date.isoformat())
                         if s.placement.code == "WEEKLY_STRUCTURAL_DISTRIBUTION" and s.placement.context.get("distributed_date") == s.date.isoformat()
                         else s.date.isoformat()),
                     "distributed_date": day.isoformat()},
        ),
    }) for s, day in zip(movable, best))
    sessions = tuple(sorted((*fixed, *updated), key=lambda s: (s.date, s.session_type.value, s.discipline)))
    occupied = {s.date for s in sessions}
    warnings = week.warnings
    if compatible_doubles:
        from app.domains.planning.contracts import PlanningWarning
        # Replace only date-derived warnings on an actually changed calendar.
        # Keeping greedy warnings here would claim a now-free Monday is used.
        derived = {'PREFERRED_REST_DAY_UNAVAILABLE','PREFERRED_LONG_DAY_UNAVAILABLE','KEY_SESSION_SPACING_CONSTRAINT'}
        warnings = [w for w in warnings if w.code not in derived]
        used_rest = sorted({s.date.weekday() for s in sessions if s.date.weekday() in context.preferences.preferred_rest_days})
        if used_rest:
            warnings.append(PlanningWarning(code='PREFERRED_REST_DAY_UNAVAILABLE',context={'weekdays':','.join(map(str,used_rest))}))
        if len(days) == 7:
            warnings.extend(PlanningWarning(code='PREFERRED_LONG_DAY_UNAVAILABLE',context={'discipline':s.discipline,'preferred_weekday':preferred(s)})
                for s in sessions if preferred(s) is not None and preferred(s) != s.date.weekday())
        keys = [s for s in sessions if s.key_session]
        warnings.extend(PlanningWarning(code='KEY_SESSION_SPACING_CONSTRAINT',context={'date':s.date.isoformat()})
            for i,s in enumerate(keys) if any(abs((s.date-t.date).days)<config.minimum_gap_between_key_sessions_days for t in keys[:i]))
        warnings = tuple(sorted(warnings,key=lambda w:(w.code,str(w.context))))
    return week.model_copy(update={"sessions": sessions, "rest_dates": tuple(d for d in days if d not in occupied),"warnings":warnings})
