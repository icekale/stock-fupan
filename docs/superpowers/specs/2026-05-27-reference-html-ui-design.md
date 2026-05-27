# Reference HTML UI Design

Goal: make the generated daily review report use the provided reference HTML visual system as the primary and only UI direction.

Assumptions:
- The reference file `/Users/kale/Downloads/2026-05-26_structured_review.html` is the design source of truth.
- Dynamic report data stays unchanged; this change replaces presentation only.
- Production report content must not add fake examples copied from the reference file.
- Watchlist remains optional and hidden by default.

Design:
- Replace the current `.page/.paper/.hero/.module-card/.sector-card` design with the reference article structure: `.article-wrap`, `.article-card`, `.header-date`, `.header-title`, `.header-sub`, `.preamble`, `.section-num`, `.section-title`, `.section-subtitle`, `.section-sub-subtitle`, `.card`, `.table-wrap`, `.point-list`, `.tag`, `.conclusion-box`, `.avoid-box`, `.footer-disclaimer`, and `.footer-sources`.
- Keep the module sequence aligned with the reference: ZERO prediction review, ONE conclusion, TWO overview, THREE sectors, FOUR news, FIVE sustainability, SIX rotation, SEVEN opportunities and position discipline, EIGHT action discipline, NINE practical conclusion, APPENDIX index outlook.
- Render all module content from `ReportDTO.structured_review`; do not hard-code reference market narratives or stocks.
- Preserve fallback rendering for reports without structured review using the same article system.

Verification:
- Renderer tests assert reference classes and viewport settings are present.
- Renderer tests assert old UI classes are absent.
- Existing section-content tests continue to pass.
- Generate a real report and serve it for visual review.
