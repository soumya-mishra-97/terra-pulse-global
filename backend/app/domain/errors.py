class DomainError(Exception):
    """Base class for expected, user-safe domain failures."""


class CalculationError(DomainError):
    pass


class ImportValidationError(DomainError):
    def __init__(self, message: str, rejected: list[dict] | None = None) -> None:
        super().__init__(message)
        self.rejected = rejected or []


class DuplicateImportError(DomainError):
    pass


class NotFoundError(DomainError):
    pass


class DataUnavailableError(DomainError):
    pass
