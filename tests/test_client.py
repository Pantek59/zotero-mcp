import os
from unittest.mock import patch

import pytest
from zotero_mcp.client_factory import get_zotero_client_from_env


@pytest.fixture
def mock_env_vars():
    with patch.dict(
        os.environ,
        {
            "ZOTERO_LIBRARY_ID": "1234567",
            "ZOTERO_LIBRARY_TYPE": "user",
            "ZOTERO_API_KEY": "abcdef123456",
            "ZOTERO_LOCAL": "",
        },
        clear=True,
    ):
        yield


@pytest.fixture
def mock_env_vars_local():
    with patch.dict(
        os.environ,
        {
            "ZOTERO_LIBRARY_ID": "",
            "ZOTERO_LIBRARY_TYPE": "user",
            "ZOTERO_API_KEY": "",
            "ZOTERO_LOCAL": "true",
        },
        clear=True,
    ):
        yield


def test_get_zotero_client_with_api_key(mock_env_vars):
    with patch("zotero_mcp.client_factory.zotero.Zotero") as mock_zotero:
        get_zotero_client_from_env()
        mock_zotero.assert_called_once_with(
            library_id="1234567",
            library_type="user",
            api_key="abcdef123456",
            local=False,
        )


def test_get_zotero_client_missing_api_key():
    with patch.dict(
        os.environ,
        {
            "ZOTERO_LIBRARY_ID": "1234567",
            "ZOTERO_LIBRARY_TYPE": "user",
            "ZOTERO_API_KEY": "",
            "ZOTERO_LOCAL": "",
        },
        clear=True,
    ):
        with pytest.raises(ValueError, match="Missing required environment variables"):
            get_zotero_client_from_env()


def test_get_zotero_client_local_mode(mock_env_vars_local):
    with patch("zotero_mcp.client_factory.zotero.Zotero") as mock_zotero:
        get_zotero_client_from_env()
        mock_zotero.assert_called_once_with(
            library_id="0",
            library_type="user",
            api_key=None,
            local=True,
        )


def test_get_zotero_client_local_mode_with_library_id():
    with patch.dict(
        os.environ,
        {
            "ZOTERO_LIBRARY_ID": "custom_id",
            "ZOTERO_LIBRARY_TYPE": "user",
            "ZOTERO_API_KEY": "",
            "ZOTERO_LOCAL": "true",
        },
        clear=True,
    ):
        with patch("zotero_mcp.client_factory.zotero.Zotero") as mock_zotero:
            get_zotero_client_from_env()
            mock_zotero.assert_called_once_with(
                library_id="custom_id",
                library_type="user",
                api_key=None,
                local=True,
            )
