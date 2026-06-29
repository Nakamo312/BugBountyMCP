from __future__ import annotations

from collections.abc import Sequence

from .cli_handlers import GraphProjectorCli
from .cli_parser import build_parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return GraphProjectorCli().run(args)
