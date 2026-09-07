# Original applied SQL: partial, non-executable archive

These three files preserve the exact UTF-8 bytes of production's applied migration
statements, including original version IDs and absence of a trailing newline.
Their MD5 checksums and Git blob SHAs were independently computed in a READ ONLY
production query and match the committed objects.

| Version | Bytes | Statement MD5 | Git blob SHA |
|---|---:|---|---|
| 20260906230828 | 7186 | 0d006e178b880816b2ee77bec2188290 | 040ac8eedcfbd91adb3e993d3bf81a1f41f38cdc |
| 20260906233426 | 17533 | 5929e3b93b2dc636a346a99c2db0ebfc | 67271cf35ac0715fb0f4c2a5feea0d70f76701df |
| 20260906233651 | 1300 | 76f49732e0e449d1106eff2b412d7a47 | 0d4cf9fda0ad61614d0a88a2adf6991398d72efe |

This is **3 of 89 original statement sequences**, not completed migration-history
reconciliation. The manifest next to this folder covers all 89 IDs and SQL hashes.
The remaining 86 original sequences are not archived here yet.

Do not execute these files manually against production. They have already been
applied and depend on earlier production definitions and data. Do not move them
into an executable migration directory until both repository migration histories,
nominal timestamp aliases, and interleaved changes are reconciled. No placeholder,
renumbering, or SQL reapplication is authorized by this archive.

Run `python backend/scripts/audit_price_storage_v2_migration_sources.py` for an
offline integrity/inventory report. The default reports incomplete synchronization
without failing archive integrity; `--strict` exits nonzero unless all 89 exact
originals are reconciled in both executable migration folders.
