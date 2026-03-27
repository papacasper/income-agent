import Database from 'better-sqlite3';
import fs from 'fs';
import path from 'path';

let _db: Database.Database | null = null;

export function getDB(): Database.Database {
  if (_db) return _db;

  const dbPath = process.env.DB_PATH || './data/agent.db';
  const dir = path.dirname(dbPath);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

  _db = new Database(dbPath);
  _db.pragma('journal_mode = WAL');
  _db.pragma('foreign_keys = ON');

  const schema = fs.readFileSync(path.join(__dirname, 'schema.sql'), 'utf-8');
  _db.exec(schema);

  return _db;
}

export function postMessage(from: string, to: string | null, type: string, payload: object) {
  const db = getDB();
  db.prepare(`
    INSERT INTO agent_messages (from_agent, to_agent, type, payload)
    VALUES (?, ?, ?, ?)
  `).run(from, to, type, JSON.stringify(payload));
}

export function readMessages(agentId: string): Array<{ id: number; from: string; type: string; payload: object }> {
  const db = getDB();
  const rows = db.prepare(`
    SELECT id, from_agent, type, payload
    FROM agent_messages
    WHERE (to_agent = ? OR to_agent IS NULL)
      AND read = 0
    ORDER BY created_at ASC
  `).all(agentId) as Array<{ id: number; from_agent: string; type: string; payload: string }>;

  if (rows.length > 0) {
    const ids = rows.map(r => r.id);
    db.prepare(`UPDATE agent_messages SET read = 1 WHERE id IN (${ids.join(',')})`).run();
  }

  return rows.map(r => ({
    id: r.id,
    from: r.from_agent,
    type: r.type,
    payload: JSON.parse(r.payload)
  }));
}

export function updateAgentState(agentId: string, status: string, task?: string, meta?: object) {
  const db = getDB();
  db.prepare(`
    INSERT INTO agent_state (agent_id, last_run, run_count, status, current_task, metadata)
    VALUES (?, CURRENT_TIMESTAMP, 1, ?, ?, ?)
    ON CONFLICT(agent_id) DO UPDATE SET
      last_run = CURRENT_TIMESTAMP,
      run_count = run_count + 1,
      status = excluded.status,
      current_task = excluded.current_task,
      metadata = excluded.metadata
  `).run(agentId, status, task || null, meta ? JSON.stringify(meta) : null);
}

export function getTotals(): { revenue: number; expenses: number; net: number; products: number; sales: number } {
  const db = getDB();
  const tx = db.prepare(`
    SELECT
      SUM(CASE WHEN type = 'sale' THEN net ELSE 0 END) as revenue,
      SUM(CASE WHEN type = 'expense' THEN ABS(net) ELSE 0 END) as expenses,
      SUM(net) as net,
      COUNT(CASE WHEN type = 'sale' THEN 1 END) as sales
    FROM transactions
  `).get() as { revenue: number; expenses: number; net: number; sales: number };

  const products = db.prepare(`SELECT COUNT(*) as c FROM products WHERE status = 'listed'`).get() as { c: number };

  return {
    revenue: tx?.revenue || 0,
    expenses: tx?.expenses || 0,
    net: tx?.net || 0,
    products: products?.c || 0,
    sales: tx?.sales || 0
  };
}

export function logTransaction(productId: number | null, amount: number, fee: number, type: string, description: string, platform?: string) {
  const db = getDB();
  const net = type === 'expense' ? -Math.abs(amount) : amount - fee;
  db.prepare(`
    INSERT INTO transactions (product_id, amount, fee, net, type, description, platform)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `).run(productId, amount, fee, net, type, description, platform || null);
}
