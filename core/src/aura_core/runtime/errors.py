class BackendUnavailableError(Exception):
    """Raised when the inference backend cannot be reached."""


class BackendInvalidResponseError(Exception):
    """Raised when the inference backend returns an invalid response."""