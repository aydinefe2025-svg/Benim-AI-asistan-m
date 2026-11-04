import { DatabaseSync } from 'node:sqlite';
import { randomBytes } from 'node:crypto';
import { createInterface } from 'node:readline';

const db = new DatabaseSync(process.env.CANO_TASK_DB);
db.exec(`
  PRAGMA journal_mode = WAL;
  CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('working','completed','failed','cancelled')),
    input_json TEXT NOT NULL,
    result_json TEXT,
    idempotency_key TEXT UNIQUE,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
  );
`);

function compute(input) {
  if (!Number.isSafeInteger(input.a) || !Number.isSafeInteger(input.b)) {
    throw new TypeError('a and b must be safe integers');
  }
  return { result: input.a + input.b };
}

function finish(taskId, input) {
  try {
    const result = compute(input);
    db.prepare("UPDATE tasks SET status='completed', result_json=?, last_updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE task_id=? AND status='working'")
      .run(JSON.stringify(result), taskId);
  } catch (error) {
    db.prepare("UPDATE tasks SET status='failed', result_json=?, last_updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE task_id=? AND status='working'")
      .run(JSON.stringify({ message: error.message }), taskId);
  }
}

// This recovery path is safe only because the prototype tool is deterministic and side-effect free.
for (const row of db.prepare("SELECT task_id, input_json FROM tasks WHERE status='working'").all()) {
  finish(row.task_id, JSON.parse(row.input_json));
}

const send = (id, result) => process.stdout.write(`${JSON.stringify({ jsonrpc: '2.0', id, result })}\n`);
const fail = (id, code, message, data) => process.stdout.write(`${JSON.stringify({ jsonrpc: '2.0', id, error: { code, message, ...(data ? { data } : {}) } })}\n`);
const supportsTasks = (params) => Boolean(
  params?._meta?.['io.modelcontextprotocol/clientCapabilities']?.extensions?.['io.modelcontextprotocol/tasks'],
);
const requiresTasks = (id, params) => {
  if (supportsTasks(params)) return true;
  fail(id, -32021, 'Missing required client capability', {
    requiredCapabilities: { extensions: { 'io.modelcontextprotocol/tasks': {} } },
  });
  return false;
};

const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
rl.on('line', (line) => {
  let message;
  try { message = JSON.parse(line); } catch { return; }
  const { id, method, params = {} } = message;
  try {
    if (method === 'server/discover') {
      send(id, {
        protocolVersion: '2026-07-28',
        serverInfo: { name: 'cano-task-recovery-prototype', version: '0.0.1' },
        capabilities: { tools: {}, extensions: { 'io.modelcontextprotocol/tasks': {} } },
      });
      return;
    }
    if (method === 'tools/list') {
      send(id, { tools: [{ name: 'add_numbers', description: 'Deterministic recovery smoke tool', inputSchema: {
        type: 'object', properties: { a: { type: 'integer' }, b: { type: 'integer' }, idempotencyKey: { type: 'string' } }, required: ['a','b'], additionalProperties: false,
      } }] });
      return;
    }
    if (method === 'tools/call') {
      if (params.name !== 'add_numbers') return fail(id, -32602, 'Unknown tool');
      const input = params.arguments ?? {};
      if (!supportsTasks(params)) {
        return send(id, { content: [{ type: 'text', text: JSON.stringify(compute(input)) }], isError: false });
      }
      const key = typeof input.idempotencyKey === 'string' && input.idempotencyKey.length <= 200
        ? input.idempotencyKey : null;
      let row = key ? db.prepare('SELECT task_id,status,created_at,last_updated_at FROM tasks WHERE idempotency_key=?').get(key) : null;
      if (!row) {
        const taskId = randomBytes(32).toString('base64url');
        db.prepare("INSERT INTO tasks(task_id,status,input_json,idempotency_key) VALUES(?,'working',?,?)")
          .run(taskId, JSON.stringify({ a: input.a, b: input.b }), key);
        row = db.prepare('SELECT task_id,status,created_at,last_updated_at FROM tasks WHERE task_id=?').get(taskId);
        const copied = { a: input.a, b: input.b };
        setTimeout(() => finish(taskId, copied), 1500).unref();
      }
      return send(id, { resultType: 'task', taskId: row.task_id, status: row.status,
        createdAt: row.created_at, lastUpdatedAt: row.last_updated_at, ttlMs: 86400000, pollIntervalMs: 100 });
    }
    if (method === 'tasks/get') {
      if (!requiresTasks(id, params)) return;
      const row = db.prepare('SELECT task_id,status,result_json,created_at,last_updated_at FROM tasks WHERE task_id=?').get(params.taskId);
      if (!row) return fail(id, -32602, 'Unknown task id');
      const task = { taskId: row.task_id, status: row.status, createdAt: row.created_at,
        lastUpdatedAt: row.last_updated_at, ttlMs: 86400000, pollIntervalMs: 100 };
      if (row.status === 'completed') task.result = { content: [{ type: 'text', text: row.result_json }], isError: false };
      if (row.status === 'failed') task.error = { code: -32603, message: JSON.parse(row.result_json).message };
      return send(id, { resultType: 'complete', ...task });
    }
    if (method === 'tasks/cancel') {
      if (!requiresTasks(id, params)) return;
      const update = db.prepare("UPDATE tasks SET status='cancelled',last_updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE task_id=? AND status='working'").run(params.taskId);
      if (update.changes === 0 && !db.prepare('SELECT 1 FROM tasks WHERE task_id=?').get(params.taskId)) return fail(id, -32602, 'Unknown task id');
      return send(id, { resultType: 'complete' });
    }
    fail(id, -32601, `Method not found: ${method}`);
  } catch (error) {
    fail(id, -32603, `Request failed: ${error.message}`);
  }
});
rl.on('close', () => db.close());
