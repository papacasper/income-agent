import { BaseAgent, AgentTool } from './base-agent.js';
import { webSearch, webFetch, getTrendingTopics } from '../tools/web.js';
import { getDB, postMessage } from '../db/index.js';

const SYSTEM_PROMPT = `You are an elite market research agent specializing in finding high-profit digital product and service opportunities.

Your mission: Find opportunities that can realistically generate revenue quickly using AI automation.

Focus on:
1. **Digital products** - Templates (Notion, Figma, Excel, Canva), prompt packs, guides, toolkits
2. **Digital services** - SEO audits, copy, social media content, scripts, resumes
3. **Micro-SaaS** - Simple tools people pay for monthly
4. **Arbitrage** - Cheap/free info people will pay for when packaged well

For each opportunity assess:
- Market demand (search volume, competition)
- Price point ($5-$97 sweet spot for digital products)
- Creation time with AI (<2 hours)
- Likely conversion rate

Output structured JSON for each opportunity found.`;

export class ScannerAgent extends BaseAgent {
  constructor() {
    const tools: AgentTool[] = [
      {
        name: 'web_search',
        description: 'Search the web for market opportunities, trends, and competitor data',
        input_schema: {
          type: 'object',
          properties: {
            query: { type: 'string', description: 'Search query' },
            numResults: { type: 'number', description: 'Number of results (default 10)' }
          },
          required: ['query']
        },
        execute: async (input) => {
          const results = await webSearch(input.query as string, (input.numResults as number) || 10);
          return JSON.stringify(results, null, 2);
        }
      },
      {
        name: 'fetch_page',
        description: 'Fetch and read a webpage for competitive research',
        input_schema: {
          type: 'object',
          properties: { url: { type: 'string' } },
          required: ['url']
        },
        execute: async (input) => webFetch(input.url as string)
      },
      {
        name: 'get_trends',
        description: 'Get current trending topics to find hot niches',
        input_schema: { type: 'object', properties: {} },
        execute: async () => {
          const trends = await getTrendingTopics();
          return JSON.stringify(trends);
        }
      },
      {
        name: 'save_opportunity',
        description: 'Save a validated opportunity to the database',
        input_schema: {
          type: 'object',
          properties: {
            type: {
              type: 'string',
              enum: ['digital_product', 'service', 'affiliate', 'micro_saas'],
              description: 'Opportunity type'
            },
            title: { type: 'string', description: 'Product/service title' },
            description: { type: 'string', description: 'What it is and why it sells' },
            estimatedRevenue: { type: 'number', description: 'Estimated monthly revenue in USD' },
            effortHours: { type: 'number', description: 'Hours to create with AI assistance' },
            platform: { type: 'string', description: 'Platform to sell on (gumroad, etsy, etc.)' },
            metadata: { type: 'object', description: 'Extra data like keywords, competitors, price range' }
          },
          required: ['type', 'title', 'description', 'estimatedRevenue', 'effortHours', 'platform']
        },
        execute: async (input) => {
          const db = getDB();
          const result = db.prepare(`
            INSERT INTO opportunities (type, title, description, estimated_revenue, effort_hours, platform, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
          `).run(
            input.type, input.title, input.description,
            input.estimatedRevenue, input.effortHours, input.platform,
            input.metadata ? JSON.stringify(input.metadata) : null
          );

          const id = result.lastInsertRowid;
          postMessage('scanner', 'content', 'task', {
            task: 'create_product',
            opportunityId: id,
            title: input.title,
            description: input.description,
            platform: input.platform,
            metadata: input.metadata
          });

          console.log(`[Scanner] Saved opportunity #${id}: ${input.title}`);
          return `Saved opportunity #${id}`;
        }
      },
      {
        name: 'get_existing_opportunities',
        description: 'Check what opportunities have already been found to avoid duplicates',
        input_schema: { type: 'object', properties: {} },
        execute: async () => {
          const db = getDB();
          const rows = db.prepare('SELECT title, type, status FROM opportunities ORDER BY created_at DESC LIMIT 20').all();
          return JSON.stringify(rows);
        }
      }
    ];

    super({
      id: 'scanner',
      name: 'Market Scanner',
      systemPrompt: SYSTEM_PROMPT,
      tools,
      maxTurns: 25,
      model: 'claude-sonnet-4-6'  // Needs good reasoning for market research
    });
  }

  async scan(): Promise<string> {
    return this.run(`
      Perform a comprehensive market scan to find the TOP 5 most promising digital product opportunities right now.

      Steps:
      1. Get trending topics
      2. Search for "best selling digital products 2024 2025 gumroad etsy"
      3. Search for "notion template best sellers" and "figma template best sellers"
      4. Search for "AI prompt packs bestsellers"
      5. Look at what's NOT yet saturated but has clear demand
      6. Check existing opportunities to avoid duplicates
      7. Save the top 5 opportunities with full details

      For each opportunity, estimate:
      - How many units could sell per month at what price
      - Time to create with AI assistance
      - Which platform is best

      Be aggressive about finding things that can actually sell. We need revenue fast.
    `);
  }
}
