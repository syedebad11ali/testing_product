CREATE TABLE admin_totp (
  user_id TEXT PRIMARY KEY,
  secret_enc TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at BIGINT NOT NULL,
  confirmed_at BIGINT,
  last_step BIGINT NOT NULL DEFAULT 0
);
CREATE TABLE admin_stepups (
  id_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  session_hash TEXT NOT NULL,
  action_class TEXT NOT NULL,
  created_at BIGINT NOT NULL,
  expires_at BIGINT NOT NULL,
  used_at BIGINT
);
CREATE INDEX idx_admin_stepups_user ON admin_stepups (user_id, expires_at)
