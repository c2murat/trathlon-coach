# Training frequency configuration

Adds nullable target_sessions_per_week as a total training-session preference including strength. It is constrained to 1..28 and cannot exceed max_sessions_per_week. NULL preserves the legacy setting. Migration 0028 adds the nullable field without applying any migration to real databases during consolidation.

This commit introduces configuration, persistence, API validation and the preferences form. Applying the setting to generated calendars is consolidated with the following distribution commit: its integration tests depend on compatible doubles. Those tests remain intact in the pending working tree.
