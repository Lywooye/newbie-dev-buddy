import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, readdir, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const cli = fileURLToPath(new URL('../bin/acceptance.mjs', import.meta.url));
const passingTest = "import test from 'node:test'; import assert from 'node:assert/strict'; test('adds integers', () => assert.equal(2 + 2, 4));\n";
const passedChecks = { status: 'passed', checks: [{ name: 'saved output', status: 'passed' }] };

async function put(root, relative, contents) {
  const file = path.join(root, relative);
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, typeof contents === 'string' ? contents : JSON.stringify(contents, null, 2));
}

function tapStep(extra = {}) {
  return { id: 'behavior', command: ['node', '--test', '--test-reporter=tap', 'test/example.test.mjs'], format: 'tap', ...extra };
}

function checksStep(extra = {}) {
  return { id: 'behavior', command: ['node', 'check.mjs'], format: 'checks', ...extra };
}

async function fixture(t, { steps = [tapStep()], files = {}, config = {} } = {}) {
  const root = await mkdtemp(path.join(tmpdir(), 'acceptance-cli-test-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  await put(root, 'test/example.test.mjs', passingTest);
  await put(root, 'acceptance.config.json', { schema: 1, name: 'Temporary acceptance fixture', exclude: [], dependencyDirs: [], steps, ...config });
  for (const [file, value] of Object.entries(files)) await put(root, file, value);
  return root;
}

function invoke(...args) {
  const result = spawnSync(process.execPath, [cli, ...args], { encoding: 'utf8', timeout: 15_000 });
  assert.equal(result.error, undefined, `CLI could not complete: ${result.error?.message}\n${result.stderr}`);
  assert.notEqual(result.status, null, `CLI terminated by ${result.signal}`);
  return result;
}

function good(result) {
  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
}

function bad(result) {
  assert.notEqual(result.status, 0, `Unexpected acceptance:\n${result.stdout}\n${result.stderr}`);
}

async function receipts(root) {
  let runs;
  try { runs = await readdir(path.join(root, '.acceptance'), { withFileTypes: true }); }
  catch (error) { if (error.code === 'ENOENT') return []; throw error; }
  const found = [];
  for (const run of runs.filter(entry => entry.isDirectory())) {
    const file = path.join(root, '.acceptance', run.name, 'report.json');
    try { found.push({ file, report: JSON.parse(await readFile(file, 'utf8')) }); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  return found;
}

async function rejected(root, result) {
  bad(result);
  for (const { report } of await receipts(root)) assert.notEqual(report.status, 'passed');
}

async function accepted(root) {
  good(invoke('run', '--project', root));
  const result = await receipts(root);
  assert.equal(result.length, 1);
  assert.equal(result[0].report.status, 'passed');
  return result[0];
}

test('runs an actual Node test in a copied workspace and verifies its receipt', async t => {
  const root = await fixture(t);
  const { file } = await accepted(root);
  good(invoke('check', '--project', root, '--receipt', file));
  assert.equal(await readFile(path.join(root, 'test/example.test.mjs'), 'utf8'), passingTest);
  assert.equal(await readFile(path.join(path.dirname(file), 'workspace/test/example.test.mjs'), 'utf8'), passingTest);
});

test('a test assertion failure cannot pass', async t => {
  const root = await fixture(t, { files: { 'test/example.test.mjs': "import test from 'node:test'; import assert from 'node:assert/strict'; test('wrong result', () => assert.equal(2 + 2, 5));" } });
  await rejected(root, invoke('run', '--project', root));
});

test('skipped tests cannot pass even when Node exits successfully', async t => {
  const root = await fixture(t, { files: { 'test/example.test.mjs': "import test from 'node:test'; test.skip('not exercised', () => {});" } });
  await rejected(root, invoke('run', '--project', root));
});

test('TODO tests cannot pass even when Node exits successfully', async t => {
  const root = await fixture(t, { files: { 'test/example.test.mjs': "import test from 'node:test'; test.todo('future behavior');" } });
  await rejected(root, invoke('run', '--project', root));
});

test('an exit-zero TAP report with no tests cannot pass', async t => {
  const summary = 'TAP version 13\n1..0\n# tests 0\n# suites 0\n# pass 0\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0';
  const root = await fixture(t, { steps: [tapStep({ command: ['node', '-e', `console.log(${JSON.stringify(summary)})`] })] });
  await rejected(root, invoke('run', '--project', root));
});

test('TAP missing its summary cannot pass', async t => {
  const root = await fixture(t, { steps: [tapStep({ command: ['node', '-e', "console.log('All tests passed')"] })] });
  await rejected(root, invoke('run', '--project', root));
});

test('TAP with inconsistent counts cannot pass', async t => {
  const summary = 'TAP version 13\n1..2\n# tests 2\n# pass 1\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0';
  const root = await fixture(t, { steps: [tapStep({ command: ['node', '-e', `console.log(${JSON.stringify(summary)})`] })] });
  await rejected(root, invoke('run', '--project', root));
});

test('an exit-only configuration cannot claim behavioral acceptance', async t => {
  const root = await fixture(t, { steps: [{ id: 'build', command: ['node', '-e', 'process.exit(0)'], format: 'exit' }] });
  await rejected(root, invoke('run', '--project', root));
});

test('duplicate step identifiers cannot overwrite each other’s evidence', async t => {
  const root = await fixture(t, { steps: [tapStep(), tapStep()] });
  await rejected(root, invoke('run', '--project', root));
});

test('checks format accepts named checks and binds a real generated artifact', async t => {
  const root = await fixture(t, {
    steps: [checksStep({ evidence: ['artifact.txt'] })],
    files: { 'check.mjs': `import {writeFileSync} from 'node:fs'; writeFileSync('artifact.txt', 'actual output'); console.log(${JSON.stringify(JSON.stringify(passedChecks))});` },
  });
  const { file } = await accepted(root);
  good(invoke('check', '--project', root, '--receipt', file));
  assert.equal(await readFile(path.join(path.dirname(file), 'workspace/artifact.txt'), 'utf8'), 'actual output');
  await assert.rejects(readFile(path.join(root, 'artifact.txt')), { code: 'ENOENT' });
});

for (const [name, body] of [
  ['empty checks', { status: 'passed', checks: [] }],
  ['failed check', { status: 'passed', checks: [{ name: 'behavior', status: 'failed' }] }],
  ['missing check name', { status: 'passed', checks: [{ status: 'passed' }] }],
  ['duplicate check names', { status: 'passed', checks: [{ name: 'same', status: 'passed' }, { name: 'same', status: 'passed' }] }],
  ['failed overall status', { status: 'failed', checks: [{ name: 'behavior', status: 'passed' }] }],
]) {
  test(`${name} cannot pass checks format`, async t => {
    const root = await fixture(t, { steps: [checksStep()], files: { 'check.mjs': `console.log(${JSON.stringify(JSON.stringify(body))});` } });
    await rejected(root, invoke('run', '--project', root));
  });
}

test('malformed checks JSON cannot pass', async t => {
  const root = await fixture(t, { steps: [checksStep()], files: { 'check.mjs': "console.log('this is not a JSON result');" } });
  await rejected(root, invoke('run', '--project', root));
});

test('a nonzero process exit cannot be overridden by successful checks JSON', async t => {
  const root = await fixture(t, { steps: [checksStep()], files: { 'check.mjs': `console.log(${JSON.stringify(JSON.stringify(passedChecks))}); process.exitCode = 1;` } });
  await rejected(root, invoke('run', '--project', root));
});

test('a missing required evidence file prevents acceptance', async t => {
  const root = await fixture(t, { steps: [tapStep({ evidence: ['missing-artifact.txt'] })] });
  await rejected(root, invoke('run', '--project', root));
});

test('a command timeout remains non-passing', async t => {
  const root = await fixture(t, { steps: [checksStep({ command: ['node', '-e', 'setInterval(() => {}, 1000)'], timeoutMs: 100 })] });
  await rejected(root, invoke('run', '--project', root));
});

test('source edits after acceptance make the receipt stale', async t => {
  const root = await fixture(t);
  const { file } = await accepted(root);
  await put(root, 'test/example.test.mjs', passingTest.replace('2 + 2, 4', '2 + 2, 5'));
  bad(invoke('check', '--project', root, '--receipt', file));
});

test('a new previously untracked source file makes the receipt stale', async t => {
  const root = await fixture(t);
  const { file } = await accepted(root);
  await put(root, 'new-source.mjs', 'export const added = true;');
  bad(invoke('check', '--project', root, '--receipt', file));
});

test('deleting a previously verified input makes the receipt stale', async t => {
  const root = await fixture(t, { files: { 'source.mjs': 'export const answer = 42;' } });
  const { file } = await accepted(root);
  await rm(path.join(root, 'source.mjs'));
  bad(invoke('check', '--project', root, '--receipt', file));
});

test('input mutations during a command prevent a passing receipt', async t => {
  const root = await fixture(t, { steps: [checksStep()] });
  await put(root, 'check.mjs', `import {writeFileSync} from 'node:fs'; writeFileSync(${JSON.stringify(path.join(root, 'changed-during-run.txt'))}, 'changed'); console.log(${JSON.stringify(JSON.stringify(passedChecks))});`);
  await rejected(root, invoke('run', '--project', root));
});

test('snapshot input mutation during a command prevents a passing receipt', async t => {
  const root = await fixture(t, { steps: [checksStep()], files: {
    'source.mjs': 'export const original = true;',
    'check.mjs': `import {writeFileSync} from 'node:fs'; writeFileSync('source.mjs', 'mutated'); console.log(${JSON.stringify(JSON.stringify(passedChecks))});`,
  } });
  await rejected(root, invoke('run', '--project', root));
  assert.equal(await readFile(path.join(root, 'source.mjs'), 'utf8'), 'export const original = true;');
});

test('mutating generated evidence invalidates a passed receipt', async t => {
  const root = await fixture(t, { steps: [checksStep({ evidence: ['artifact.txt'] })], files: {
    'check.mjs': `import {writeFileSync} from 'node:fs'; writeFileSync('artifact.txt', 'original'); console.log(${JSON.stringify(JSON.stringify(passedChecks))});`,
  } });
  const { file } = await accepted(root);
  await writeFile(path.join(path.dirname(file), 'workspace/artifact.txt'), 'replacement');
  bad(invoke('check', '--project', root, '--receipt', file));
});

test('altering a raw TAP log invalidates the receipt even when its passing counts remain valid', async t => {
  const root = await fixture(t);
  const { file } = await accepted(root);
  const logDir = path.join(path.dirname(file), 'logs');
  const logFiles = await readdir(logDir);
  let altered = 0;
  for (const name of logFiles) {
    const log = path.join(logDir, name);
    const content = await readFile(log, 'utf8');
    if (content.includes('TAP version 13') && content.includes('adds integers')) {
      await writeFile(log, content.replaceAll('adds integers', 'a substituted test'));
      altered++;
    }
  }
  assert.equal(altered, 1, 'Expected one retained raw TAP log');
  bad(invoke('check', '--project', root, '--receipt', file));
});

test('deleting a required snapshot input invalidates a receipt', async t => {
  const root = await fixture(t);
  const { file } = await accepted(root);
  await rm(path.join(path.dirname(file), 'workspace/test/example.test.mjs'));
  bad(invoke('check', '--project', root, '--receipt', file));
});

test('a receipt cannot omit its executed steps', async t => {
  const root = await fixture(t);
  const { file, report } = await accepted(root);
  report.steps = [];
  await writeFile(file, JSON.stringify(report));
  bad(invoke('check', '--project', root, '--receipt', file));
});

test('changing only a failed receipt status to passed cannot manufacture acceptance', async t => {
  const root = await fixture(t, { files: { 'test/example.test.mjs': "import test from 'node:test'; test('failure', () => { throw new Error('real failure'); });" } });
  await rejected(root, invoke('run', '--project', root));
  const result = await receipts(root);
  assert.equal(result.length, 1);
  result[0].report.status = 'passed';
  await writeFile(result[0].file, JSON.stringify(result[0].report));
  bad(invoke('check', '--project', root, '--receipt', result[0].file));
});

test('malformed receipt JSON is rejected', async t => {
  const root = await fixture(t);
  const { file } = await accepted(root);
  await writeFile(file, '{broken');
  bad(invoke('check', '--project', root, '--receipt', file));
});

test('subsequent runs preserve the original receipt and create separate evidence', async t => {
  const root = await fixture(t);
  const { file } = await accepted(root);
  const original = await readFile(file, 'utf8');
  good(invoke('run', '--project', root));
  assert.equal((await receipts(root)).length, 2);
  assert.equal(await readFile(file, 'utf8'), original);
  good(invoke('check', '--project', root, '--receipt', file));
});

test('config paths escaping the project are rejected even if valid JSON exists', async t => {
  const parent = await mkdtemp(path.join(tmpdir(), 'acceptance-config-escape-'));
  t.after(() => rm(parent, { recursive: true, force: true }));
  const root = path.join(parent, 'project');
  await mkdir(root);
  await put(parent, 'outside.json', { schema: 1, name: 'Outside', steps: [tapStep()], exclude: [], dependencyDirs: [] });
  await put(root, 'test/example.test.mjs', passingTest);
  await rejected(root, invoke('run', '--project', root, '--config', '../outside.json'));
});

test('evidence paths escaping the copied workspace are rejected', async t => {
  const root = await fixture(t, { steps: [tapStep({ evidence: ['../outside.txt'] })] });
  await rejected(root, invoke('run', '--project', root));
});

test('undeclared source symlinks are rejected', async t => {
  const root = await fixture(t, { files: { 'real-source.mjs': 'export const original = true;' } });
  await symlink('real-source.mjs', path.join(root, 'linked-source.mjs'));
  await rejected(root, invoke('run', '--project', root));
});

for (const [name, body] of [
  ['failure record', 'TAP version 13\n1..1\nnot ok 1 - failed assertion'],
  ['bailout', 'TAP version 13\n1..1\nBail out! worker crashed'],
  ['zero-test plan', 'TAP version 13\n1..0'],
  ['summary without test records', ''],
]) {
  test(`TAP ${name} cannot be hidden by a passing summary`, async t => {
    const output = `${body}\n# tests 1\n# suites 0\n# pass 1\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n`;
    const root = await fixture(t, {
      steps: [tapStep({ command: ['node', '-e', `console.log(${JSON.stringify(output)})`] })],
    });
    await rejected(root, invoke('run', '--project', root));
  });
}

test('two steps cannot overwrite the same declared evidence file', async t => {
  const root = await fixture(t, {
    steps: [
      checksStep({ id: 'first', command: ['node', 'first.mjs'], evidence: ['artifact.txt'] }),
      checksStep({ id: 'second', command: ['node', 'second.mjs'], evidence: ['artifact.txt'] }),
    ],
    files: {
      'first.mjs': `import {writeFileSync} from 'node:fs'; writeFileSync('artifact.txt', 'first output'); console.log(${JSON.stringify(JSON.stringify(passedChecks))});`,
      'second.mjs': `import {writeFileSync} from 'node:fs'; writeFileSync('artifact.txt', 'second output'); console.log(${JSON.stringify(JSON.stringify(passedChecks))});`,
    },
  });
  await rejected(root, invoke('run', '--project', root));
});

test('a root file named __proto__ is copied, fingerprinted and checked for later changes', async t => {
  const contents = 'this is a source input';
  const root = await fixture(t, { files: { ['__proto__']: contents } });
  const { file, report } = await accepted(root);
  assert.equal(Object.hasOwn(report.inputs, '__proto__'), true);
  assert.equal(await readFile(path.join(path.dirname(file), 'workspace/__proto__'), 'utf8'), contents);
  good(invoke('check', '--project', root, '--receipt', file));
  await put(root, '__proto__', 'modified source input');
  bad(invoke('check', '--project', root, '--receipt', file));
});

test('a dependency directory named __proto__ retains metadata and detects changes', async t => {
  const root = await fixture(t, {
    config: { dependencyDirs: ['__proto__'] },
    files: { '__proto__/package.json': { name: 'temporary-dependency', version: '1.0.0' } },
  });
  const { file, report } = await accepted(root);
  assert.equal(Object.hasOwn(report.environment.dependencies, '__proto__'), true);
  good(invoke('check', '--project', root, '--receipt', file));
  await put(root, '__proto__/package.json', { name: 'temporary-dependency', version: '2.0.0' });
  bad(invoke('check', '--project', root, '--receipt', file));
});

test('actual Node describe suites and nested suites remain valid TAP', async t => {
  const root = await fixture(t, { files: { 'test/example.test.mjs': `
    import { describe, it } from 'node:test';
    import assert from 'node:assert/strict';
    describe('outer suite', () => {
      it('adds integers', () => assert.equal(2 + 2, 4));
      describe('nested suite', () => {
        it('multiplies integers', () => assert.equal(3 * 4, 12));
      });
    });
  ` } });
  const { file } = await accepted(root);
  good(invoke('check', '--project', root, '--receipt', file));
});

test('actual Node nested test subtests remain valid TAP', async t => {
  const root = await fixture(t, { files: { 'test/example.test.mjs': `
    import test from 'node:test';
    import assert from 'node:assert/strict';
    test('parent test', async t => {
      await t.test('first child', () => assert.equal(2 + 2, 4));
      await t.test('second child', () => assert.equal(3 * 4, 12));
    });
  ` } });
  const { file } = await accepted(root);
  good(invoke('check', '--project', root, '--receipt', file));
});
