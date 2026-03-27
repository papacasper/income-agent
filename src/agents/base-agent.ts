import Anthropic from '@anthropic-ai/sdk';
import { getDB, postMessage, readMessages, updateAgentState } from '../db/index.js';

export interface AgentTool {
  name: string;
  description: string;
  input_schema: {
    type: 'object';
    properties: Record<string, unknown>;
    required?: string[];
  };
  execute: (input: Record<string, unknown>) => Promise<string>;
}

export interface AgentConfig {
  id: string;
  name: string;
  systemPrompt: string;
  tools: AgentTool[];
  maxTurns?: number;
  model?: string;
}

export class BaseAgent {
  protected client: Anthropic;
  protected config: AgentConfig;
  protected model: string;

  constructor(config: AgentConfig) {
    this.client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
    this.config = config;
    this.model = config.model || 'claude-sonnet-4-6';
  }

  async run(task: string): Promise<string> {
    updateAgentState(this.config.id, 'running', task);
    console.log(`[${this.config.name}] Starting: ${task}`);

    const messages: Anthropic.MessageParam[] = [
      { role: 'user', content: task }
    ];

    const tools: Anthropic.Tool[] = this.config.tools.map(t => ({
      name: t.name,
      description: t.description,
      input_schema: t.input_schema
    }));

    let result = '';
    let turns = 0;
    const maxTurns = this.config.maxTurns || 20;

    while (turns < maxTurns) {
      turns++;

      const useThinking = this.model.includes('sonnet') || this.model.includes('opus');
      const response = await this.client.messages.create({
        model: this.model,
        max_tokens: 8192,
        ...(useThinking ? { thinking: { type: 'adaptive' } } : {}),
        system: this.config.systemPrompt,
        tools: tools.length > 0 ? tools : undefined,
        messages
      });

      // Append assistant response
      messages.push({ role: 'assistant', content: response.content });

      if (response.stop_reason === 'end_turn') {
        result = response.content
          .filter(b => b.type === 'text')
          .map(b => (b as Anthropic.TextBlock).text)
          .join('\n');
        break;
      }

      if (response.stop_reason === 'tool_use') {
        const toolResults: Anthropic.ToolResultBlockParam[] = [];

        for (const block of response.content) {
          if (block.type !== 'tool_use') continue;

          const tool = this.config.tools.find(t => t.name === block.name);
          let toolResult: string;

          if (!tool) {
            toolResult = `Error: Unknown tool "${block.name}"`;
          } else {
            try {
              console.log(`[${this.config.name}] Calling tool: ${block.name}`);
              toolResult = await tool.execute(block.input as Record<string, unknown>);
            } catch (err) {
              toolResult = `Error: ${err instanceof Error ? err.message : String(err)}`;
            }
          }

          toolResults.push({
            type: 'tool_result',
            tool_use_id: block.id,
            content: toolResult
          });
        }

        messages.push({ role: 'user', content: toolResults });
        continue;
      }

      // Unknown stop reason - extract text and stop
      result = response.content
        .filter(b => b.type === 'text')
        .map(b => (b as Anthropic.TextBlock).text)
        .join('\n');
      break;
    }

    updateAgentState(this.config.id, 'idle', undefined);
    return result;
  }

  protected postMessage(to: string | null, type: string, payload: object) {
    postMessage(this.config.id, to, type, payload);
  }

  protected readMyMessages() {
    return readMessages(this.config.id);
  }

  protected getDB() {
    return getDB();
  }
}
