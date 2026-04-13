"""Tests for JWT-based brand claim verification."""

import base64
import time

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


def _generate_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, public_pem


def _make_token(private_key, brand="test_brand", exp_offset=3600, issuer="test", audience="chatbot"):
    now = int(time.time())
    payload = {
        "brand": brand,
        "iat": now,
        "exp": now + exp_offset,
        "iss": issuer,
        "aud": audience,
    }
    return pyjwt.encode(payload, private_key, algorithm="RS256")


class TestBrandJWT:

    def setup_method(self):
        self.private_key, self.public_pem = _generate_keypair()
        self.public_key = self.private_key.public_key()

    def test_valid_token_extracts_brand(self):
        token = _make_token(self.private_key, brand="acme")
        claims = pyjwt.decode(token, self.public_key, algorithms=["RS256"], audience="chatbot")
        assert claims["brand"] == "acme"

    def test_expired_token_rejected(self):
        token = _make_token(self.private_key, exp_offset=-100)
        with pytest.raises(pyjwt.ExpiredSignatureError):
            pyjwt.decode(token, self.public_key, algorithms=["RS256"], audience="chatbot")

    def test_missing_brand_claim(self):
        now = int(time.time())
        token = pyjwt.encode(
            {"iat": now, "exp": now + 3600, "iss": "test", "aud": "chatbot"},
            self.private_key,
            algorithm="RS256",
        )
        claims = pyjwt.decode(token, self.public_key, algorithms=["RS256"], audience="chatbot")
        assert "brand" not in claims

    def test_wrong_audience_rejected(self):
        token = _make_token(self.private_key, audience="wrong")
        with pytest.raises(pyjwt.InvalidAudienceError):
            pyjwt.decode(token, self.public_key, algorithms=["RS256"], audience="chatbot")

    def test_tampered_token_rejected(self):
        token = _make_token(self.private_key, brand="acme")
        tampered = token[:-4] + "XXXX"
        with pytest.raises(pyjwt.InvalidSignatureError):
            pyjwt.decode(tampered, self.public_key, algorithms=["RS256"], audience="chatbot")

    def test_public_key_base64_roundtrip(self):
        encoded = base64.b64encode(self.public_pem).decode()
        decoded_pem = base64.b64decode(encoded).decode("utf-8")
        loaded = serialization.load_pem_public_key(decoded_pem.encode("utf-8"))
        token = _make_token(self.private_key, brand="roundtrip")
        claims = pyjwt.decode(token, loaded, algorithms=["RS256"], audience="chatbot")
        assert claims["brand"] == "roundtrip"
