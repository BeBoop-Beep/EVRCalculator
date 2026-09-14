"""Collector Appeal market-validation research harness. RESEARCH ONLY.

Measures how Collector Appeal and its subcomponents relate to market outcomes
WITHOUT letting price influence Collector Appeal's own construction or tuning.
See price_separation.py for the enforced contract: PRICE IS OUTCOME ONLY.

This package does not read a database or a live price feed itself -- callers
supply card-level and set-level record dicts (schema.py) built from whatever
source-of-truth is current at analysis time. Nothing here mutates or persists
Collector Appeal, Overall RIP, or any production model.
"""
