"""
extensions/cache_ext.py

Cache instance lives here — imported by both app.py and routes —
so neither file depends on the other at import time.
"""
from flask_caching import Cache

cache = Cache()