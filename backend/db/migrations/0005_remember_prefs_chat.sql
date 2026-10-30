CREATE TABLE remember_tokens (
  id TEXT PRIMARY KEY,
  selector TEXT NOT NULL UNIQUE,
  validator_hash TEXT NOT NULL,
  user_id TEXT NOT NULL,
  device_label TEXT,
  created_at BIGINT NOT NULL,
  last_used_at BIGINT NOT NULL,
  expires_at BIGINT NOT NULL,
  rotated_at BIGINT,
  revoked_at BIGINT
);
CREATE INDEX idx_remember_user ON remember_tokens (user_id);
CREATE TABLE user_prefs (
  user_id TEXT PRIMARY KEY,
  prefs TEXT NOT NULL,
  updated_at BIGINT NOT NULL
);
CREATE TABLE chat_sessions (
  sid_hash TEXT PRIMARY KEY,
  history TEXT NOT NULL,
  memory TEXT NOT NULL,
  updated_at BIGINT NOT NULL
);
CREATE INDEX idx_chat_sessions_updated ON chat_sessions (updated_at)
