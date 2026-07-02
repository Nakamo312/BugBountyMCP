from api.application.pipeline.extractors import default_target_extractor, normalize_targets


def test_normalize_targets_flattens_nested_action_targets():
    assert normalize_targets([["a.wb.ru"], ["https://auth.wb.ru"]]) == [
        "a.wb.ru",
        "https://auth.wb.ru",
    ]


def test_normalize_targets_extracts_common_object_values():
    assert normalize_targets([{"host": "auth.wb.ru"}, {"url": "https://a.wb.ru"}]) == [
        "auth.wb.ru",
        "https://a.wb.ru",
    ]


def test_default_target_extractor_returns_strings_for_legacy_nested_targets():
    assert default_target_extractor({"targets": [["a.wb.ru"]]}) == ["a.wb.ru"]
