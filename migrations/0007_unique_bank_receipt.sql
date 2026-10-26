-- One verified bank transfer must never fund multiple self-service orders.
-- Old admin/manual migration references can be non-bank labels, so restrict
-- the uniqueness invariant to newly verified self-service payments only.
-- Case/whitespace normalization blocks trivial duplicate reference variants.
-- Index creation is transactional; no real banking credentials are stored.
CREATE UNIQUE INDEX IF NOT EXISTS idx_self_service_paid_bank_receipt
  ON orders(upper(trim(reference)))
  WHERE source='self_service' AND status='paid'
    AND reference IS NOT NULL AND length(trim(reference))>=3;
