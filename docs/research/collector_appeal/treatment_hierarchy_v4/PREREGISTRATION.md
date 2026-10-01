# Treatment Hierarchy V4 — Set-Local Scarcity Identifiability Preregistration

Status: `FROZEN_BEFORE_LOCAL_SCARCITY_FIT`

Date frozen: 2026-10-01

## Question

Treatment Hierarchy V2/V3 estimated Set-specific Treatment coefficients but used one global Exact Pull Scarcity slope across all Sets/families.

This V4 study asks the narrower question implied by the intended architecture:

> Inside a single Set/family, can Treatment be separated from Exact Pull Scarcity at all?

No global scarcity coefficient is allowed.

## Frozen evidence

V4 consumes exactly the Treatment Panel Recovery V3 artifact:

- workflow run `36929725640`
- artifact `11196076068`
- digest `sha256:e3dc70d260e53e079348db304774c89812b9a9fc0d35654ecf6d0470f1fc974b`
- recovery manifest fingerprint `55b8dcd3090acb707d101a3b03e574862cc3ef15f752c95940870f7b4b3d6e24`
- recovery sample fingerprint `7fecdbd2cb448dd9414f062d0d83b16a58b187dcbd7bf679cf781dc295d7b23e`

Only identities already marked `PANEL_READY_STRONG` or `PANEL_READY_MODERATE` are eligible.

A Set/family must retain at least 2 ready identities. No blocked identity may be imputed, substituted, or replaced.

## Stage A — local identifiability gate

Each Set/family is analyzed independently.

For each group:

### PACKAGE

Outcome:
- exact shared-date log Near-Mint price
- demeaned by matched identity/date

Predictors:
- Set/family treatment indicators only
- same reference-treatment rules as V2/V3
- no intercept

### PURE_LOCAL

Same treatment indicators plus **one scarcity slope belonging only to that Set/family**:

`scarcity = -ln(exact modeled probability)`

Scarcity is demeaned within matched identity.

Before fitting coefficients, calculate exact matrix rank.

A group is `LOCAL_SCARCITY_UNDERIDENTIFIED` if the PURE_LOCAL design is not full column rank.

Prohibited rescue methods:
- no pseudoinverse interpretation of non-identified coefficients;
- no ridge/lasso;
- no priors that manufacture within-Set separation;
- no dropping scarcity;
- no collapsing treatment categories after seeing rank;
- no using another Set's scarcity slope.

If fewer than two independent Sets in every shared treatment family have a full-rank local PURE design, the study stops at identifiability. Bootstrap/era pooling is not fabricated.

## Stage B — support gates if locally identifiable

For any full-rank Set/family, reuse V3 numerical gates unchanged:

- 2,000 matched-identity bootstrap draws;
- seed 20261001;
- sign stability >= 0.80;
- leave-one-identity maximum coefficient drift <= 0.50 log points;
- early/late same sign for supported coefficients;
- global early/late Spearman across all locally estimable Treatment coefficients >= 0.60;
- Artist and Playability sensitivity drift <= 0.50 or invariant by construction.

## Era progression

An era/family may be pooled only when at least 2 independent Sets in that family pass the complete local support gates.

No cross-era inference is authorized.

## Interpretation

A rank-deficient PURE_LOCAL model is not a failure of data plumbing. It means that, in the observed Set, Treatment designation and Exact Pull Scarcity do not vary independently enough to estimate separate effects from market price.

That result would support keeping Treatment as:
- a descriptive/diagnostic card attribute, or
- part of a bundled Treatment/rarity package,

but would not support calling the residual a scarcity-independent Collector Appeal component.

## Decision tokens

- `TREATMENT_HIERARCHY_V4_LOCAL_SCARCITY_UNDERIDENTIFIED`
- `TREATMENT_HIERARCHY_V4_DIAGNOSTIC_ONLY`
- `TREATMENT_HIERARCHY_V4_SET_LOCAL_SUPPORTED`
- `TREATMENT_HIERARCHY_V4_SV_ERA_SUPPORTED`

## Safety

- production writes: prohibited
- provider calls: prohibited
- canonical price mutation: prohibited
- Collector Appeal mutation: prohibited
- Overall RIP mutation: prohibited
- Rankings / Set-page mutation: prohibited
