# Shrouded Fable contextual mapping follow-up

The production contextual-roster V4 cutover intentionally leaves the current
Shrouded Fable simulator Basic Energy rows unresolved. They account for about
7.6849% of positive modeled card EV and are semantically non-Pokemon. They stay
in the whole-positive-EV denominator, so Pokemon chase shares are not inflated.

A future data-quality change should classify these rows as
`intentional_non_pokemon` so they stop consuming unresolved-mapping headroom:
Basic Grass, Darkness, Psychic, Water, Fire, Metal, Fighting, and Lightning
Energy. That cleanup must not weaken or bypass V4's 10% reliability gate.
