"""Build legacy content from fixed intents, before final calendar distribution.

Seed dates retain the existing date-derived content rules. After distribution
only legacy draft identity is rebound; no target, step or duration is edited.
"""
from datetime import date

from app.domains.planning.contracts import context_fingerprint
from app.domains.planning.weekly_intent import prescriptions_by_intent
from app.domains.planning.workout_builder import build_structured_workout, STRUCTURED_WORKOUT_SCHEMA_VERSION


def bind_legacy_draft_identity(draft, context, prescription, config):
    """Mirror the legacy builder's identity projection without rebuilding content.

    This adapter is deliberately guarded by full-draft equivalence tests against
    build_structured_workout. WorkoutBuilder itself and its formulas stay intact.
    """
    original = prescription.placement.context.get("original_date")
    if (prescription.placement.code == "WEEKLY_STRUCTURAL_DISTRIBUTION" and isinstance(original, str)
            and prescription.placement.context.get("distributed_date") == prescription.date.isoformat()):
        prescription = prescription.model_copy(update={"date": date.fromisoformat(original)})
    fingerprint = context_fingerprint({
        "context_fingerprint": context.fingerprint, "session_prescription": prescription,
        "config": config, "structured_workout_schema_version": STRUCTURED_WORKOUT_SCHEMA_VERSION,
    })
    return draft.model_copy(update={"fingerprint": fingerprint})


class IntentWorkoutBuild:
    def __init__(self, context, config):
        self.context = context
        self.config = config
        self.drafts = {}
        self.week_counts = {}

    def prepare(self, intent, prescriptions):
        if len(prescriptions) != len(intent.session_intents):
            raise ValueError("WORKOUT_FREQUENCY_MUST_COME_FROM_INTENT")
        for session, prescription in zip(intent.session_intents, prescriptions, strict=True):
            if session.intent_id in self.drafts:
                raise ValueError("SESSION_INTENT_BUILT_TWICE")
            self.drafts[session.intent_id] = build_structured_workout(self.context, prescription, self.config)
        self.week_counts[intent.week_start] = len(prescriptions)

    def finish(self, plan, structural_report):
        drafts = []
        for result, week in zip(structural_report.weeks, plan.weeks, strict=True):
            by_intent = prescriptions_by_intent(result.intent, week)
            ordered = {id(p): key for key, p in by_intent.items()}
            for prescription in week.sessions:
                if prescription.discipline == "competition":
                    drafts.append(build_structured_workout(self.context, prescription, self.config))
                else:
                    key = ordered[id(prescription)]
                    drafts.append(bind_legacy_draft_identity(self.drafts[key], self.context, prescription, self.config))
        return tuple(drafts)

    def annotate(self, structural_report):
        return structural_report.model_copy(update={"weeks": tuple(
            result.model_copy(update={"generated_workout_count": self.week_counts[result.intent.week_start]})
            for result in structural_report.weeks
        )})
