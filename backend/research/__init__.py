"""Research-only modules. Nothing here is imported by a production scoring path.

Every module under ``backend.research`` is a study instrument: it may READ
production constants, formulas and services, and it may never be read BY them.
A test (`backend/tests/unit/research/test_research_isolation.py`) asserts that
direction, because the whole value of a pre-registered candidate grid is that
it cannot quietly become the thing it was built to evaluate.
"""
