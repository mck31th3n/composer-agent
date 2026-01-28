"""Custom exceptions for musicdiff."""


class MusicDiffError(Exception):
    """Base exception for musicdiff."""

    code: str = "E_UNKNOWN"


class ParseError(MusicDiffError):
    """Failed to parse input file."""

    def __init__(self, message: str, file_type: str = "unknown") -> None:
        super().__init__(message)
        self.code = f"E_{file_type.upper()}_PARSE"


class AlignmentError(MusicDiffError):
    """Failed to align events."""

    code = "E_ALIGNMENT"


class ValidationError(MusicDiffError):
    """Output failed schema validation."""

    code = "E_VALIDATION"
