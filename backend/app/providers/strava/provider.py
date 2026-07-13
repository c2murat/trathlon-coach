from app.providers.base import Provider


class StravaProvider(Provider):
    """Static metadata describing the planned Strava adapter.

    The class intentionally has no HTTP client, OAuth behavior, credentials,
    secrets, persistence access, webhook handling, or synchronization logic.
    Feature names describe the adapter's planned capabilities and must not be
    interpreted as implemented runtime behavior.
    """

    provider_name = "strava"
    display_name = "Strava"
    supported_features = frozenset(
        {
            "oauth",
            "historical_activity_import",
            "activity_webhooks",
            "token_refresh",
        }
    )
    supported_activity_types = frozenset(
        {
            "swimming",
            "cycling",
            "running",
            "strength",
            "other",
        }
    )

