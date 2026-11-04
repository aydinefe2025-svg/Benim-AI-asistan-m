/** Genuine pinned Mastra package smoke, isolated from production. */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Mastra } from '@mastra/core/mastra';
import { createTool } from '@mastra/core/tools';
import { MCPServer } from '@mastra/mcp';
import { LibSQLStore } from '@mastra/libsql';
import { z } from 'zod';

const minNode = [22, 22];
const [major, minor] = process.versions.node.split('.').map(Number);

test('Node runtime passes known posthog peer engine floor', () => {
  assert.ok(major > minNode[0] || (major === minNode[0] && minor >= minNode[1]),
    `Node ${process.version} below 22.22; do not claim validated peer compatibility`);
});

test('actual MCPServer, tool, and file-backed Mastra store register together', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'cano-mastra-'));
  try {
    const addNumbers = createTool({
      id: 'add_numbers',
      description: 'Add two integers without any side effects.',
      inputSchema: z.object({ a: z.number().int(), b: z.number().int() }),
      execute: async ({ a, b }) => ({ result: a + b }),
    });
    const server = new MCPServer({
      id: 'cano-mcp-storage-smoke',
      name: 'CANO MCP Storage Smoke',
      version: '0.0.1',
      tools: { addNumbers },
      tasks: { tools: { addNumbers: { mode: 'always', recover: true } } },
    });
    const mastra = new Mastra({
      storage: new LibSQLStore({ id: 'cano-mcp-smoke', url: `file:${join(dir, 'smoke.db')}` }),
      backgroundTasks: { enabled: true },
      mcpServers: { cano: server },
    });
    assert.ok(mastra.getStorage(), 'Mastra storage missing');
    const actual = await server.executeTool('add_numbers', { a: 17, b: 25 });
    assert.match(JSON.stringify(actual), /42/, 'Real Mastra tool output was not 42');
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
