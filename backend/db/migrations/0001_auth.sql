CREATE TABLE users (
  id TEXT PRIMARY KEY,
  email TEXT UNIQUE,
  username TEXT UNIQUE,
  name TEXT NOT NULL,
  password_hash TEXT,
  role TEXT NOT NULL DEFAULT 'user',
  status TEXT NOT NULL DEFAULT 'active',
  method TEXT NOT NULL DEFAULT 'password',
  must_change_password INTEGER NOT NULL DEFAULT 0,
  created_at BIGINT NOT NULL,
  last_login_at BIGINT
);
CREATE TABLE sessions (
  id_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  created_at BIGINT NOT NULL,
  last_seen_at BIGINT NOT NULL,
  expires_at BIGINT NOT NULL,
  idle_s BIGINT NOT NULL,
  ip_hash TEXT,
  user_agent TEXT,
  revoked_at BIGINT
);
CREATE INDEX idx_sessions_user ON sessions (user_id);
CREATE TABLE login_events (
  id TEXT PRIMARY KEY,
  ts BIGINT NOT NULL,
  user_id TEXT,
  identifier TEXT,
  method TEXT NOT NULL,
  success INTEGER NOT NULL,
  reason TEXT,
  ip_hash TEXT,
  user_agent TEXT
);
CREATE INDEX idx_login_events_ts ON login_events (ts);
CREATE INDEX idx_login_events_ident ON login_events (identifier, ts);
CREATE TABLE audit_log (
  id TEXT PRIMARY KEY,
  ts BIGINT NOT NULL,
  actor_id TEXT,
  action TEXT NOT NULL,
  target TEXT,
  ip_hash TEXT,
  detail TEXT
);
CREATE INDEX idx_audit_ts ON audit_log (ts);
