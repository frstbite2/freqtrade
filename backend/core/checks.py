"""Small runtime checks that also tell the type checker what is known."""


def need[T](value: T | None, what: str = "value") -> T:
    """Return `value`, which the caller knows is present; fail loudly if that is ever wrong."""
    if value is None:
        raise ValueError(f"missing {what}")
    return value
