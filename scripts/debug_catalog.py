import inspect
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.spill_catalog_service import SpillCatalogService

service = SpillCatalogService()
print("=== SpillCatalogService Attributes ===")
for attr in dir(service):
    if not attr.startswith("_"):
        val = getattr(service, attr)
        print(f"• {attr}: {val}")

print("\n=== SpillCatalogService Source Code ===")
print(inspect.getsource(SpillCatalogService))