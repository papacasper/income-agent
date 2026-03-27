-- Agent coordination and shared state

CREATE TABLE IF NOT EXISTS opportunities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT NOT NULL,           -- 'digital_product', 'freelance', 'affiliate', 'service'
  title TEXT NOT NULL,
  description TEXT,
  estimated_revenue REAL,
  effort_hours REAL,
  status TEXT DEFAULT 'pending', -- pending, in_progress, listed, sold, failed
  platform TEXT,                 -- gumroad, etsy, upwork, etc.
  platform_id TEXT,              -- ID on the external platform
  platform_url TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  metadata TEXT                  -- JSON blob for extra data
);

CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  opportunity_id INTEGER REFERENCES opportunities(id),
  title TEXT NOT NULL,
  description TEXT,
  price REAL NOT NULL,
  platform TEXT NOT NULL,
  platform_id TEXT,
  platform_url TEXT,
  file_path TEXT,
  status TEXT DEFAULT 'draft',   -- draft, listed, unlisted
  views INTEGER DEFAULT 0,
  sales INTEGER DEFAULT 0,
  revenue REAL DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER REFERENCES products(id),
  amount REAL NOT NULL,
  fee REAL DEFAULT 0,
  net REAL NOT NULL,
  platform TEXT,
  transaction_id TEXT,
  type TEXT DEFAULT 'sale',      -- sale, refund, expense
  description TEXT,
  occurred_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  from_agent TEXT NOT NULL,
  to_agent TEXT,                 -- NULL = broadcast
  type TEXT NOT NULL,            -- 'task', 'result', 'insight', 'alert'
  payload TEXT NOT NULL,         -- JSON
  read INTEGER DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_state (
  agent_id TEXT PRIMARY KEY,
  last_run DATETIME,
  run_count INTEGER DEFAULT 0,
  status TEXT DEFAULT 'idle',
  current_task TEXT,
  metadata TEXT
);

CREATE TABLE IF NOT EXISTS market_insights (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  category TEXT NOT NULL,        -- 'trend', 'competitor', 'keyword', 'niche'
  title TEXT NOT NULL,
  data TEXT NOT NULL,            -- JSON
  score REAL,                    -- relevance/opportunity score 0-10
  source TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  expires_at DATETIME
);

CREATE TABLE IF NOT EXISTS daily_metrics (
  date TEXT PRIMARY KEY,
  revenue REAL DEFAULT 0,
  expenses REAL DEFAULT 0,
  net REAL DEFAULT 0,
  opportunities_found INTEGER DEFAULT 0,
  products_created INTEGER DEFAULT 0,
  products_listed INTEGER DEFAULT 0,
  sales_count INTEGER DEFAULT 0
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_opportunities_status ON opportunities(status);
CREATE INDEX IF NOT EXISTS idx_opportunities_title ON opportunities(title);
CREATE INDEX IF NOT EXISTS idx_products_status ON products(status);
CREATE INDEX IF NOT EXISTS idx_agent_messages_to_read ON agent_messages(to_agent, read);
CREATE INDEX IF NOT EXISTS idx_market_insights_category ON market_insights(category, score DESC);

-- Triggers
CREATE TRIGGER IF NOT EXISTS update_opportunities_timestamp
AFTER UPDATE ON opportunities
BEGIN
  UPDATE opportunities SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS update_products_timestamp
AFTER UPDATE ON products
BEGIN
  UPDATE products SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
