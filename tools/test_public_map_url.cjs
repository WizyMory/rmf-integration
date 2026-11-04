// Run with the pinned dashboard Node and dependencies, without publishing a tunnel.
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const web = process.env.RMF_WEB_ROOT || '/mnt/UbuntuData/rmf-web';
const ts = require(path.join(web, 'packages/dashboard/node_modules/typescript'));
const source = fs.readFileSync(path.join(__dirname,
  '../laptop/src/brin_husky_distributed/web/public-map-url.ts'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const moduleExports = {};
new Function('exports', compiled)(moduleExports);
const rewrite = moduleExports.publicMapImageUrl;
const api = 'https://example.trycloudflare.com/api';
assert.strictEqual(rewrite('http://192.168.0.218:8000/cache/map.png', api),
  `${api}/cache/map.png`);
assert.strictEqual(rewrite('/cache/map.png?version=2', api), `${api}/cache/map.png?version=2`);
assert.strictEqual(rewrite('/api/cache/map.png', api), '/api/cache/map.png');
assert.strictEqual(rewrite(`${api}/cache/map.png`, api), `${api}/cache/map.png`);
for (const value of ['data:image/png;base64,abc', 'blob:https://example.com/id',
  'https://example.com/image.png', 'http://[invalid']) {
  assert.strictEqual(rewrite(value, api), value);
}
console.log('Public map image URL checks passed (REST and Socket.IO payload compatibility).');
