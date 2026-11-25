"""Per-user stages 7 and 8 (CLAUDE.md sections 5 and 7): match and score.

``blackkite.scoring.service`` is the entry point: ``score_new_opportunities`` (the
worker, after ingest), ``backfill_profile`` (a new or edited profile) and
``score_user`` (``bk score``). Rows go to ``user_opportunity_score`` in the shape
fixed by docs/api-contract.md section 1; ``user_opportunity`` is never touched.
"""
