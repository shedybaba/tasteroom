class ApiError(Exception):
    """A user-facing error with an HTTP status; rendered as {"error": message} by the app's handler."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message
