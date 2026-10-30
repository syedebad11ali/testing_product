CREATE TABLE chat_feedback (
  id TEXT PRIMARY KEY,
  ts BIGINT NOT NULL,
  message_id TEXT NOT NULL,
  rating TEXT NOT NULL,
  intent TEXT,
  question TEXT,
  answered INTEGER
);
CREATE INDEX idx_chat_feedback_ts ON chat_feedback (ts);
