from unittest.mock import MagicMock

import pytest
from starlette.requests import Request

from zotero_mcp.credentials import (
    InvalidCredentialsError,
    MissingCredentialsError,
    ZoteroCredentials,
    resolve_zotero_credentials,
)


class TestZoteroCredentials:
    def test_cache_key_uses_hashed_api_key(self):
        creds = ZoteroCredentials(
            api_key="secret123", library_id="12345", library_type="user"
        )
        assert "secret123" not in creds.cache_key
        assert "12345" in creds.cache_key
        assert "user" in creds.cache_key

    def test_cache_key_different_for_different_keys(self):
        creds1 = ZoteroCredentials(
            api_key="key1", library_id="12345", library_type="user"
        )
        creds2 = ZoteroCredentials(
            api_key="key2", library_id="12345", library_type="user"
        )
        assert creds1.cache_key != creds2.cache_key

    def test_cache_key_same_for_same_credentials(self):
        creds1 = ZoteroCredentials(
            api_key="same_key", library_id="12345", library_type="user"
        )
        creds2 = ZoteroCredentials(
            api_key="same_key", library_id="12345", library_type="user"
        )
        assert creds1.cache_key == creds2.cache_key

    def test_default_library_type_is_user(self):
        creds = ZoteroCredentials(api_key="key", library_id="12345")
        assert creds.library_type == "user"


class TestResolveZoteroCredentials:
    def test_missing_request_raises_error(self):
        with pytest.raises(MissingCredentialsError, match="missing or invalid"):
            resolve_zotero_credentials(None)

    def test_missing_api_key_header(self):
        request = MagicMock(spec=Request)
        request.headers = {
            "x-zotero-library-id": "12345",
            "x-zotero-library-type": "user",
        }
        with pytest.raises(MissingCredentialsError, match="X-Zotero-Api-Key"):
            resolve_zotero_credentials(request)

    def test_missing_library_id_header(self):
        request = MagicMock(spec=Request)
        request.headers = {"x-zotero-api-key": "mykey", "x-zotero-library-type": "user"}
        with pytest.raises(MissingCredentialsError, match="X-Zotero-Library-Id"):
            resolve_zotero_credentials(request)

    def test_empty_api_key_header(self):
        request = MagicMock(spec=Request)
        request.headers = {"x-zotero-api-key": "  ", "x-zotero-library-id": "12345"}
        with pytest.raises(MissingCredentialsError, match="X-Zotero-Api-Key"):
            resolve_zotero_credentials(request)

    def test_empty_library_id_header(self):
        request = MagicMock(spec=Request)
        request.headers = {"x-zotero-api-key": "mykey", "x-zotero-library-id": ""}
        with pytest.raises(MissingCredentialsError, match="X-Zotero-Library-Id"):
            resolve_zotero_credentials(request)

    def test_non_numeric_library_id(self):
        request = MagicMock(spec=Request)
        request.headers = {"x-zotero-api-key": "mykey", "x-zotero-library-id": "abc"}
        with pytest.raises(InvalidCredentialsError, match="numeric"):
            resolve_zotero_credentials(request)

    def test_invalid_library_type(self):
        request = MagicMock(spec=Request)
        request.headers = {
            "x-zotero-api-key": "mykey",
            "x-zotero-library-id": "12345",
            "x-zotero-library-type": "invalid",
        }
        with pytest.raises(InvalidCredentialsError, match="user.*group"):
            resolve_zotero_credentials(request)

    def test_valid_credentials_user(self):
        request = MagicMock(spec=Request)
        request.headers = {
            "x-zotero-api-key": "mykey",
            "x-zotero-library-id": "12345",
            "x-zotero-library-type": "user",
        }
        creds = resolve_zotero_credentials(request)
        assert creds.api_key == "mykey"
        assert creds.library_id == "12345"
        assert creds.library_type == "user"

    def test_valid_credentials_group(self):
        request = MagicMock(spec=Request)
        request.headers = {
            "x-zotero-api-key": "mykey",
            "x-zotero-library-id": "99999",
            "x-zotero-library-type": "group",
        }
        creds = resolve_zotero_credentials(request)
        assert creds.library_type == "group"

    def test_default_library_type_is_user(self):
        request = MagicMock(spec=Request)
        request.headers = {
            "x-zotero-api-key": "mykey",
            "x-zotero-library-id": "12345",
        }
        creds = resolve_zotero_credentials(request)
        assert creds.library_type == "user"

    def test_error_messages_do_not_contain_api_key(self):
        request = MagicMock(spec=Request)
        request.headers = {
            "x-zotero-api-key": "super_secret_key_12345",
            "x-zotero-library-id": "abc",
        }
        with pytest.raises(InvalidCredentialsError) as exc_info:
            resolve_zotero_credentials(request)
        assert "super_secret_key_12345" not in str(exc_info.value)
