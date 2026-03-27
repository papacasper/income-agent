import axios from 'axios';

/**
 * Web search using Brave Search API.
 * Free tier: 2000 queries/month. Docs: https://api.search.brave.com
 */
export async function webSearch(query: string, numResults = 10): Promise<Array<{ title: string; url: string; snippet: string }>> {
  const key = process.env.BRAVE_API_KEY;
  if (!key) throw new Error('BRAVE_API_KEY not set');

  const res = await axios.get('https://api.search.brave.com/res/v1/web/search', {
    headers: {
      'Accept': 'application/json',
      'Accept-Encoding': 'gzip',
      'X-Subscription-Token': key,
    },
    params: { q: query, count: numResults, search_lang: 'en' },
    timeout: 10000,
  });

  const results = res.data?.web?.results || [];
  return results.map((r: { title: string; url: string; description: string }) => ({
    title: r.title,
    url: r.url,
    snippet: r.description || '',
  }));
}

export async function webFetch(url: string): Promise<string> {
  const res = await axios.get(url, {
    timeout: 15000,
    headers: { 'User-Agent': 'Mozilla/5.0 (compatible; IncomeAgent/1.0)' },
    maxContentLength: 500000,
  });
  return String(res.data).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 10000);
}

export async function getTrendingTopics(): Promise<string[]> {
  // Use Brave to find what's trending in digital products / AI tools
  const results = await webSearch('trending digital products AI tools 2025 best selling', 5);
  const topics = results.map(r => r.title).filter(Boolean);

  // Also pull Google Trends RSS as supplemental
  try {
    const res = await axios.get('https://trends.google.com/trends/trendingsearches/daily/rss?geo=US', {
      timeout: 8000,
      headers: { 'User-Agent': 'Mozilla/5.0' },
    });
    const matches = String(res.data).match(/<title><!\[CDATA\[([^\]]+)\]\]><\/title>/g) || [];
    const trending = matches.slice(1, 10).map(m => m.replace(/<[^>]+>/g, '').replace(/CDATA\[|\]\]/g, '').trim());
    return [...new Set([...topics, ...trending])];
  } catch {
    return topics.length ? topics : ['AI prompt packs', 'Notion templates', 'automation tools', 'passive income', 'digital downloads'];
  }
}
