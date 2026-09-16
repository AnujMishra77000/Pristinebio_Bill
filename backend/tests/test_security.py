from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.enums import UserRole


def test_argon2_password_hash_verifies_correct_password():
    hashed = hash_password("Correct-Horse-Battery-937")

    assert hashed != "Correct-Horse-Battery-937"
    assert verify_password("Correct-Horse-Battery-937", hashed)
    assert not verify_password("incorrect-password", hashed)


def test_access_and_refresh_tokens_have_distinct_token_types():
    access_token = create_access_token(subject="42", role=UserRole.ADMIN)
    refresh_token = create_refresh_token(subject="42", role=UserRole.ADMIN)

    access_payload = decode_token(access_token, expected_type="access")
    refresh_payload = decode_token(refresh_token, expected_type="refresh")

    assert access_payload["sub"] == "42"
    assert access_payload["role"] == "admin"
    assert access_payload["typ"] == "access"
    assert refresh_payload["sub"] == "42"
    assert refresh_payload["typ"] == "refresh"


def test_refresh_decoder_rejects_access_token():
    access_token = create_access_token(subject="42", role=UserRole.ADMIN)

    try:
        decode_token(access_token, expected_type="refresh")
    except ValueError as exc:
        assert "Invalid token type" in str(exc)
    else:
        raise AssertionError("access token was accepted as refresh token")
