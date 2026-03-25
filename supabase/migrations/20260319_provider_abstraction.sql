-- Provider abstraction: add provider identity columns, make instrument_token nullable

-- instrument_catalog
ALTER TABLE market.instrument_catalog
  ADD COLUMN IF NOT EXISTS provider text NOT NULL DEFAULT 'upstox',
  ADD COLUMN IF NOT EXISTS provider_instrument_id text,
  ALTER COLUMN instrument_token DROP NOT NULL;

-- phase0_universe
ALTER TABLE ops.phase0_universe
  ADD COLUMN IF NOT EXISTS provider text NOT NULL DEFAULT 'upstox',
  ADD COLUMN IF NOT EXISTS provider_instrument_id text;

-- underlying_snapshot_1m
ALTER TABLE market.underlying_snapshot_1m
  ADD COLUMN IF NOT EXISTS instrument_key text,
  ADD COLUMN IF NOT EXISTS provider text NOT NULL DEFAULT 'upstox';

-- option_snapshot_1m
ALTER TABLE market.option_snapshot_1m
  ADD COLUMN IF NOT EXISTS instrument_key text,
  ADD COLUMN IF NOT EXISTS provider text NOT NULL DEFAULT 'upstox',
  ALTER COLUMN instrument_token DROP NOT NULL;

-- expiry_nodes_1m
ALTER TABLE analytics.expiry_nodes_1m
  ADD COLUMN IF NOT EXISTS provider text NOT NULL DEFAULT 'upstox',
  ADD COLUMN IF NOT EXISTS source_mode text NOT NULL DEFAULT 'live_quote';

-- Indexes for provider-based lookups
CREATE INDEX IF NOT EXISTS instrument_catalog_provider_id_idx
  ON market.instrument_catalog (provider, provider_instrument_id);

CREATE INDEX IF NOT EXISTS option_snapshot_provider_key_ts_idx
  ON market.option_snapshot_1m (provider, instrument_key, ts DESC);
