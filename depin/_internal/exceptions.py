from io import StringIO
from typing import Any, Literal


class MissingProviderError(RuntimeError):
    pass


class UnexpectedCoroutineError(RuntimeError):
    pass


class CircularDependencyError(Exception):
    def __init__(self, visited: dict[Any, Literal[True]], source: Any) -> None:
        dependency_graph_string = self._get_dependency_graph_string(visited, source)
        super().__init__(f'Circular dependency detected:\n{dependency_graph_string}')

    def _get_dependency_graph_string(self, visited: dict[Any, Literal[True]], source: Any) -> str:
        builder = StringIO()

        visited_sources = list(visited.keys()) + [str(source)]

        for i, v in enumerate(visited_sources):
            tab_level = i * 4

            if i == 0:
                builder.write('\n')

            if i != 0:
                builder.write(' ' * tab_level + ':\n')
                builder.write(' ' * tab_level + ':\n')

            if i == len(visited):
                builder.write(f'{" " * tab_level} {v} \x1b[31m  <- Circular dependency detected!\x1b[0m\n\n')
            else:
                builder.write(f'{" " * tab_level} {v}\n')

        return builder.getvalue()
