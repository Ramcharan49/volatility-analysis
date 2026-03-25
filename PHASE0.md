# Phase 0

Phase 0 is a local-first validation spike for the `NIFTY` data and quant pipeline.

## Scope

- Zerodha auth and session persistence
- `NIFTY` instruments sync
- REST quote validation
- Historical candle validation
- Sample `ATM IV`, `RR25`, and `BF25` computation
- Live WebSocket minute sealing
- Deterministic replay from saved live artifacts
- Optional Supabase writes for the Phase 0 schemas

## Setup

1. Create or activate a virtual environment.
2. Install the Phase 0 dependencies.
3. Copy `.env.example` values into your local `.env`.
4. If you want database writes, add `SUPABASE_DB_URL_SESSION`.
5. Apply the checked-in SQL migration to the correct Supabase project before running DB-backed probes.

## Commands

Interactive auth:

```powershell
python test_zerodha.py
```

Offline probe:

```powershell
python phase0_probe.py probe
```

Skip database writes:

```powershell
python phase0_probe.py probe --skip-db
```

Skip historical data:

```powershell
python phase0_probe.py probe --skip-historical
```

Live validation:

```powershell
python phase0_probe.py live
```

Replay a saved live manifest:

```powershell
python phase0_probe.py replay --manifest artifacts\phase0_live_manifest_YYYYMMDD_HHMMSS.json
```

## What gets written locally

- `state/kite_session.json`
- `artifacts/*`
- raw live ticks are stored only in local artifacts, not in Supabase

## What gets written to Supabase

- `market.instrument_catalog`
- `ops.phase0_universe`
- `market.underlying_snapshot_1m`
- `market.option_snapshot_1m`
- `analytics.expiry_nodes_1m`
- `ops.probe_runs`
- `ops.probe_errors`

## Notes

- `market`, `analytics`, and `ops` remain private Phase 0 schemas.
- Phase 0 creates no product tables in `public`.
- The worker writes to Supabase via `SUPABASE_DB_URL_SESSION`.

## Testing

Run the quant unit tests:

```powershell
python -m unittest tests.test_quant
```

Run the offline probe on a weekend or after market hours. Run the same probe again during market hours to validate live quote freshness and minute snapshots.
