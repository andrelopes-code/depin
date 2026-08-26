"""Reusable binding collections that compose into containers."""

from depin._core.bindings import BindingCollector


class Registry(BindingCollector):
    """A reusable, composable collection of bindings.

    A ``Registry`` holds the same kind of bindings as a `Container` but performs
    no validation and no resolution: it is a module-level catalogue you declare
    once and feed into one or more containers. Registries compose with ``|``, and
    a container accepts any number of them at construction.

    Args:
        name: Optional label, used only to identify the registry; combining two
            named registries keeps the first non-empty name.

    Example:
        ```pycon
        >>> from depin import Container, Registry
        >>> class Logger: ...
        >>> class Metrics: ...
        >>> infra = Registry('infra').bind(Logger)
        >>> obs = Registry('obs').bind(Metrics)
        >>> di = Container(infra | obs).freeze()
        >>> isinstance(di[Logger], Logger) and isinstance(di[Metrics], Metrics)
        True

        ```
    """

    __slots__ = ('name',)

    def __init__(self, name: str = '') -> None:
        super().__init__()
        self.name = name

    def __or__(self, other: 'Registry') -> 'Registry':
        """Combine two registries into a new one, concatenating their bindings.

        Neither operand is modified. The result takes this registry's name, or the
        other's when this one is unnamed.
        """
        return Registry(name=self.name or other.name).include(self, other)
