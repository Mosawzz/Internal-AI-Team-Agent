
class ValidationError(Exception):
    """Raised when input data is missing or invalid."""
    pass


class NotFoundError(Exception):
    """Raised when a requested database record does not exist."""
    pass


class ModelUnavailableError(Exception):
    """Raised when the LLM service is unavailable or times out."""
    pass


class ExtractionError(Exception):
    """Raised when the model output fails schema validation."""
    pass
