"""Small, deterministic registry supporting primary/secondary providers."""

from collections import defaultdict
from typing import DefaultDict, List

from .base import DataProvider, ProviderKind


class ProviderRegistry:
    def __init__(self):
        self._providers: DefaultDict[ProviderKind, List[DataProvider]] = defaultdict(list)

    def register(self, provider: DataProvider) -> None:
        self._providers[provider.kind].append(provider)

    def providers_for(self, kind: ProviderKind) -> List[DataProvider]:
        return list(self._providers.get(kind, []))
