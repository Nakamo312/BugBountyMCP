from pathlib import Path


PROGRAM_SERVICE = Path("src/api/application/services/program.py")


def test_program_service_uses_single_full_response_mapper() -> None:
    source = PROGRAM_SERVICE.read_text(encoding="utf-8")

    assert "def _program_full_response" in source
    assert source.count("ProgramFullResponseDTO(") == 1
    assert source.count("ScopeRuleResponseDTO(") == 1
    assert source.count("RootInputResponseDTO(") == 1
