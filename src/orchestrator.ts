import 'dotenv/config';
import cron from 'node-cron';
import { ScannerAgent } from './agents/scanner.js';
import { FinanceAgent } from './agents/finance.js';
import { readMessages } from './db/index.js';
import { getDB, getTotals } from './db/index.js';
import { execSync } from 'child_process';
import path from 'path';

const scanner = new ScannerAgent();
const finance = new FinanceAgent();

async function runScan() {
  console.log('\n=== [ORCHESTRATOR] Running market scan ===');
  try {
    const result = await scanner.scan();
    console.log('[Scanner Result]', result.slice(0, 500));
  } catch (err) {
    console.error('[Scanner Error]', err);
  }
}

async function runContentPipeline() {
  console.log('\n=== [ORCHESTRATOR] Running content pipeline ===');
  try {
    // Trigger Python content agent for any pending tasks
    const pendingMessages = readMessages('content');
    if (pendingMessages.length > 0) {
      console.log(`[Orchestrator] ${pendingMessages.length} content tasks queued`);
      // Run Python content agent
      execSync('.venv/bin/python3 python/agents/content_agent.py', {
        cwd: path.join(__dirname, '..'),
        stdio: 'inherit',
        env: { ...process.env }
      });
    }
  } catch (err) {
    console.error('[Content Pipeline Error]', err);
  }
}

async function runSales() {
  console.log('\n=== [ORCHESTRATOR] Running sales agent (Playwright) ===');
  try {
    execSync('.venv/bin/python3 python/agents/sales_agent.py', {
      cwd: path.join(__dirname, '..'),
      stdio: 'inherit',
      env: { ...process.env }
    });
  } catch (err) {
    console.error('[Sales Error]', err);
  }
}

async function runDailyReport() {
  console.log('\n=== [ORCHESTRATOR] Generating daily report ===');
  try {
    const report = await finance.getDailyReport();
    console.log('\n' + '='.repeat(60));
    console.log('DAILY FINANCIAL REPORT');
    console.log('='.repeat(60));
    console.log(report);
    console.log('='.repeat(60) + '\n');

    // Also run Python analytics
    try {
      execSync('.venv/bin/python3 python/agents/analytics_agent.py', {
        cwd: path.join(__dirname, '..'),
        stdio: 'inherit',
        env: { ...process.env }
      });
    } catch {
      // Analytics agent is optional
    }
  } catch (err) {
    console.error('[Finance Error]', err);
  }
}

async function runBlog(articles = 3) {
  console.log(`\n=== [ORCHESTRATOR] Running blog agent (${articles} articles) ===`);
  try {
    execSync(`.venv/bin/python3 python/agents/blog_agent.py --articles ${articles}`, {
      cwd: path.join(__dirname, '..'),
      stdio: 'inherit',
      env: { ...process.env }
    });
  } catch (err) {
    console.error('[Blog Error]', err);
  }
}

async function runSalesSync() {
  console.log('\n=== [ORCHESTRATOR] Syncing sales data ===');
  try {
    execSync('.venv/bin/python3 python/agents/sales_agent.py --sync-only', {
      cwd: path.join(__dirname, '..'),
      stdio: 'inherit',
      env: { ...process.env }
    });
  } catch (err) {
    console.error('[Sales Sync Error]', err);
  }
}

function printStatus() {
  const totals = getTotals();
  const goal = Number(process.env.GOAL_AMOUNT || 20000);
  const pct = ((totals.net / goal) * 100).toFixed(1);
  console.log(`\n[STATUS] Revenue: $${totals.net.toFixed(2)} / $${goal} (${pct}%) | Products: ${totals.products} | Sales: ${totals.sales}`);
}

async function main() {
  console.log('='.repeat(60));
  console.log('INCOME AGENT SYSTEM STARTING');
  console.log(`Goal: $${process.env.GOAL_AMOUNT || 20000} in 60 days`);
  console.log(`Start: ${process.env.START_DATE || '2026-03-24'}`);
  console.log('='.repeat(60));

  // Initialize DB
  getDB();
  printStatus();

  const args = process.argv.slice(2);
  const cmd = args[0];

  if (cmd === 'scan') {
    await runScan();
    await runContentPipeline();
  } else if (cmd === 'sell') {
    await runSales();
  } else if (cmd === 'blog') {
    const n = args[1] ? parseInt(args[1]) : 3;
    await runBlog(n);
  } else if (cmd === 'report') {
    await runDailyReport();
  } else if (cmd === 'sync') {
    await runSalesSync();
  } else if (cmd === 'once') {
    await runScan();
    await runContentPipeline();
    await runSales();
    await runBlog(3);
    await runDailyReport();
  } else {
    // Daemon mode
    const scanInterval = Number(process.env.SCAN_INTERVAL || 30);
    const executeInterval = Number(process.env.EXECUTE_INTERVAL || 60);

    console.log(`\nRunning in daemon mode:`);
    console.log(`  Market scan every ${scanInterval} min`);
    console.log(`  Products/sales every ${executeInterval} min`);
    console.log(`  Blog: 3 articles at 6am, 3 more at 2pm`);
    console.log(`  Daily report at 8am\n`);

    // Run immediately on start
    await runScan();
    await runContentPipeline();
    await runSales();
    await runBlog(3);
    await runDailyReport();

    cron.schedule(`*/${scanInterval} * * * *`, async () => {
      await runScan();
      await runContentPipeline();
      printStatus();
    });

    cron.schedule(`*/${executeInterval} * * * *`, async () => {
      await runSales();
      await runSalesSync();
      printStatus();
    });

    // Blog: 3 articles at 6am and 2pm daily
    cron.schedule('0 6 * * *', () => runBlog(3));
    cron.schedule('0 14 * * *', () => runBlog(3));

    // Daily report at 8am
    cron.schedule('0 8 * * *', runDailyReport);

    // Sync sales every 2 hours
    cron.schedule('0 */2 * * *', runSalesSync);

    console.log('Daemon running. Press Ctrl+C to stop.\n');
    process.stdin.resume();
  }
}

main().catch(console.error);
