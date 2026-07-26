import logging
import os
import time
from collections import OrderedDict

from dotenv import load_dotenv
from pyzotero import zotero

from zotero_mcp.credentials import ZoteroCredentials

load_dotenv()

logger = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS = 15 * 60
_DEFAULT_MAX_CACHE_SIZE = 256


class _CacheEntry:
    __slots__ = ("client", "expires_at")

    def __init__(self, client: zotero.Zotero, expires_at: float) -> None:
        self.client = client
        self.expires_at = expires_at


class ZoteroClientCache:
    def __init__(
        self,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
        max_size: int = _DEFAULT_MAX_CACHE_SIZE,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_size = max_size
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()

    def get_or_create(self, credentials: ZoteroCredentials) -> zotero.Zotero:
        cache_key = credentials.cache_key
        now = time.monotonic()

        entry = self._cache.get(cache_key)
        if entry is not None:
            if now < entry.expires_at:
                self._cache.move_to_end(cache_key)
                return entry.client
            else:
                del self._cache[cache_key]

        client = _create_zotero_client(credentials)
        self._cache[cache_key] = _CacheEntry(
            client=client,
            expires_at=now + self._ttl_seconds,
        )
        self._cache.move_to_end(cache_key)

        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

        return client

    def evict_expired(self) -> None:
        now = time.monotonic()
        expired_keys = [k for k, v in self._cache.items() if now >= v.expires_at]
        for k in expired_keys:
            del self._cache[k]

    def clear(self) -> None:
        self._cache.clear()


def _create_zotero_client(credentials: ZoteroCredentials) -> zotero.Zotero:
    return zotero.Zotero(
        library_id=credentials.library_id,
        library_type=credentials.library_type,
        api_key=credentials.api_key,
    )


_client_cache: ZoteroClientCache | None = None


def get_client_cache() -> ZoteroClientCache:
    global _client_cache
    if _client_cache is None:
        _client_cache = ZoteroClientCache()
    return _client_cache


def set_client_cache(cache: ZoteroClientCache) -> None:
    global _client_cache
    _client_cache = cache


def get_zotero_client_from_credentials(
    credentials: ZoteroCredentials,
) -> zotero.Zotero:
    return get_client_cache().get_or_create(credentials)


def get_zotero_client_from_env() -> zotero.Zotero:
    library_id = os.getenv("ZOTERO_LIBRARY_ID")
    library_type = os.getenv("ZOTERO_LIBRARY_TYPE", "user")
    api_key = os.getenv("ZOTERO_API_KEY") or None
    local = os.getenv("ZOTERO_LOCAL", "").lower() in ["true", "yes", "1"]
    if local:
        if not library_id:
            library_id = "0"
    elif not all([library_id, api_key]):
        raise ValueError(
            "Missing required environment variables. "
            "Please set ZOTERO_LIBRARY_ID and ZOTERO_API_KEY"
        )

    return zotero.Zotero(
        library_id=library_id,
        library_type=library_type,
        api_key=api_key,
        local=local,
    )
