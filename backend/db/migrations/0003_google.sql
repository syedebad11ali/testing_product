ALTER TABLE users ADD COLUMN google_sub TEXT;
CREATE UNIQUE INDEX idx_users_google_sub ON users (google_sub);
CREATE TABLE auth_nonces (
  id_hash TEXT PRIMARY KEY,
  created_at BIGINT NOT NULL,
  used_at BIGINT
);
CREATE INDEX idx_auth_nonces_created ON auth_nonces (created_at);
