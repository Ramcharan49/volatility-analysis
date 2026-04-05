1. Auth (daily, before anything else):  
   python phase0_probe.py auth --code <CODE_FROM_FRIEND>
2. Snapshot (single point-in-time from REST quotes):  
   python verify_pipeline.py snapshot

# or with --skip-db to skip Supabase writes:

python verify_pipeline.py snapshot --skip-db

3. History (full day of 375 minutes from candles):
   python verify_pipeline.py history --date 2026-03-30

# or with --skip-db:

python verify_pipeline.py history --date 2026-03-30 --skip-db

4. Live worker (continuous during market hours):
   python -m worker.main

The live worker runs autonomously — pre-market gap-fill, market-hours WebSocket accumulation, post-market baselines/brief. Ctrl+C to  
 stop.

5. # Backfill Mar 24 to Apr 2 (writes to DB)
   python backfill.py --from 2026-03-24 --to 2026-04-02

# Dry run (CSV only, no DB)

python backfill.py --from 2026-03-24 --to 2026-04-02 --skip-db

Usage:

# Recommended: hybrid ~1 year

python backfill.py --from 2025-06-01 --to 2026-04-02 --daily-before 2026-03-01

# Daily-only (fastest)

python backfill.py --from 2025-06-01 --to 2026-04-02 --mode daily

# Full intraday only

python backfill.py --from 2026-03-01 --to 2026-04-02

# Single day test

python verify_pipeline.py daily --date 2026-03-24 --skip-db
