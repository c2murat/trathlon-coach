# TriCoach AI Domain Model

## Purpose and boundary

This document defines the business meaning of TriCoach AI: the language athletes and coaches use to reason about training, performance, recovery, and decisions. It does not describe storage, software components, integrations, interfaces, or delivery mechanisms.

A business concept is meaningful in coaching even if no software exists. A technical entity is an implementation choice used to represent that meaning. They are not interchangeable: one business concept may have several technical representations, and one technical representation may support several business concepts. Names here establish domain language, not implementation requirements.

The domain supports swimming, cycling, running, strength, multisport, and complementary training. It serves amateur triathletes first and allows human coaching under explicit athlete authority. TriCoach AI supports coaching judgment; it is not a medical diagnostic tool.

## Core concepts

### 1. Athlete

- **Definition:** A person preparing for, participating in, or learning from endurance and strength training.
- **Purpose:** Owns and benefits from training intentions, history, wellness context, and coaching choices.
- **Lifecycle:** Begins when the person establishes training context; preferences, experience, availability, and goals evolve; participation may pause or end without changing the meaning of history.
- **Relationships:** Has Plans, Objectives, Zones, Workouts, Activities, Races, Wellness, Equipment, Recommendations, and Decisions; may work with a Coach.
- **Created by:** The athlete establishes their coaching identity and context.
- **Modified by:** The Athlete; a Coach contributes only within granted authority.
- **Nature:** A real-world actor, neither deterministic nor AI-derived.
- **Examples:** An amateur preparing for a first Olympic-distance triathlon; an age-group athlete targeting a long-course race.

### 2. Coach

- **Definition:** A human who guides Athletes through observation, planning, communication, and accountable judgment.
- **Purpose:** Adds experience, context, empathy, and oversight to training choices.
- **Lifecycle:** A relationship is proposed, accepted, scoped, changed, paused, or ended by the Athlete; ending access does not rewrite prior decisions.
- **Relationships:** Reviews evidence, authors or adjusts plans, proposes Recommendations, and participates in Coaching Decisions.
- **Created by:** A person acting as a coach and an Athlete granting a relationship.
- **Modified by:** The Coach maintains coaching context; the Athlete controls relationship authority.
- **Nature:** A real-world actor. Human interpretation is judgment, not deterministic or AI-derived.
- **Examples:** A remote triathlon coach; a swim specialist advising an Athlete.

### 3. Training Plan

- **Definition:** An evolving arrangement of training intended to move an Athlete toward Objectives and Races over time.
- **Purpose:** Connects long-term intent with progressive, practical training while accommodating recovery and life constraints.
- **Lifecycle:** Drafted, reviewed, activated, revised, completed, paused, or retired; its history remains meaningful as it evolves.
- **Relationships:** Organizes Cycles, Weeks, and Planned Workouts; responds to Objectives, Race Goals, Recovery, Recommendations, and Decisions.
- **Created by:** An Athlete, authorized Coach, or assisted process reviewed by the Athlete.
- **Modified by:** The Athlete or authorized Coach; accepted Decisions may cause explicit revisions.
- **Nature:** Schedule and totals can be deterministic. Design is human judgment and may be AI-assisted, never silently AI-controlled.
- **Examples:** A 20-week half-distance plan; a return-to-consistency plan without a target race.

### 4. Training Cycle

- **Definition:** A phase within a Training Plan grouping weeks around a shared adaptation emphasis.
- **Purpose:** Makes progression, specificity, and recovery understandable between the whole plan and one week.
- **Lifecycle:** Proposed, scheduled, entered, adjusted, completed, shortened, extended, or superseded.
- **Relationships:** Belongs to a Plan, contains Weeks, advances Objectives, and may be timed relative to a Race.
- **Created by:** Athlete, Coach, or an AI-assisted proposal accepted through coaching judgment.
- **Modified by:** Athlete or authorized Coach through an explicit adjustment.
- **Nature:** Declared boundaries and totals are deterministic; emphasis and timing are coaching judgment, possibly AI-assisted.
- **Examples:** Aerobic base; build; race-specific preparation; taper; post-race transition.

### 5. Training Week

- **Definition:** A planning window, usually seven days, coordinating training demand, disciplines, recovery, and availability.
- **Purpose:** Provides the main rhythm for reviewing adherence, progression, and upcoming commitments.
- **Lifecycle:** Planned, adjusted, underway, reviewed, and closed; a recovery or incomplete week remains valid history.
- **Relationships:** Sits within a Cycle, groups Planned Workouts by time, and frames weekly Activities, Metrics, and Recommendations.
- **Created by:** The plan author or planning process.
- **Modified by:** Athlete or authorized Coach; accepted adjustments may reschedule its contents.
- **Nature:** Calendar membership and summaries are deterministic; interpretation is human or AI-generated judgment.
- **Examples:** A build week with swim, bike, run, and strength; a reduced-load recovery week.

### 6. Workout Template

- **Definition:** A reusable, unscheduled description of a workout's purpose and structure.
- **Purpose:** Preserves repeatable session design without tying it to one Athlete, date, or execution.
- **Lifecycle:** Authored, refined, reused, meaningfully versioned, or retired; past uses retain the prescription understood then.
- **Relationships:** Can become many Planned Workouts and may target Objectives, sports, Zones, or skills.
- **Created by:** Athlete, Coach, or reviewed AI-assisted authoring process.
- **Modified by:** Its author or authorized curator; changes do not rewrite prior uses.
- **Nature:** Declared structure is deterministic; rationale or variants may be human- or AI-authored.
- **Examples:** Bike 4 x 8 minutes near threshold; swim drills plus aerobic sets; foundational strength circuit.

### 7. Planned Workout

- **Definition:** A specific training intention assigned to an Athlete, usually with a time, sport, purpose, and structure.
- **Purpose:** States what the Athlete intends to do and why before execution.
- **Lifecycle:** Drafted, scheduled, adjusted, completed in intent, skipped, cancelled, or rescheduled; original and revised intent remain distinguishable.
- **Relationships:** Belongs to a Plan or stands alone; may derive from a Template and be evaluated through a Workout Execution.
- **Created by:** Athlete, authorized Coach, or accepted assisted-planning proposal.
- **Modified by:** Athlete or authorized Coach, including through an accepted Decision.
- **Nature:** Prescription and schedule are declared facts. Generation may be human or AI-assisted but requires accountable acceptance.
- **Examples:** Tuesday easy run for 45 minutes; Saturday long ride with tempo blocks; a recovery swim moved to Thursday.

### 8. Completed Activity

- **Definition:** A factual account that physical activity occurred, based on an Athlete report or external recording source.
- **Purpose:** Preserves training history independently from what was planned.
- **Lifecycle:** Recorded or imported, validated, supplemented with Athlete-owned context, corrected at the source when appropriate, and optionally deleted by explicit choice.
- **Relationships:** May support an Execution, Metrics, Recovery context, Recommendations, and Decisions; it never becomes a Planned Workout.
- **Created by:** Athlete or an authorized recording source acting for the Athlete.
- **Modified by:** Imported facts are immutable within TriCoach AI; Athlete-owned context may be added without overwriting them.
- **Nature:** Observed facts and direct calculations are deterministic subject to source quality; interpretation is separate.
- **Examples:** A recorded 10 km run; a manually reported strength session; a device-recorded multisport race.

### 9. Workout Execution

- **Definition:** The coaching interpretation of how a Planned Workout was or was not carried out.
- **Purpose:** Keeps planned intent and completed evidence separate while enabling adherence and quality assessment.
- **Lifecycle:** Unassessed, tentatively associated, confirmed, evaluated, revised with better evidence, or unlinked; a skipped execution needs no Activity.
- **Relationships:** References one Planned Workout, zero or more Activities, Athlete feedback, Zones, and context.
- **Created by:** Athlete, Coach, or a deterministic matching suggestion handled under a confidence policy.
- **Modified by:** Athlete or authorized Coach; automated suggestions may be accepted, rejected, or reversed.
- **Nature:** Matching and comparisons can be deterministic. Whether purpose was achieved is uncertain coaching interpretation, potentially AI-assisted.
- **Examples:** A tempo run assessed as partially completed; a swim marked skipped; a brick associated with bike and run recordings.

### 10. Race

- **Definition:** A scheduled competitive or personally significant event for which an Athlete may prepare and record an outcome.
- **Purpose:** Gives planning a concrete date, discipline context, priority, and meaning.
- **Lifecycle:** Considered, scheduled, prioritized, changed, completed, cancelled, or withdrawn from.
- **Relationships:** May anchor a Plan, motivate Objectives, contain Race Goals, and influence cycles, tapering, and Recommendations.
- **Created by:** Athlete or authorized Coach with Athlete agreement.
- **Modified by:** Athlete; a Coach may propose priority or planning changes.
- **Nature:** Event details are declared facts; priority and preparation implications are coaching judgment.
- **Examples:** A sprint triathlon used as practice; an A-priority long-course race.

### 11. Race Goal

- **Definition:** A desired outcome, experience, or process associated with a Race.
- **Purpose:** Clarifies success beyond merely finishing and prevents unstated expectations.
- **Lifecycle:** Proposed, refined, committed to, reviewed, achieved, missed, or retired as circumstances change.
- **Relationships:** Belongs to a Race, informs Objectives and plan design, and is reviewed using race evidence and context.
- **Created by:** Primarily the Athlete, often with Coach guidance.
- **Modified by:** Athlete; Coach or AI may propose refinements that require acceptance.
- **Nature:** Declared intent. Feasibility analysis may be deterministic and interpretive; AI estimates are not facts.
- **Examples:** Finish comfortably; execute even pacing; complete the swim calmly; target a time range under suitable conditions.

### 12. Training Objective

- **Definition:** A desired adaptation, capability, habit, or skill that training seeks to develop.
- **Purpose:** Explains why training exists and guides session selection and evaluation.
- **Lifecycle:** Identified, prioritized, pursued, reassessed, achieved sufficiently, deferred, or replaced.
- **Relationships:** Informs Plans, Cycles, Templates, Workouts, Metrics, and Recommendations; may support a Race Goal without requiring a Race.
- **Created by:** Athlete and Coach, or proposed by analysis for review.
- **Modified by:** Athlete or authorized Coach through explicit reprioritization.
- **Nature:** Declared intent. Progress indicators may be deterministic; adaptation claims remain evidence-based interpretation.
- **Examples:** Improve aerobic durability; build swim consistency; maintain strength during race preparation.

### 13. Training Zone

- **Definition:** An Athlete-specific range describing intended or observed intensity through heart rate, power, pace, speed, swimming pace, or thresholds.
- **Purpose:** Creates a shared intensity language for prescription and analysis.
- **Lifecycle:** Established using a named method and evidence, effective for a period, reviewed, replaced, and retained for historical interpretation.
- **Relationships:** Guides Templates and Planned Workouts and contextualizes Activities, Executions, and Metrics.
- **Created by:** Athlete or Coach from a test, estimate, or accepted method; calculation may produce boundaries.
- **Modified by:** Athlete or Coach when new evidence justifies a new effective period; history is not overwritten.
- **Nature:** Boundaries are deterministic given inputs and method. Method selection and uncertain threshold interpretation are coaching judgment.
- **Examples:** Cycling zones based on FTP; running zones based on threshold heart rate; swim zones based on CSS.

### 14. Recovery

- **Definition:** The ongoing process through which an Athlete responds and adapts after training and life stress.
- **Purpose:** Balances stimulus with restoration so progress is sustainable and safety concerns are visible.
- **Lifecycle:** Continuously changes; it is observed through trends, reports, and responses rather than created once.
- **Relationships:** Informed by Wellness, Fatigue, sleep, soreness, pain, illness, and load; influences Readiness, Recommendations, and Decisions.
- **Created by:** Recovery is a physiological and psychological process, not authored by the product.
- **Modified by:** No actor edits it as a fact; behavior and circumstances influence it, while observations may be corrected.
- **Nature:** Neither directly deterministic nor AI-derived. Measurements are evidence; interpretations remain uncertain.
- **Examples:** Restoring after a long ride; poorer recovery during high stress; improved response during a recovery week.

### 15. Wellness

- **Definition:** Athlete-reported or observed day-to-day physical and psychological context relevant to training.
- **Purpose:** Adds context that workout recordings alone cannot capture.
- **Lifecycle:** Reported for a time, optionally corrected, and retained as history; missing context is not inferred.
- **Relationships:** Includes sleep, soreness, stress, mood, pain, illness, and subjective Fatigue; informs Recovery and Readiness.
- **Created by:** Primarily Athlete; an authorized source may contribute clearly identified observations.
- **Modified by:** Athlete may correct their report; one source never silently overwrites another.
- **Nature:** A report is a fact about what was reported, not an objective medical fact. Summaries may be deterministic; AI interpretation is labeled.
- **Examples:** Sleep quality 2/5; high work stress; mild leg soreness; no illness symptoms reported.

### 16. Fatigue

- **Definition:** Experienced or inferred reduction in capacity associated with training, recovery, health, and life stress.
- **Purpose:** Helps distinguish productive loading from strain that may warrant caution.
- **Lifecycle:** Rises and falls, is reported or estimated, and is interpreted through trends rather than one value.
- **Relationships:** Contributes to Recovery and Readiness and relates to Wellness, load, Executions, and Recommendations.
- **Created by:** Subjective Fatigue is Athlete-reported; estimated Fatigue comes from a declared model.
- **Modified by:** Athlete corrects reports; estimates change only with evidence or method version.
- **Nature:** Reports are testimony; modeled estimates are deterministic; AI commentary is interpretation.
- **Examples:** Fatigue 8/10; an acute-load trend suggesting elevated accumulated strain.

### 17. Readiness

- **Definition:** A contextual assessment of how prepared an Athlete appears for a particular demand at a particular time.
- **Purpose:** Supports conservative choices without presenting one score as certainty or medical clearance.
- **Lifecycle:** Assessed for a moment or session, expires quickly, and changes with fresh evidence.
- **Relationships:** Synthesizes Recovery, Wellness, Fatigue, recent training, safety signals, proposed demand, and uncertainty.
- **Created by:** Deterministic model, Athlete or Coach judgment, or labeled AI interpretation.
- **Modified by:** Recomputed or reassessed from new evidence; historical assessments retain original context.
- **Nature:** Always derived, never a direct fact. Deterministic and AI forms must be distinguished and explained.
- **Examples:** Low confidence because wellness is missing; ready for easy work but not intensity; a stop-training safety flag.

### 18. Recommendation

- **Definition:** A non-binding, evidence-based proposal for Athlete or Coach consideration.
- **Purpose:** Presents a possible action or question without changing plans, goals, or facts.
- **Lifecycle:** Generated, presented, reviewed, accepted, rejected, deferred, expired, or superseded.
- **Relationships:** References evidence across plans, executions, activities, wellness, recovery, metrics, objectives, and races; may lead to a Decision.
- **Created by:** Coach, deterministic rule, or AI coaching process.
- **Modified by:** Author may clarify it; substantive changes create a distinguishable proposal. Athlete controls acceptance.
- **Nature:** Explicitly deterministic, human-authored, or AI-derived. AI output is interpretation, not fact.
- **Examples:** Move intervals after worsening fatigue; keep the plan unchanged after one poor session; ask for missing pain context.

### 19. Coaching Decision

- **Definition:** An accountable choice to act, not act, or seek information in response to evidence.
- **Purpose:** Separates suggestions from authorized outcomes and preserves reasoning behind meaningful changes.
- **Lifecycle:** Considered, made, applied where authorized, reviewed, and possibly superseded; never retroactively rewritten.
- **Relationships:** Must reference evidence, may respond to a Recommendation, and can adjust future intent without changing historical facts.
- **Created by:** Athlete or authorized human Coach. Safety rules may block unsafe options but do not impersonate consent.
- **Modified by:** A made Decision is preserved; changes are new superseding Decisions.
- **Nature:** Human-accountable judgment. AI may inform it but cannot be the accountable decision-maker.
- **Examples:** Replace intervals with rest after illness evidence; reject a volume increase; await another recovery check-in.

### 20. Equipment

- **Definition:** Gear whose characteristics, condition, and usage matter to an Athlete's training or racing.
- **Purpose:** Adds practical context, supports maintenance awareness, and explains session differences.
- **Lifecycle:** Added, used, maintained, changed, retired, lost, or replaced; historical usage remains meaningful.
- **Relationships:** Used in Planned Workouts, Activities, and Races; may contextualize Metrics and Recommendations.
- **Created by:** Athlete; a provider may suggest an item for Athlete confirmation.
- **Modified by:** Athlete, with optional Coach visibility but no ownership control.
- **Nature:** Identity and usage are declared or observed facts. Maintenance intervals may be deterministic; AI suggestions are advisory.
- **Examples:** Road bike with power meter; trail shoes nearing a replacement threshold; open-water wetsuit.

### 21. Performance Metric

- **Definition:** A defined measurement or calculation describing training, execution, recovery context, or progress.
- **Purpose:** Makes evidence comparable without turning a number into a complete coaching conclusion.
- **Lifecycle:** Observed or calculated for a period, method, and evidence set; superseded only by source correction or distinguishable recalculation.
- **Relationships:** Summarizes Activities, Executions, Weeks, Zones, Recovery inputs, Objectives, or Races and supports Recommendations and Decisions.
- **Created by:** Recording source, Athlete observation, or deterministic calculation.
- **Modified by:** Source correction or versioned recalculation; AI never edits factual values.
- **Nature:** Observed or deterministic, never AI-created as fact. AI may interpret it with uncertainty.
- **Examples:** Weekly run duration; cycling zone time; plan adherence; session RPE load; a versioned load trend.

## Business rules

1. A Completed Activity never becomes a Planned Workout; each retains its identity and meaning.
2. A Workout Execution relates intention to evidence but never merges or rewrites either side.
3. A Recommendation never modifies domain information directly. Material action requires an accountable Coaching Decision.
4. Every Coaching Decision references its responsible human actor, outcome, and the evidence available when made.
5. Imported provider facts are immutable within TriCoach AI. Corrections come from the source or separate Athlete-owned context without overwriting provenance.
6. AI interpretations are never treated as observations, measurements, diagnoses, or Athlete statements.
7. A Training Plan may evolve. Revisions preserve prior intent and the reason for material change.
8. Wellness reports never overwrite imported physiological observations, and imported observations never overwrite Athlete testimony.
9. Every Recommendation is reproducible in provenance: its evidence, rules, assumptions, uncertainty, and generation approach can be reconstructed. This does not promise identical AI wording.
10. Missing, stale, conflicting, or low-quality evidence is explicit and lowers confidence; it is never silently invented.
11. Training Zones apply for defined periods. New Zones do not reinterpret history without explicit, traceable recalculation.
12. A Race Goal belongs to the Athlete. A Coach or AI may propose refinement but cannot silently replace it.
13. A skipped Planned Workout never creates a fictional Completed Activity.
14. Planned-to-completed associations are explicit and reversible; multisport execution may use several Activities.
15. One unusual workout or wellness observation does not justify an aggressive plan change.
16. Safety overrides performance optimization. TriCoach AI never diagnoses or recommends training through chest pain, severe symptoms, acute injury, or illness.
17. Readiness is time-specific, evidence-dependent, advisory, and never medical clearance.
18. Performance Metrics retain method, period, coverage, and limitations; different sports and methods are not assumed equivalent.
19. Provider disconnection ends authorization but does not alter the meaning of previously imported Activities.
20. Material plan changes require Athlete visibility and acceptance, regardless of who or what proposed them.

## Domain events

Domain events state that something meaningful happened. They are past-tense business facts, not commands, and imply no implementation mechanism.

### WorkoutCompleted

- **Trigger:** Athlete confirmation or credible activity evidence establishes that a workout occurred.
- **Consequences:** Execution, adherence, volume, and recovery context may be assessed.
- **Consumers:** Athlete, Coach, weekly analysis, recovery assessment, recommendation and objective review.

### WorkoutSkipped

- **Trigger:** A Planned Workout passes without execution or is explicitly marked skipped.
- **Consequences:** Missed intent and reason remain visible; no Activity is fabricated.
- **Consumers:** Athlete, Coach, adherence analysis, plan review, and recommendations.

### RaceCreated

- **Trigger:** The Athlete establishes a meaningful future or completed Race.
- **Consequences:** Goals and priority can be defined; planning may evaluate timing and specificity.
- **Consumers:** Planning, cycle design, calendar review, objective setting, Athlete, and Coach.

### PlanAdjusted

- **Trigger:** An authorized Coaching Decision changes future training intent.
- **Consequences:** A new plan state becomes current while prior intent and rationale remain visible.
- **Consumers:** Athlete, Coach, workout planning, calendar review, comparisons, and decision review.

### RecommendationGenerated

- **Trigger:** Coach, deterministic rule, or AI process produces a proposal from identified evidence.
- **Consequences:** It becomes reviewable but changes nothing directly; provenance and uncertainty accompany it.
- **Consumers:** Athlete, authorized Coach, explanation review, and Coaching Decision process.

### RecoveryUpdated

- **Trigger:** New recovery evidence arrives or the Athlete corrects a report.
- **Consequences:** Recovery and Readiness may be reassessed without silently rewriting earlier interpretations.
- **Consumers:** Athlete, Coach, safety rules, readiness, recommendations, and plan review.

### ProviderConnected

- **Trigger:** Athlete grants sufficient authorization and external identity is confirmed.
- **Consequences:** Provider observations may become available under consent; connection alone implies no Activity.
- **Consumers:** Athlete consent awareness and future activity acquisition.

### ProviderDisconnected

- **Trigger:** Athlete ends authorization or remote revocation is confirmed.
- **Consequences:** New observations stop; existing Activities remain unless separately deleted.
- **Consumers:** Athlete consent awareness and provider-dependent work.

### WellnessRecorded

- **Trigger:** Athlete reports wellness for a defined time.
- **Consequences:** Recovery and Readiness may be reassessed without treating the report as diagnosis.
- **Consumers:** Athlete, Coach, recovery analysis, safety rules, and recommendations.

### CoachingDecisionMade

- **Trigger:** Athlete or authorized Coach chooses an outcome using referenced evidence.
- **Consequences:** Accountable history is established and may authorize a separate plan adjustment.
- **Consumers:** Athlete, Coach, planning, recommendation follow-up, and later review.

### TrainingZoneChanged

- **Trigger:** Accepted evidence or method establishes a Zone for a new effective period.
- **Consequences:** Future prescription uses it; history retains the Zone applicable at the time.
- **Consumers:** Planning, activity analysis, Metrics, Athlete, and Coach.

### RaceCompleted

- **Trigger:** Athlete completes a Race and outcome evidence becomes available.
- **Consequences:** Goals may be reviewed, Recovery context changes, and Objectives may be reconsidered.
- **Consumers:** Athlete, Coach, goal review, recovery planning, and future plan design.

## Glossary

- **Adherence:** Degree to which execution corresponded with intent; not a moral judgment or universal pass/fail score.
- **AI-assisted:** Proposed or interpreted by AI while labeled, evidence-based, reviewable, and subordinate to human authority.
- **Athlete-owned context:** Athlete-controlled reports such as RPE, notes, preferences, goals, and Wellness.
- **Coaching evidence:** Traceable facts, reports, calculations, context, and uncertainty considered in guidance.
- **Consent:** Athlete's explicit, scoped, revocable permission for Coach or provider participation.
- **CSS:** Critical Swim Speed, a method-dependent sustainable swim pace estimate.
- **Deterministic:** Produces the same result from the same defined inputs and method version.
- **Effective period:** Time span during which a changing Zone or context applies.
- **Evidence coverage:** Proportion of relevant time or meaning supported by usable evidence.
- **Execution:** Relationship between intended and actual training, including skipped or partial work.
- **External load:** Work performed, such as duration, distance, power, pace, elevation, sets, or repetitions.
- **Fatigue:** Reported or modeled reduction in capacity; not a diagnosis or synonym for one load score.
- **FTP:** Functional Threshold Power, a method-dependent estimate used to contextualize cycling power.
- **Goal:** Desired outcome or experience; intent rather than prediction.
- **Immutable source fact:** Provider-originated observation protected from silent alteration.
- **Intensity:** Training demand described through a declared reference such as heart rate, power, pace, speed, or RPE.
- **Internal response:** Athlete's physiological or perceived response, such as heart rate or RPE.
- **Lifecycle:** Meaningful business states and transitions a concept experiences.
- **Metric:** Defined observation or calculation with method, period, units, evidence, and limitations.
- **Objective:** Capability, adaptation, habit, or skill training seeks to develop.
- **Plan revision:** New state of future intent preserving previous intent and reason for change.
- **Prescription:** Declared purpose, structure, intensity, and constraints of intended training.
- **Provenance:** Where evidence came from, when it applied, and how it was produced or changed.
- **Readiness:** Temporary derived assessment for a specific demand; advisory, not medical clearance.
- **Recommendation:** Reviewable proposal that cannot directly change domain information.
- **Recovery:** Continuing process of responding and adapting after training and life stress.
- **RPE:** Athlete-reported Rating of Perceived Exertion on a declared scale.
- **Session RPE:** Session-level RPE, sometimes combined with duration using a declared internal-load method.
- **Training load:** Model-dependent training demand description, not direct fitness, fatigue, health, or Readiness.
- **Uncertainty:** Limitation from missing, stale, conflicting, low-quality, or interpretation-dependent evidence.
- **Wellness:** Day-to-day training context, distinct from medical diagnosis.
- **Workout purpose:** Intended adaptation, skill, recovery effect, or race-specific outcome.
- **Zone:** Athlete-specific intensity range established by a named method for an effective period.

## Remaining conceptual questions

1. What plan revision history is useful without overwhelming an amateur Athlete?
2. Which Objectives are shared across sports and which remain discipline-specific?
3. Which plan decisions may be delegated to a human Coach, and which always require direct Athlete confirmation?
4. What confidence permits automatic Workout Execution association before Athlete confirmation?
5. Which deterministic Readiness assessments are useful without false precision or medical interpretation?
6. How should one Execution represent bricks, multisport races, duplicate recordings, and split Activities?
7. What evidence history is needed to reproduce a Recommendation after methods or AI models change?
8. How should shared Coach-authored Templates be governed when revised or reused across Athletes?
