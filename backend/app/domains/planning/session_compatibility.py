"""Calendar compatibility only: never creates or modifies workout content."""


def explicit_doubles(context):
    return context.preferences.target_sessions_per_week is not None and context.preferences.max_sessions_per_day >= 2


def daily_capacity(context, slot, config):
    if config.allow_double_sessions:
        return min(slot.max_sessions, context.preferences.max_sessions_per_day)
    return min(slot.max_sessions, context.preferences.max_sessions_per_day, 2 if explicit_doubles(context) else 1)


def pair_cost(a, b, context):
    """None: no supported pairing. Numeric costs are placement preferences.

    Strength/long is permitted with a high soft cost, not a physiological ban.
    Multiple key sessions have no explicit same-day exception in this domain.
    """
    if getattr(a, 'key_session', getattr(a, 'key', False)) and getattr(b, 'key_session', getattr(b, 'key', False)):
        return None
    sports = frozenset((a.discipline, b.discipline))
    if sports == {'swimming', 'strength'}:
        return 0
    if 'strength' in sports and sports & {'cycling', 'running'}:
        return 6 if a.session_type.value.endswith('LONG') or b.session_type.value.endswith('LONG') else 2
    # Restrict objective-specific combinations to goals relevant to both
    # sessions, when associations are available (tests/legacy can omit them).
    related_a = set(getattr(a, 'related_goal_ids', getattr(a, 'goals', ())))
    related_b = set(getattr(b, 'related_goal_ids', getattr(b, 'goals', ())))
    for goal in context.goals:
        if related_a and goal.competition_goal_id not in related_a:
            continue
        if related_b and goal.competition_goal_id not in related_b:
            continue
        legs = {s.sport for s in goal.segments}
        category = goal.category.strip().lower()
        if sports == {'cycling', 'running'} and (category in {'triathlon','duathlon'} or {'bike','run'} <= legs):
            return 1
        if sports == {'swimming', 'running'} and (category == 'aquathlon' or legs == {'swim','run'}):
            return 1
    return None
