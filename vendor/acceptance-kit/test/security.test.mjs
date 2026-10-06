import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, link, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const cli = fileURLToPath(new URL('../bin/acceptance.mjs', import.meta.url));
const checks = JSON.stringify({ status: 'passed', checks: [{ name: 'synthetic requirement', status: 'passed' }] });

async function fixture(t, script, { evidence = [], exclude = [], timeoutMs = 3000 } = {}) {
  const parent = await mkdtemp(path.join(tmpdir(), 'buddy-acceptance-security-'));
  t.after(() => rm(parent, { recursive: true, force: true }));
  const project = path.join(parent, 'project');
  await mkdir(project);
  await writeFile(path.join(project, 'check.mjs'), script);
  await writeFile(path.join(project, 'acceptance.config.json'), JSON.stringify({
    schema: 1, name: 'Synthetic security fixture', exclude, steps: [
      { id: 'behavior', command: ['node', 'check.mjs'], format: 'checks', evidence, timeoutMs },
    ],
  }));
  return { parent, project };
}

function invoke(project) {
  return spawnSync(process.execPath, [cli, 'run', '--project', project], {
    encoding: 'utf8', timeout: 5000, killSignal: 'SIGKILL',
  });
}

async function receipt(project) {
  const [directory] = await readdir(path.join(project, '.acceptance'));
  assert.ok(directory, 'An incomplete run must retain its receipt');
  const out = path.join(project, '.acceptance', directory);
  return { out, report: JSON.parse(await readFile(path.join(out, 'report.json'), 'utf8')) };
}

test('a hardlink to preexisting external evidence cannot pass', async t => {
  const { parent, project } = await fixture(t, '', { evidence: ['artifact.txt'] });
  const external = path.join(parent, 'preexisting.txt');
  await writeFile(external, 'SYNTHETIC PREEXISTING EVIDENCE');
  await writeFile(path.join(project, 'check.mjs'), `import { linkSync } from 'node:fs'; linkSync(${JSON.stringify(external)}, 'artifact.txt'); console.log(${JSON.stringify(checks)});`);
  const result = invoke(project);
  assert.ifError(result.error);
  assert.equal(result.status, 1);
  const { report } = await receipt(project);
  assert.equal(report.status, 'incomplete');
  assert.match(report.error, /regular file with a single link/);
  assert.equal(await readFile(external, 'utf8'), 'SYNTHETIC PREEXISTING EVIDENCE');
});

test('hardlinked external inputs are not collected in the frozen workspace', async t => {
  const { parent, project } = await fixture(t, `console.log(${JSON.stringify(checks)});`);
  const external = path.join(parent, 'source.txt');
  await writeFile(external, 'SYNTHETIC EXTERNAL INPUT');
  await link(external, path.join(project, 'linked-source.txt'));
  const result = invoke(project);
  assert.ifError(result.error);
  assert.equal(result.status, 1);
  const { out, report } = await receipt(project);
  assert.equal(report.status, 'incomplete');
  assert.match(report.error, /Source inputs must be regular files with a single link/);
  assert.deepEqual(report.steps, []);
  await assert.rejects(readFile(path.join(out, 'workspace/linked-source.txt')), { code: 'ENOENT' });
  assert.equal(await readFile(external, 'utf8'), 'SYNTHETIC EXTERNAL INPUT');
});

test('timeout terminates a direct child that ignores SIGTERM', async t => {
  const script = `import { writeFileSync } from 'node:fs'; process.on('SIGTERM', () => {}); writeFileSync('worker.pid', String(process.pid)); setInterval(() => {}, 100);`;
  const { project } = await fixture(t, script, { exclude: ['worker.pid'], timeoutMs: 800 });
  let workerPid;
  t.after(() => {
    if (workerPid) {
      try { process.kill(workerPid, 'SIGKILL'); }
      catch (error) { if (error.code !== 'ESRCH') throw error; }
    }
  });
  const start = Date.now();
  const result = invoke(project);
  const elapsed = Date.now() - start;
  const [directory] = await readdir(path.join(project, '.acceptance'));
  workerPid = Number(await readFile(path.join(project, '.acceptance', directory, 'workspace/worker.pid'), 'utf8'));
  assert.ok(Number.isInteger(workerPid) && workerPid > 0, 'The signal handler must have been installed before timeout');
  assert.ifError(result.error);
  assert.equal(result.status, 1);
  assert.ok(elapsed < 4500, `Timeout exceeded the direct-child bound: ${elapsed} ms`);
  const { report } = await receipt(project);
  assert.equal(report.status, 'incomplete');
  assert.equal(report.steps[0].signal, 'SIGKILL');
});
