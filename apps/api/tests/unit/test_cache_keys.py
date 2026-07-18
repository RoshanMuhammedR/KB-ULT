import unittest
from uuid import uuid4

from src.core.exceptions import MissingTenantContextError
from src.core.tenant_context import reset_tenant_context, set_tenant_context
from src.infrastructure.cache import ValkeyCache, system_cache_key, tenant_cache_key


class TenantCacheKeyTests(unittest.TestCase):
    def test_tenant_key_is_namespaced_and_fails_closed(self):
        # No tenant in context -> fails closed rather than building an ambiguous key.
        with self.assertRaises(MissingTenantContextError):
            tenant_cache_key("docs", "list")

        tid, uid = uuid4(), uuid4()
        tokens = set_tenant_context(tid, uid)
        try:
            key = tenant_cache_key("docs", "list")
            self.assertEqual(key, f"tenant:{tid}:docs:list")
            # A different tenant yields a different key -> no cross-tenant bleed.
            reset_tenant_context(tokens)
            other = uuid4()
            tokens = set_tenant_context(other, uid)
            self.assertNotEqual(tenant_cache_key("docs", "list"), key)
        finally:
            reset_tenant_context(tokens)

    def test_system_key_format(self):
        self.assertEqual(system_cache_key("embedding", "abc"), "system:embedding:abc")
        self.assertEqual(system_cache_key("health"), "system:health")


class ValkeyCacheDegradationTests(unittest.TestCase):
    def test_cache_outage_degrades_to_miss(self):
        # Unreachable host: get() is a miss, set()/delete() are no-ops — never raise.
        cache = ValkeyCache("redis://127.0.0.1:6390/0")
        self.assertIsNone(cache.get("system:x"))
        cache.set("system:x", "1", ttl_seconds=5)  # must not raise
        cache.delete("system:x")  # must not raise


if __name__ == "__main__":
    unittest.main()
