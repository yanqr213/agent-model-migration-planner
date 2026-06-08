class PlannerError(Exception):
    """Base exception for planner failures."""


class ConfigError(PlannerError):
    """Raised when input configuration is missing or invalid."""


class InputDataError(PlannerError):
    """Raised when prompt, eval, or model input data cannot be loaded."""
