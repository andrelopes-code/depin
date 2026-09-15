"""Build and run a container from an explicitly imported manifest.

Run with ``python -m examples.declarative_discovery.main``.
"""

from depin import Container, FrozenContainer
from examples.declarative_discovery.manifest import manifest
from examples.declarative_discovery.providers import Greeter


def build() -> FrozenContainer:
    return Container(manifest).freeze()


def main() -> None:
    di = build()
    try:
        print(di[Greeter].render('depin'))
    finally:
        di.close()


if __name__ == '__main__':
    main()
