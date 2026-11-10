// Verify both request paths without submitting any robot task.
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const web = process.env.RMF_WEB_ROOT || '/mnt/UbuntuData/rmf-web';
const ts = require(path.join(web, 'packages/dashboard/node_modules/typescript'));
const source = fs.readFileSync(path.join(__dirname, 'overlay/src/components/brin/patrol-request.ts'), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }}).outputText;
const result = { exports: {} };
new Function('exports', 'require', 'module', js)(result.exports, require, result);
const { makePatrolRequest, submitPatrol } = result.exports;
(async () => {
  const calls = [];
  const api = {
    postDispatchTaskTasksDispatchTaskPost: async (req) => { calls.push(req); return { data: { success: true } }; },
    postRobotTaskTasksRobotTaskPost: async (req) => { calls.push(req); return { data: { success: true } }; },
  };
  const request = makePatrolRequest(['ws_p0', 'utara_WS'], 2, 'operator');
  assert.deepStrictEqual(request.description, { places: ['ws_p0', 'utara_WS'], rounds: 2 });
  assert.throws(() => makePatrolRequest([], 1, 'operator'));
  assert.throws(() => makePatrolRequest(['a'], 1.5, 'operator'));
  await submitPatrol(api, request, null);
  assert.strictEqual(calls[0].type, 'dispatch_task_request');
  assert(!('robot' in calls[0]));
  for (const choice of [{ fleet: 'Devi', robot: 'devi' }, { fleet: 'HuskyA200', robot: 'husky_0' }]) {
    await submitPatrol(api, request, choice);
    assert.deepStrictEqual(calls[calls.length - 1], { type: 'robot_task_request', ...choice, request });
  }
  api.postDispatchTaskTasksDispatchTaskPost = async () => ({ data: { success: false, errors: ['rejected'] } });
  await assert.rejects(submitPatrol(api, request, null), /rejected/);
  api.postRobotTaskTasksRobotTaskPost = async () => undefined;
  await assert.rejects(submitPatrol(api, request, { fleet: 'Devi', robot: 'devi' }));
  console.log('Patrol validation, bidding, both manual robots and error handling passed.');
})().catch((error) => { console.error(error); process.exit(1); });
