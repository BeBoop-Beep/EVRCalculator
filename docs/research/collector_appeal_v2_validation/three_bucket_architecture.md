# The three-bucket architecture — documented, not implemented

**Status:** design documentation. **Personal Fit is not implemented and this
document does not authorize implementing it.** Nothing here changes a score, a
weight, or a contract.

---

## The three buckets

```text
Financial RIP
    universal monetary opening quality

General Collector Appeal
    population-level roster and opening appeal

Personal Fit
    incremental user-specific match
```

They answer three different questions and must stay separable:

| Bucket | Question | Varies by |
|---|---|---|
| Financial RIP | "Is this product good value to open?" | set only |
| General Collector Appeal | "Is this a set the average collector enjoys opening?" | set only |
| Personal Fit | "Is this a set **you** would enjoy opening, beyond that?" | set **×** user |

**General Collector Appeal must remain a set-level property. Personal Fit must
remain a set-user interaction.** Collapsing them is the failure mode this
document exists to prevent — and it is an easy one, because a personalized appeal
score and a general appeal score look identical in a payload.

---

## Definition of Personal Fit

```text
Personal Fit is the incremental match between a set and a specific user,
beyond the population-level Collector Appeal already assigned to the set.
```

The word **beyond** is load-bearing. A Personal Fit that simply recomputed appeal
using one user's favorites would not be incremental — it would be General
Collector Appeal with a different weighting, and adding it to a score that
already contains General Collector Appeal would double-count the population
signal.

### What it may eventually include

* Favorite Pokémon
* Favorite trainers
* Preferred artists
* Preferred eras
* Preference for attainable cards versus elite chases
* Risk tolerance
* Collection-completion goals
* Opening-session preferences

Note that several of these — trainers, artists, eras — have **no desirability
model today**. The current subject model covers Pokémon only, and
`desirable_outcome_frequency` deliberately refuses to fabricate the others. Any
Personal Fit that used them would need those models built first, not assumed.

---

## Keeping Personal Fit distinct — candidate approaches

None of these is chosen here. All preserve the "incremental" property.

**1. Centering on population desirability.** Score a user's preferred subjects
relative to the population's, so a user whose favorites are simply the most
popular Pokémon receives a Personal Fit near zero — correctly, because General
Collector Appeal already captured them.

**2. Preferred-subject coverage beyond the general roster score.** Measure how
much of *this user's* preferred-subject demand the set covers, minus the coverage
the average collector would get. Again zero when the user is average.

**3. Accessibility-versus-chase alignment.** The July study established that
`axis_position` is a **taste** coordinate, not a quality one: a set at 0.2 is not
worse than a set at 0.8, it suits a different collector. This is the cleanest
Personal Fit signal available, because it is the axis General Collector Appeal
deliberately *cannot* encode without choosing whose taste to privilege.

**4. Residual or interaction modelling.** Estimate Personal Fit as the residual
of a user's personal choice after conditioning on the general-choice model — the
specification in [behavioral_validation_plan.md](behavioral_validation_plan.md)
§4. This is the most rigorous option and the only one that can return "Personal
Fit does not exist as a separate construct".

---

## Metric ownership: Dual-Path Depth

**Owner bucket: none yet. Retained, maintained, and unassigned.**

Collector Appeal V4 removes Dual-Path Depth (`P`) from the **universal**
Collector Appeal formula. The metric itself is **not deprecated and must not be
deleted.** Its authoritative definition stays where it has always been, in
`backend/desirability/collector_appeal.compute_dual_path_depth`, carrying
`DUAL_PATH_DEPTH_VERSION`, with its mathematics unchanged.

**Why it left universal Collector Appeal.** The V4 ablation held every other
assumption identical — same D, same H transform and anchors, same neutral point,
same +4.0 / −2.0 asymmetric modifier, same clamp — and varied only whether P
entered the structural index. P changed 3 of 231 pairwise orderings, moved six
sets by exactly one rank each, and left Spearman(with P, without P) = **0.9966**.
For a universal set-level appeal score that is not useful discrimination beyond
Desirable Outcome Frequency. Evidence:
[`collector_appeal_v4_promotion_validation.md`](../collector_appeal_v4_promotion_validation.md) §2.

**Why it is kept.** "Adds little at the population level" and "measures nothing
useful" are different claims, and only the first is supported. P asks a question
whose answer plausibly depends on *who is asking*, which is the defining shape of
a Personal Fit feature rather than a General Collector Appeal one:

* **master-set collectors** — accessible plus elite printing paths may change the
  progression and completion experience;
* **collectors chasing one specific Pokémon** — subject-level dual-path depth
  (`subject_dual_path` already computes exactly this, per subject) could measure
  whether *their* Pokémon has both an attainable and a premium chase printing;
* **other personalized collecting profiles** where a stated preference makes
  rarity structure relevant.

This sits naturally beside candidate approach **3** above: `axis_position` is a
taste coordinate that General Collector Appeal cannot encode without privileging
someone's taste, and P is a *structural* companion to it — taste-free in itself,
but differently valuable depending on the user's goal.

```text
Universal Collector Appeal V4      Future Personal Fit
    D + modest H modifier              P remains a CANDIDATE feature
    NO P                               usage depends on the collector's
                                       stated goal / preferences
```

**What this entry does not authorize.** It is not permission to add P back to
universal Collector Appeal, and it is not permission to build Personal Fit —
which this document has never authorized and still does not. Any future
personalization work must validate P's appropriate use and weighting
independently, on its own evidence, under the same "incremental, not repeated"
constraint the rest of this document imposes. Note in particular that P is
**not** currently known to satisfy constraint 1 below: nobody has measured
whether a P-based Personal Fit would merely repeat General Collector Appeal.

---

## A future Personal RIP

A future Personal RIP may combine all three. Two constraints:

1. **Personal Fit must not repeat General Appeal.** If `Personal Fit ≈ General
   Collector Appeal` empirically, then a Personal RIP containing both weights the
   same signal twice, and the second application is invisible in the formula.
2. **The weights are not decided in this task and are not decided by this
   document.** They are a product decision informed by the behavioral study, and
   the behavioral study has not been run.

---

## Why this ordering matters

Personal Fit is the most requested and the least ready of the three. It requires:

* a validated General Collector Appeal to be incremental *to* — and the current
  evidence (see [validation_summary.md](validation_summary.md)) shows the shipped
  Collector Appeal correlates ρ ≈ 0.99 with pure desirability, so what it adds
  over D is not yet established;
* collector-preference data that does not exist;
* desirability models for trainers, artists and eras that do not exist;
* a user-identity and preference-capture surface that does not exist.

Building Personal Fit before General Collector Appeal is validated would mean
personalizing a metric whose population-level meaning is still an open question.
