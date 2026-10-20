from .settings import *


# Ordinary tests should not share rate-limit counters.
# Dedicated throttle tests override this with a real local cache.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    },
}