from unittest.mock import patch

from zotero_mcp.client_factory import ZoteroClientCache, _create_zotero_client
from zotero_mcp.credentials import ZoteroCredentials


class TestZoteroClientCache:
    def test_cache_creates_client_on_first_access(self):
        cache = ZoteroClientCache()
        creds = ZoteroCredentials(
            api_key="testkey", library_id="12345", library_type="user"
        )
        with patch("zotero_mcp.client_factory._create_zotero_client") as mock_create:
            mock_client = object()
            mock_create.return_value = mock_client
            client = cache.get_or_create(creds)
            assert client is mock_client
            mock_create.assert_called_once_with(creds)

    def test_cache_returns_same_client_on_second_access(self):
        cache = ZoteroClientCache()
        creds = ZoteroCredentials(
            api_key="testkey", library_id="12345", library_type="user"
        )
        with patch("zotero_mcp.client_factory._create_zotero_client") as mock_create:
            mock_client = object()
            mock_create.return_value = mock_client
            client1 = cache.get_or_create(creds)
            client2 = cache.get_or_create(creds)
            assert client1 is client2
            assert mock_create.call_count == 1

    def test_cache_different_credentials_create_different_clients(self):
        cache = ZoteroClientCache()
        creds1 = ZoteroCredentials(
            api_key="key1", library_id="12345", library_type="user"
        )
        creds2 = ZoteroCredentials(
            api_key="key2", library_id="67890", library_type="user"
        )
        with patch("zotero_mcp.client_factory._create_zotero_client") as mock_create:
            mock_create.side_effect = [object(), object()]
            client1 = cache.get_or_create(creds1)
            client2 = cache.get_or_create(creds2)
            assert client1 is not client2
            assert mock_create.call_count == 2

    def test_cache_key_does_not_contain_raw_api_key(self):
        creds = ZoteroCredentials(
            api_key="super_secret_key", library_id="12345", library_type="user"
        )
        cache_key = creds.cache_key
        assert "super_secret_key" not in cache_key

    def test_cache_ttl_expiry(self):
        cache = ZoteroClientCache(ttl_seconds=0)
        creds = ZoteroCredentials(
            api_key="testkey", library_id="12345", library_type="user"
        )
        with patch("zotero_mcp.client_factory._create_zotero_client") as mock_create:
            import time

            mock_create.side_effect = [object(), object()]
            cache.get_or_create(creds)
            time.sleep(0.01)
            cache.get_or_create(creds)
            assert mock_create.call_count == 2

    def test_cache_max_size_eviction(self):
        cache = ZoteroClientCache(max_size=2)
        with patch("zotero_mcp.client_factory._create_zotero_client") as mock_create:
            mock_create.side_effect = [object() for _ in range(3)]
            creds1 = ZoteroCredentials(
                api_key="key1", library_id="1", library_type="user"
            )
            creds2 = ZoteroCredentials(
                api_key="key2", library_id="2", library_type="user"
            )
            creds3 = ZoteroCredentials(
                api_key="key3", library_id="3", library_type="user"
            )
            cache.get_or_create(creds1)
            cache.get_or_create(creds2)
            cache.get_or_create(creds3)
            assert len(cache._cache) == 2

    def test_evict_expired_removes_old_entries(self):
        cache = ZoteroClientCache(ttl_seconds=0)
        creds = ZoteroCredentials(
            api_key="testkey", library_id="12345", library_type="user"
        )
        with patch("zotero_mcp.client_factory._create_zotero_client") as mock_create:
            import time

            mock_create.return_value = object()
            cache.get_or_create(creds)
            time.sleep(0.01)
            cache.evict_expired()
            assert len(cache._cache) == 0

    def test_clear_removes_all_entries(self):
        cache = ZoteroClientCache()
        with patch("zotero_mcp.client_factory._create_zotero_client") as mock_create:
            mock_create.side_effect = [object(), object()]
            creds1 = ZoteroCredentials(
                api_key="key1", library_id="1", library_type="user"
            )
            creds2 = ZoteroCredentials(
                api_key="key2", library_id="2", library_type="user"
            )
            cache.get_or_create(creds1)
            cache.get_or_create(creds2)
            assert len(cache._cache) == 2
            cache.clear()
            assert len(cache._cache) == 0


class TestCreateZoteroClient:
    def test_creates_client_with_credentials(self):
        creds = ZoteroCredentials(
            api_key="testkey", library_id="12345", library_type="user"
        )
        with patch("zotero_mcp.client_factory.zotero.Zotero") as mock_zotero:
            _create_zotero_client(creds)
            mock_zotero.assert_called_once_with(
                library_id="12345",
                library_type="user",
                api_key="testkey",
            )

    def test_creates_client_with_group_type(self):
        creds = ZoteroCredentials(
            api_key="testkey", library_id="99999", library_type="group"
        )
        with patch("zotero_mcp.client_factory.zotero.Zotero") as mock_zotero:
            _create_zotero_client(creds)
            mock_zotero.assert_called_once_with(
                library_id="99999",
                library_type="group",
                api_key="testkey",
            )
