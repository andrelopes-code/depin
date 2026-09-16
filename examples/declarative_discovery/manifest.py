"""The composition root's exact declarative imports."""

from depin import Manifest
from examples.declarative_discovery.providers import providers

manifest = Manifest(__name__, providers)
