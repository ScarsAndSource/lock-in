"""
Domain-level exceptions. Routers and services raise these; main.py's
exception handlers translate them to HTTP responses. Nothing in this app
should let an unexpected condition fall through to a bare 500 with no
context, and nothing should catch-and-ignore an error just to keep a
request "succeeding" -- per the project's own no-silently-swallowed-errors
standard.
"""
from __future__ import annotations


class LockinError(Exception):
    """Base class for all domain-level errors in this app."""


class NotFoundError(LockinError):
    """
    Raised when a resource doesn't exist OR doesn't belong to the requesting
    user. Deliberately the same exception for both cases -- returning a
    different error for "doesn't exist" vs "exists but isn't yours" would
    let a caller enumerate other users' habit IDs by timing or response
    shape, which is a real information leak for a personal-data app like
    this one.
    """


class ValidationError(LockinError):
    """Raised for domain-rule violations that aren't caught by Pydantic's
    schema validation (e.g. a cross-field consistency rule)."""
