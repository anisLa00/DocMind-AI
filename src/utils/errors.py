"""Domain errors that routers translate into HTTP responses."""


class DocMindError(Exception):
    """Base class for application errors."""


class NotFoundError(DocMindError):
    """The requested resource does not exist, or is not visible to the caller."""


class ConflictError(DocMindError):
    """The request conflicts with existing state (e.g. a duplicate email)."""


class ValidationError(DocMindError):
    """The request is well-formed but not acceptable (bad file type, size...)."""


class DocumentNotReadyError(DocMindError):
    """The document exists but has not finished being indexed."""


class LLMError(DocMindError):
    """The language model could not be reached or refused the request."""


class UnsupportedFileTypeError(ValidationError):
    """The uploaded file's extension is not in the allow-list."""


class FileTooLargeError(ValidationError):
    """The uploaded file exceeds MAX_UPLOAD_SIZE_MB."""


class EmbeddingError(DocMindError):
    """The embedding provider could not be reached or returned a bad response."""
