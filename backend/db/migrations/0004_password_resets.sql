CREATE TABLE password_resets (
  id_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  created_at BIGINT NOT NULL,
  expires_at BIGINT NOT NULL,
  used_at BIGINT
);
CREATE INDEX idx_password_resets_user ON password_resets (user_id)
