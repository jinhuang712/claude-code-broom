"""What a setter's name is, in each language's naming (decision 042): a setter's boolean parameter is no flag, as its
name says what the boolean sets, so the call doesn't read `f(x, true)`. Each language's reader gets the name from its
syntax tree and asks here."""

from __future__ import annotations


def camel_setter(name: str) -> bool:
    """Whether `name` is a setter's in camel case (Go, Swift, TS/JS): `Set` or `set` alone or before a capital, as
    `SetKeepAlivesEnabled` or `setEnabled`, never `settle`."""
    rest = next((name[len(prefix):] for prefix in ("Set", "set") if name.startswith(prefix)), None)
    return rest is not None and (not rest or rest[0].isupper())


def snake_setter(name: str) -> bool:
    """Whether `name` is a setter's in snake case (Python, Rust): `set` alone or before an underscore, as
    `set_enabled`, never `settle`."""
    return name == "set" or name.startswith("set_")
