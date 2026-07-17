class KBError(Exception):
    """Base application exception."""


class UnsupportedSourceTypeError(KBError):
    """Raised when no parser is registered for a source type."""


class FileStorageError(KBError):
    """Raised when object storage operations fail."""


class IngestionError(KBError):
    """Raised by the worker when an ingestion attempt fails.

    Re-raised out of `process_ingestion` so the queue engine can drive its retry
    policy; the asset/job records already carry the failed step and error detail.
    """
