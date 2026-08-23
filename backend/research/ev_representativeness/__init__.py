"""EV Representativeness research layer (``ev_representativeness_v1``).

Backend research and instrumentation only. Nothing in this package feeds
Financial RIP, Overall RIP, Collector Appeal, any public snapshot, or any
publication gate, and nothing in it may until the research says a metric here is
defensible.

Central question::

    EV says this pack averages $X. If someone opens the amount a normal person
    opens, how likely are they to experience anything close to that number - and
    how many packs would they need before EV became a reasonable description of
    their experience?

Layering:

  ``distribution``    Parts 1-5    one-pack statistics, EV vs Typical, tails, buckets
  ``finite_sample``   Parts 11-17  session kernel, Wilson intervals, horizons
  ``clt``             Part 25      asymptotic comparison (never the reported answer)
  ``contribution``    Parts 6-10   card / rarity contribution, hit frequencies
  ``counterfactual``  Parts 18-19  ablations, winsorization, chase price shocks
  ``recorder``        Tier B       per-pack decomposition captured from the simulator

See ``backend/docs/research/ev_representativeness_v1_architecture_audit.md`` for
the audit that produced this design, including the two findings that shaped it:
the analytic card-EV table diverges 47% from the simulator's own mean, and the
authoritative simulation is unseeded (hence the Tier A / Tier B split).
"""

from .version import EV_REPRESENTATIVENESS_VERSION

__all__ = ["EV_REPRESENTATIVENESS_VERSION"]
