from __future__ import annotations

from api.infrastructure.runners.cli_specs.discovery import DISCOVERY_SPECS
from api.infrastructure.runners.cli_specs.dns import DNS_SPECS
from api.infrastructure.runners.cli_specs.http import HTTP_SPECS
from api.infrastructure.runners.cli_specs.js import JS_SPECS
from api.infrastructure.runners.cli_specs.network import NETWORK_SPECS

_ALL_SPECS = (*DISCOVERY_SPECS, *DNS_SPECS, *HTTP_SPECS, *JS_SPECS, *NETWORK_SPECS)
CLI_TOOL_SPECS = {spec.name: spec for spec in _ALL_SPECS}
