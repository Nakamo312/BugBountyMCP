from api.application.research.sanitizer import sanitize_text


def test_sanitizer_redacts_headers_bearer_tokens_and_json_secrets() -> None:
    source = "\n".join(
        (
            "Authorization: Bearer abc.def.ghi",
            "Cookie: session=secret-cookie",
            "Set-Cookie: refresh=secret-refresh; HttpOnly",
            '{"token":"secret-token","nested":{"api_key":"secret-key"}}',
        )
    )

    sanitized = sanitize_text(source)

    assert "abc.def.ghi" not in sanitized.safe_excerpt
    assert "secret-cookie" not in sanitized.safe_excerpt
    assert "secret-refresh" not in sanitized.safe_excerpt
    assert "secret-token" not in sanitized.safe_excerpt
    assert "secret-key" not in sanitized.safe_excerpt
    assert sanitized.safe_for_llm is True
    assert sanitized.redaction_rules_triggered


def test_sanitizer_limits_preview_before_exposure() -> None:
    sanitized = sanitize_text("x" * 100, limit=16)

    assert sanitized.safe_excerpt == "x" * 16
    assert sanitized.safe_for_llm is True


def test_sanitizer_redacts_secret_from_truncated_json_preview() -> None:
    sanitized = sanitize_text(
        '{"nested":{"token":"secret-value-without-closing-quote',
        limit=128,
    )

    assert "secret-value" not in sanitized.safe_excerpt
    assert '"token":"[redacted]' in sanitized.safe_excerpt
    assert sanitized.safe_for_llm is True
