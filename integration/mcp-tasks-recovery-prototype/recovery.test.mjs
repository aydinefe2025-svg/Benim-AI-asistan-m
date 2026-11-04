import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { once } from 'node:events';

const directory = await mkdtemp(join(tmpdir(), 'cano-mcp-tasks-'));
const database = join(directory, 'tasks.sqlite');
const serverFile = fileURLToPath(new URL('./server.mjs', import.meta.url));
const taskCapability = { 'io.modelcontextprotocol/clientCapabilities': {
  extensions: { 'io.modelcontextprotocol/tasks': {} },
} };

function launch() {
  const child = spawn(process.execPath, [serverFile], {
    env: { ...process.env, CANO_TASK_DB: database }, stdio: ['pipe', 'pipe', 'pipe'],
  });
  child.stderr.resume();
  child.stdout.setEncoding('utf8');
  let exitedAlready = false;
  child.on('exit', () => { exitedAlready = true; });
  let buffer = '';
  let nextId = 0;
  const pending = new Map();
  child.stdout.on('data', chunk => {
    buffer += chunk;
    for (;;) {
      const newline = buffer.indexOf('\n');
      if (newline < 0) break;
      const line = buffer.slice(0, newline);
      buffer = buffer.slice(newline + 1);
      if (!line.trim()) continue;
      const message = JSON.parse(line);
      const resolve = pending.get(message.id);
      if (resolve) { pending.delete(message.id); resolve(message); }
    }
  });
  return {
    child,
    request(method, params = {}) {
      const id = ++nextId;
      const response = new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          pending.delete(id);
          reject(new Error(`Timed out waiting for ${method}`));
        }, 5000);
        pending.set(id, message => { clearTimeout(timeout); resolve(message); });
      });
      child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', id, method, params })}\n`);
      return response;
    },
    async crash() {
      if (exitedAlready || child.exitCode !== null) return;
      const exited = once(child, 'exit');
      child.kill('SIGKILL');
      await exited;
    },
    async stop() {
      if (exitedAlready || child.exitCode !== null) return;
      const exited = once(child, 'exit');
      child.stdin.end();
      await exited;
    },
  };
}

let first;
let restarted;
try {
  first = launch();
  const discovery = await first.request('server/discover');
  assert.ok(discovery.result.capabilities.extensions['io.modelcontextprotocol/tasks']);

  const args = { a: 17, b: 25, idempotencyKey: 'integration-run-1' };
  const started = await first.request('tools/call', {
    name: 'add_numbers', arguments: args, _meta: taskCapability,
  });
  assert.equal(started.result.resultType, 'task');
  const taskId = started.result.taskId;
  assert.equal(started.result.status, 'working');
  assert.ok(taskId.length >= 40, 'task ID must have sufficient entropy');

  await first.crash();
  restarted = launch();
  const recovered = await restarted.request('tasks/get', { taskId, _meta: taskCapability });
  assert.equal(recovered.result.status, 'completed');
  assert.match(JSON.stringify(recovered.result.result), /42/);

  const duplicate = await restarted.request('tools/call', {
    name: 'add_numbers', arguments: args, _meta: taskCapability,
  });
  assert.equal(duplicate.result.taskId, taskId, 'idempotent retry must return the same task');
  const conflictingRetry = await restarted.request('tools/call', {
    name: 'add_numbers', arguments: { ...args, a: 18 }, _meta: taskCapability,
  });
  assert.equal(conflictingRetry.error.code, -32602, 'idempotency key must not alias different input');

  const synchronous = await restarted.request('tools/call', {
    name: 'add_numbers', arguments: { a: 2, b: 3 },
  });
  assert.equal(synchronous.result.resultType, undefined);
  assert.match(JSON.stringify(synchronous.result), /5/);

  const unknown = await restarted.request('tasks/get', { taskId: 'unknown-task-id', _meta: taskCapability });
  assert.equal(unknown.error.code, -32602);
  const missingCapability = await restarted.request('tasks/get', { taskId, _meta: {} });
  assert.equal(missingCapability.error.code, -32021);
  const updateAck = await restarted.request('tasks/update', { taskId, inputResponses: {}, _meta: taskCapability });
  assert.equal(updateAck.result.resultType, 'complete');

  const cancellable = await restarted.request('tools/call', {
    name: 'add_numbers', arguments: { a: 1, b: 1, idempotencyKey: 'cancel-me' }, _meta: taskCapability,
  });
  const cancelId = cancellable.result.taskId;
  await restarted.request('tasks/cancel', { taskId: cancelId, _meta: taskCapability });
  assert.equal((await restarted.request('tasks/get', { taskId: cancelId, _meta: taskCapability })).result.status, 'cancelled');

  console.log('PASS: MCP task create/get, hard restart recovery, idempotency, capability negotiation, cancellation, unknown ID rejection.');
} finally {
  if (restarted) await restarted.stop();
  if (first) await first.stop();
  await rm(directory, { recursive: true, force: true });
}
