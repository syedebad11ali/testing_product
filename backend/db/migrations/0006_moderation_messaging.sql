CREATE TABLE user_bans (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  reason TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  created_at BIGINT NOT NULL,
  expires_at BIGINT,
  lifted_at BIGINT,
  lifted_by TEXT,
  lift_reason TEXT
);
CREATE INDEX idx_bans_user ON user_bans (user_id, created_at);
CREATE TABLE listings (
  id TEXT PRIMARY KEY,
  ref TEXT NOT NULL UNIQUE,
  seller_id TEXT NOT NULL,
  title TEXT NOT NULL,
  area TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  created_at BIGINT NOT NULL
);
CREATE INDEX idx_listings_seller ON listings (seller_id);
CREATE TABLE conversations (
  id TEXT PRIMARY KEY,
  listing_id TEXT NOT NULL,
  buyer_id TEXT NOT NULL,
  seller_id TEXT NOT NULL,
  created_at BIGINT NOT NULL,
  last_message_at BIGINT NOT NULL,
  buyer_read_ts BIGINT NOT NULL DEFAULT 0,
  seller_read_ts BIGINT NOT NULL DEFAULT 0,
  UNIQUE (listing_id, buyer_id)
);
CREATE INDEX idx_conv_buyer ON conversations (buyer_id, last_message_at);
CREATE INDEX idx_conv_seller ON conversations (seller_id, last_message_at);
CREATE TABLE messages (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  sender_id TEXT NOT NULL,
  body TEXT NOT NULL,
  ts BIGINT NOT NULL,
  client_id TEXT,
  UNIQUE (conversation_id, sender_id, client_id)
);
CREATE INDEX idx_msg_conv ON messages (conversation_id, ts);
CREATE TABLE user_blocks (
  blocker_id TEXT NOT NULL,
  blocked_id TEXT NOT NULL,
  created_at BIGINT NOT NULL,
  PRIMARY KEY (blocker_id, blocked_id)
);
CREATE TABLE message_reports (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  message_id TEXT,
  reporter_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at BIGINT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  reviewed_by TEXT,
  reviewed_at BIGINT,
  review_note TEXT
);
CREATE INDEX idx_reports_status ON message_reports (status, created_at)
