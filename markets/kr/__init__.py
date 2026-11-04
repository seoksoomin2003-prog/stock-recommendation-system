"""Independent South Korea (KOSPI + KOSDAQ) engine (P6-22 .. P6-25).

Nothing in this package imports or alters the frozen US P6-11B core.  It shares only infrastructure
(run recorder, hash-chained append-only ledger, JSON helpers, report rendering conventions).
"""
KR_DATA_SPEC_VERSION = "KR-DATA-0.1"
KR_ACCOUNT_MAPPING_VERSION = "KR-ACCT-0.1"
KR_MODEL_VERSION = "KR-EXP-0.1"
KR_MODEL_STATUS = "EXPERIMENTAL"        # never "APPROVED" until the validation gates in KR_MODEL_SPECIFICATION pass
