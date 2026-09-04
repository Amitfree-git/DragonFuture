class FuturesAgentError(Exception):
    """Base exception for the futures market analyst."""


class DataNotFoundError(FuturesAgentError):
    """Raised when requested market data or contract metadata does not exist."""


class InsufficientDataError(FuturesAgentError):
    """Raised when a market context cannot be constructed safely."""


class PersistenceError(FuturesAgentError):
    """Raised when persistence cannot preserve the required invariants."""


class NarrativeValidationError(FuturesAgentError):
    """Raised when generated narrative is not grounded in supplied evidence."""
