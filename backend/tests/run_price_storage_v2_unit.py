"""Run pure scope tests without executing application package initializers.

The exact implementation files are loaded, not rewritten or mocked. This tests
module behavior; it deliberately does not certify application import integration.
"""
from pathlib import Path
import importlib.util
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load test target {relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    load('backend.db.services.price_storage_v2_integration',
         'backend/db/services/price_storage_v2_integration.py')
    load('backend.scripts.reconcile_price_storage_v2_migrations',
         'backend/scripts/reconcile_price_storage_v2_migrations.py')
    tests = load('price_storage_v2_unit_targets',
                 'backend/tests/test_price_storage_v2_integration.py')
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(tests))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
