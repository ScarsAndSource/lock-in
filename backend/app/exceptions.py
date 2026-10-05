"""Domain-level exceptions. main.py maps each one to an HTTP response."""
from __future__ import annotations


class LockinError(Exception):
    """Base class for all domain-level errors."""


class NotFoundError(LockinError):
    """Missing OR not owned by the caller -- deliberately indistinguishable."""


class ValidationError(LockinError):
    """Domain-rule violation not caught by Pydantic's schema validation."""


class ConflictError(LockinError):
    """Request is valid but conflicts with current state (e.g. a second active mission)."""


class DataIntegrityError(LockinError):
    """Stored data failed an integrity check (e.g. undecryptable journal). Never swallowed."""


class RateLimitedError(LockinError):
    def __init__(self, retry_after: int):
        super().__init__("Too many requests.")
        self.retry_after = retry_after
