from __future__ import annotations

from .projection_contract_models import ProjectionContract


def validate_projection_contract_inventory(contracts: tuple[ProjectionContract, ...]) -> None:
    names = tuple(contract.name for contract in contracts)
    if len(names) != len(set(names)):
        raise ValueError("projection contract inventory contains duplicate names")
    by_name = {contract.name: contract for contract in contracts}
    for contract in contracts:
        for source_projection in contract.source_projections:
            if source_projection == contract.name:
                raise ValueError(f"{contract.name} cannot depend on itself")
            if source_projection not in by_name:
                raise ValueError(
                    f"{contract.name} depends on unknown source projection {source_projection}"
                )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str, stack: tuple[str, ...]) -> None:
        if name in visited:
            return
        if name in visiting:
            cycle = " -> ".join((*stack, name))
            raise ValueError(f"projection contract dependency cycle detected: {cycle}")
        visiting.add(name)
        for dependency in by_name[name].source_projections:
            visit(dependency, (*stack, name))
        visiting.remove(name)
        visited.add(name)

    for name in names:
        visit(name, ())
