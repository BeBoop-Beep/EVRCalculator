# E2.18A IMAGE-v2 exact-byte authority restoration

The canonical `develop` checkout already contains IMAGE-v2's original LF source bytes. No policy source edit was needed.

| Source | SHA256 |
|---|---|
| Original IMAGE-v2 freeze manifest | `f72f5d964f792815bf92ef5f24cda7d8f9d83c2d1bcdb64ea0ebd9fcf252d446` |
| `develop` raw source bytes | `f72f5d964f792815bf92ef5f24cda7d8f9d83c2d1bcdb64ea0ebd9fcf252d446` |
| `develop` HEAD blob | `f72f5d964f792815bf92ef5f24cda7d8f9d83c2d1bcdb64ea0ebd9fcf252d446` |
| Prior eBay worktree CRLF bytes | `bf50ee1fb1160711e9591755ee4905e7e4884946f7f079adeac0bb184c680ea1` |

The prior worktree file had 295 CRLF endings. Replacing only CRLF with LF in memory produced bytes identical to the `develop` HEAD blob and the original frozen hash. The strict `source_sha256()` check now passes unchanged. No normalized-hash exception, IMAGE-v3, or semantic policy modification was introduced.

The historical Git blob currently used by `develop` is `24d7eebfbd4a482c9f35997dc4d772af7e918ed0` (`HEAD:backend/scripts/ebay_image_retrieval_verifier.py`, last changed in commit `00eab7585c8572bd5f3230b7393d36d4077dc122`). Its raw SHA256 is exactly the frozen value above, and the working-tree bytes equal the blob byte-for-byte. Focused IMAGE-v2 tests: **28 passed**.

OCR-v3, LANGUAGE-v2, COMBINED-v4, and D3-v5 source/rule fingerprints also match their frozen manifests. The canonical-resolution artifact SHA256 `9fc36d8df60c77196d28075b9c8a878bd00467014ba072d037df184ab295d446` matches both the E2.13 manifest and E2.14 certification record. The later COMBINED-v2 manifest stores the old worktree's CRLF IMAGE-v2 source hash; this checkout-sensitive provenance difference is documented separately and does not change the original IMAGE-v2 freeze authority.

E2.18's original IMAGE-v2 gate is cleared on `develop`.

EBAY_IMAGE_V2_EXACT_FROZEN_AUTHORITY_RESTORED_E2_18_READY_TO_RESUME
