import { BaseAgent, AgentTool } from './base-agent.js';
import { getDB, getTotals } from '../db/index.js';

const SYSTEM_PROMPT = `You are a financial intelligence agent tracking the progress toward a $20,000 goal in 60 days.

Start date: ${process.env.START_DATE || '2026-03-24'}
Goal: $20,000 net revenue
Days remaining: calculated from today

Your job:
- Track all revenue and expenses
- Calculate required daily run rate
- Identify which products/strategies are working
- Recommend where to focus next
- Alert when on/off track

Be brutally honest about pace. If we're behind, say so and recommend specific actions.`;

export class FinanceAgent extends BaseAgent {
  constructor() {
    const tools: AgentTool[] = [
      {
        name: 'get_financial_summary',
        description: 'Get complete financial summary including revenue, expenses, and goal progress',
        input_schema: { type: 'object', properties: {} },
        execute: async () => {
          const totals = getTotals();
          const db = getDB();

          const goal = Number(process.env.GOAL_AMOUNT || 20000);
          const startDate = new Date(process.env.START_DATE || '2026-03-24');
          const today = new Date();
          const daysElapsed = Math.floor((today.getTime() - startDate.getTime()) / (1000 * 60 * 60 * 24));
          const daysRemaining = Math.max(0, 60 - daysElapsed);
          const requiredDailyRate = daysRemaining > 0 ? (goal - totals.net) / daysRemaining : 0;

          const byProduct = db.prepare(`
            SELECT p.title, p.price, p.sales, p.revenue, p.platform_url
            FROM products p WHERE p.revenue > 0
            ORDER BY p.revenue DESC
          `).all();

          const recentTx = db.prepare(`
            SELECT * FROM transactions ORDER BY occurred_at DESC LIMIT 20
          `).all();

          return JSON.stringify({
            goal, daysElapsed, daysRemaining,
            earned: totals.net,
            remaining: goal - totals.net,
            requiredDailyRate,
            onTrack: totals.net / Math.max(1, daysElapsed) >= (goal / 60),
            byProduct,
            recentTransactions: recentTx
          });
        }
      },
      {
        name: 'log_expense',
        description: 'Log an expense (API costs, platform fees, etc.)',
        input_schema: {
          type: 'object',
          properties: {
            amount: { type: 'number', description: 'Amount in USD' },
            description: { type: 'string' },
            category: { type: 'string' }
          },
          required: ['amount', 'description']
        },
        execute: async (input) => {
          const db = getDB();
          db.prepare(`
            INSERT INTO transactions (product_id, amount, fee, net, type, description, platform)
            VALUES (NULL, ?, 0, ?, 'expense', ?, ?)
          `).run(input.amount, -Math.abs(input.amount as number), input.description, input.category || 'general');
          return `Logged expense: $${input.amount} - ${input.description}`;
        }
      },
      {
        name: 'get_strategy_recommendations',
        description: 'Analyze current performance and recommend next actions',
        input_schema: { type: 'object', properties: {} },
        execute: async () => {
          const db = getDB();

          const opps = db.prepare(`
            SELECT type, COUNT(*) as count, AVG(estimated_revenue) as avg_est
            FROM opportunities GROUP BY type
          `).all();

          const products = db.prepare(`
            SELECT status, COUNT(*) as count FROM products GROUP BY status
          `).all();

          const topEarners = db.prepare(`
            SELECT title, revenue, sales FROM products
            WHERE revenue > 0 ORDER BY revenue DESC LIMIT 5
          `).all();

          return JSON.stringify({ opportunityBreakdown: opps, productStatus: products, topEarners });
        }
      }
    ];

    super({
      id: 'finance',
      name: 'Finance Tracker',
      systemPrompt: SYSTEM_PROMPT,
      tools,
      maxTurns: 10,
      model: 'claude-haiku-4-5'  // Just math, DB queries, and formatting
    });
  }

  async getDailyReport(): Promise<string> {
    return this.run(`
      Generate a concise daily financial report:
      1. Total earned to date vs. goal
      2. Daily run rate needed
      3. Are we on track? (yes/no and by how much)
      4. Top performing products
      5. Single most important action to take TODAY to hit the goal

      Be direct and data-driven.
    `);
  }
}
