"""Ordered, independently enabled extension modules."""
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ModuleResult:
    speech: str
    error: bool = False


# None is the explicit NOT_HANDLED / PASS result.
class ExtensionModule(Protocol):
    name: str

    def can_handle(self, request: Any) -> bool: ...

    async def handle(self, request: Any) -> ModuleResult | None: ...


class ModuleManager:
    def __init__(self, modules: list[ExtensionModule]) -> None:
        names = [module.name for module in modules]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate module names")
        self.modules = tuple(modules)

    async def handle(self, request: Any) -> ModuleResult | None:
        for module in self.modules:
            if module.can_handle(request):
                result = await module.handle(request)
                if result is not None:
                    return result
        return None
