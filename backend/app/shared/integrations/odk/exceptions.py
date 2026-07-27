class ODKError(Exception):
    """Base exception for ODK integration errors."""


class ODKAuthError(ODKError):
    """Authentication/credential related error."""


class ODKAuthFailed(ODKAuthError):
    """Login to ODK Central failed (invalid credentials)."""


class ODKAuthorizationError(ODKError):
    """Authorization failed for an ODK API request."""


class ODKAPIError(ODKError):
    """Generic API error returned by ODK Central."""

    def __init__(self, status_code: int, detail: str | None = None):
        super().__init__(f"ODK API error {status_code}: {detail or ''}")
        self.status_code = status_code
        self.detail = detail


class ODKNotFound(ODKAPIError):
    """Requested ODK resource was not found."""


class ODKConnectionError(ODKError):
    """Network/connection failure when contacting ODK Central."""
