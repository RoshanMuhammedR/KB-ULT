class KBError(Exception):
    """Base application exception."""


class UnsupportedSourceTypeError(KBError):
    """Raised when no parser is registered for a source type."""


class FileStorageError(KBError):
    """Raised when object storage operations fail."""
