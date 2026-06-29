from __future__ import annotations

from .projection_contract_inventory_bipartite import BIPARTITE_PROJECTION_CONTRACTS
from .projection_contract_inventory_primary import PRIMARY_PROJECTION_CONTRACTS
from .projection_contract_models import (
    AlgorithmFamily,
    ProjectionContract,
    SignalAlgorithmContract,
    _contract,
    _signal,
)
from .projection_contract_validation import validate_projection_contract_inventory


EXPECTED_PROJECTION_CONTRACT_NAMES: tuple[str, ...] = (
    "G_asset",
    "G_http",
    "G_identity",
    "G_finding",
    "G_temporal",
    "G_bipartite_endpoint_param",
    "G_bipartite_host_tech",
    "G_bipartite_endpoint_object",
)


PROJECTION_CONTRACTS: tuple[ProjectionContract, ...] = (
    *PRIMARY_PROJECTION_CONTRACTS,
    *BIPARTITE_PROJECTION_CONTRACTS,
)

PROJECTION_CONTRACTS_BY_NAME: dict[str, ProjectionContract] = {
    contract.name: contract for contract in PROJECTION_CONTRACTS
}

PROJECTION_CONTRACT_NAMES: tuple[str, ...] = tuple(
    contract.name for contract in PROJECTION_CONTRACTS
)

if PROJECTION_CONTRACT_NAMES != EXPECTED_PROJECTION_CONTRACT_NAMES:
    raise ValueError("projection contract inventory does not match expected names")

validate_projection_contract_inventory(PROJECTION_CONTRACTS)


def list_projection_contracts() -> tuple[ProjectionContract, ...]:
    return PROJECTION_CONTRACTS


def projection_contract_names() -> tuple[str, ...]:
    return PROJECTION_CONTRACT_NAMES


def get_projection_contract(name: str) -> ProjectionContract:
    try:
        return PROJECTION_CONTRACTS_BY_NAME[name]
    except KeyError as exc:
        raise KeyError(f"unknown typed projection contract: {name}") from exc


__all__ = (
    "AlgorithmFamily",
    "EXPECTED_PROJECTION_CONTRACT_NAMES",
    "PROJECTION_CONTRACT_NAMES",
    "PROJECTION_CONTRACTS",
    "PROJECTION_CONTRACTS_BY_NAME",
    "ProjectionContract",
    "SignalAlgorithmContract",
    "get_projection_contract",
    "list_projection_contracts",
    "projection_contract_names",
    "validate_projection_contract_inventory",
)
