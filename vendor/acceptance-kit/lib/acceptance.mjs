import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const readJSON = async file => JSON.parse(await fs.readFile(file, 'utf8'));
const writeJSON = (file, value) => fs.writeFile(file, JSON.stringify(value, null, 2) + '\n');
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const differences = (a, b) => [...new Set([...Object.keys(a), ...Object.keys(b)])].filter(p => a[p] !== b[p]);
const within = (base, file) => file.startsWith(base + path.sep);
const matches = (file, prefixes) => prefixes.some(p => file === p || file.startsWith(p + '/'));
const toolRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ignored = ['.acceptance', '.git'];

function relative(value) {
  if (typeof value !== 'string' || !value || value.includes('\\') || value.includes('\0') || path.isAbsolute(value) || /^[a-z]:/i.test(value) || value.split('/').some(p => !p || p === '.' || p === '..')) throw new Error(`Unsafe relative path: ${value}`);
  return value;
}

function keys(value, allowed) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).some(k => !allowed.includes(k))) throw new Error('Invalid object or unknown configuration field');
}

export function validateConfig(config, configFile) {
  relative(configFile);
  keys(config, ['schema', 'name', 'exclude', 'dependencyDirs', 'steps']);
  if (config.schema !== 1 || typeof config.name !== 'string' || !config.name.trim()) throw new Error('Config requires schema: 1 and a name');
  for (const field of ['exclude', 'dependencyDirs']) {
    if (config[field] !== undefined && !Array.isArray(config[field])) throw new Error(`${field} must be an array`);
    for (const p of config[field] ?? []) relative(p);
  }
  if (!Array.isArray(config.steps) || !config.steps.length) throw new Error('At least one acceptance step required');
  const ids = new Set(), evidencePaths = new Set();
  for (const step of config.steps) {
    keys(step, ['id', 'command', 'format', 'evidence', 'timeoutMs']);
    if (typeof step.id !== 'string' || !/^[a-z0-9][a-z0-9-]{0,63}$/.test(step.id) || ids.has(step.id)) throw new Error('Step IDs must be unique lowercase names');
    ids.add(step.id);
    if (!Array.isArray(step.command) || !step.command.length || step.command.some(s => typeof s !== 'string' || s.includes('\0')) || !step.command[0]) throw new Error(`Invalid command: ${step.id}`);
    if (!['tap', 'checks', 'exit'].includes(step.format)) throw new Error(`Invalid result format: ${step.id}`);
    if (step.timeoutMs !== undefined && (!Number.isSafeInteger(step.timeoutMs) || step.timeoutMs < 1 || step.timeoutMs > 600000)) throw new Error('timeoutMs must be 1..600000');
    if (step.evidence !== undefined && !Array.isArray(step.evidence)) throw new Error('evidence must be an array of file paths');
    for (const p of step.evidence ?? []) {
      relative(p);
      if (matches(p, [...ignored, ...(config.dependencyDirs ?? [])])) throw new Error('Evidence must not be in runtime/dependency directories');
      if (evidencePaths.has(p)) throw new Error(`Evidence paths must be unique across steps: ${p}`);
      evidencePaths.add(p);
    }
  }
  if (!config.steps.some(s => s.format !== 'exit')) throw new Error('An exit code alone is not acceptance: add a tap or checks step');
  if (matches(configFile, exclusions(config))) throw new Error('The configuration must remain a source input');
  return config;
}

const exclusions = config => [...ignored, ...(config.exclude ?? []), ...(config.dependencyDirs ?? []), ...config.steps.flatMap(s => s.evidence ?? [])];

async function manifest(root, config) {
  const files = Object.create(null);
  async function visit(directory, prefix = '') {
    for (const entry of (await fs.readdir(directory, { withFileTypes: true })).sort((a, b) => a.name.localeCompare(b.name))) {
      const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
      if (entry.name === '.DS_Store' || matches(rel, exclusions(config))) continue;
      if (entry.isSymbolicLink()) throw new Error(`Unmanaged symlink: ${rel}`);
      if (entry.isDirectory()) await visit(path.join(directory, entry.name), rel);
      else if (entry.isFile()) {
        const file = path.join(directory, entry.name), stat = await fs.lstat(file);
        if (!stat.isFile() || stat.nlink !== 1) throw new Error(`Source inputs must be regular files with a single link: ${rel}`);
        files[rel] = sha(await fs.readFile(file));
      }
      else throw new Error(`Unsupported input: ${rel}`);
    }
  }
  await visit(root);
  return files;
}

async function toolHash() {
  const files = ['package.json', 'bin/acceptance.mjs', 'lib/acceptance.mjs'];
  return sha(Buffer.concat(await Promise.all(files.map(file => fs.readFile(path.join(toolRoot, file))))));
}

async function environment(root, config) {
  const dependencies = Object.create(null);
  for (const dir of config.dependencyDirs ?? []) {
    const target = path.join(root, dir);
    if (!(await fs.stat(target)).isDirectory()) throw new Error(`Dependency directory missing: ${dir}`);
    const metadata = Object.create(null);
    for (const file of ['.package-lock.json', 'package.json', 'pyvenv.cfg']) {
      try { metadata[file] = sha(await fs.readFile(path.join(target, file))); }
      catch (error) { if (error.code !== 'ENOENT') throw error; }
    }
    dependencies[dir] = metadata;
  }
  return { node: process.version, platform: process.platform, arch: process.arch, dependencies };
}

function proof(format, stdout) {
  if (format === 'exit') return null;
  if (format === 'checks') {
    const result = JSON.parse(stdout);
    if (result.status !== 'passed' || !Array.isArray(result.checks) || !result.checks.length) throw new Error('Missing passing checks');
    if (result.errors !== undefined && (!Array.isArray(result.errors) || result.errors.length)) throw new Error('Check output includes runtime errors');
    const names = new Set();
    for (const check of result.checks) {
      if (check.status !== 'passed' || typeof check.name !== 'string' || !check.name.trim() || names.has(check.name)) throw new Error('Incomplete or duplicate named checks');
      names.add(check.name);
    }
    return { checks: result.checks.length, names: [...names] };
  }
  const counts = {};
  for (const key of ['tests', 'suites', 'pass', 'fail', 'cancelled', 'skipped', 'todo']) {
    const values = [...stdout.matchAll(new RegExp(`^# ${key} (\\d+)\\s*$`, 'gm'))];
    if (values.length !== 1) throw new Error(`Missing or ambiguous TAP summary: ${key}`);
    counts[key] = Number(values[0][1]);
    if (!Number.isSafeInteger(counts[key])) throw new Error(`Invalid TAP count: ${key}`);
  }
  if (!counts.tests || counts.tests !== counts.pass || counts.fail || counts.cancelled || counts.skipped || counts.todo) throw new Error('TAP tests failed, empty, skipped, todo or cancelled');
  // Node's nested TAP uses separate numbered plans per indentation level.
  // Ignore YAML diagnostics so message text cannot become a test record.
  const groups = new Map();
  let diagnosticIndent = null, headers = 0, rootPlans = 0, points = 0;
  for (const line of stdout.split(/\r?\n/)) {
    if (diagnosticIndent !== null) {
      if (line === `${diagnosticIndent}...`) diagnosticIndent = null;
      continue;
    }
    const diagnostic = /^( +)---$/.exec(line);
    if (diagnostic) { diagnosticIndent = diagnostic[1]; continue; }
    if (line === 'TAP version 13') { headers++; continue; }
    if (/^\s*(?:not ok\b|Bail out!)/i.test(line)) throw new Error('TAP includes a failed test or bailout');
    const point = /^( *)ok (\d+)(?:\s.*)?$/.exec(line);
    const plan = /^( *)1\.\.(\d+)\s*$/.exec(line);
    if (!point && !plan) continue;
    const [, indent, number] = point ?? plan;
    const depth = indent.length, count = groups.get(depth) ?? 0;
    if (rootPlans || headers !== 1 || depth % 4 || [...groups.keys()].some(level => level > depth)) throw new Error('Inconsistent TAP structure');
    if (point) {
      if (Number(number) !== count + 1 || /(?<!\\)#\s*(?:SKIP|TODO)\b/i.test(line)) throw new Error('Invalid, skipped or todo TAP record');
      groups.set(depth, count + 1); points++;
    } else {
      if (Number(number) !== count) throw new Error('TAP plan disagrees with test records');
      groups.delete(depth);
      if (depth === 0) rootPlans++;
    }
  }
  if (diagnosticIndent !== null || headers !== 1 || rootPlans !== 1 || groups.size || points !== counts.tests + counts.suites) throw new Error('TAP records, plans and summary disagree');
  return counts;
}

async function safeHash(base, relativePath) {
  relative(relativePath);
  const file = path.join(base, relativePath);
  const stat = await fs.lstat(file);
  if (!within(await fs.realpath(base), await fs.realpath(file)) || !stat.isFile() || stat.nlink !== 1) throw new Error(`Evidence must be a regular file with a single link within the run: ${relativePath}`);
  return sha(await fs.readFile(file));
}

export async function check(project, receipt) {
  try {
    project = await fs.realpath(project); receipt = await fs.realpath(receipt);
    const report = await readJSON(receipt), issues = [], out = path.dirname(receipt), workspace = path.join(out, 'workspace');
    if (report.schema !== 1 || report.status !== 'passed') issues.push('Receipt is not a completed passing run');
    const configFile = relative(report.configFile);
    const config = validateConfig(await readJSON(path.join(workspace, configFile)), configFile);
    if (!same(config, report.config)) issues.push('Frozen acceptance configuration changed');
    if (report.toolHash !== await toolHash()) issues.push('Verification tool changed');
    if (!same(report.environment, await environment(project, config))) issues.push('Runtime/dependency metadata changed');
    if (!report.inputs || !Object.keys(report.inputs).length) issues.push('Missing source manifest');
    if (differences(report.inputs ?? {}, await manifest(project, config)).length) issues.push('Source inputs changed: stale receipt');
    if (differences(report.inputs ?? {}, await manifest(workspace, config)).length) issues.push('Frozen workspace inputs changed');
    if (!same(report.steps?.map(s => s.id), config.steps.map(s => s.id))) issues.push('Required steps missing or reordered');
    const required = [];
    for (const step of config.steps) {
      const actual = report.steps?.find(s => s.id === step.id);
      if (!actual || actual.status !== 'passed' || actual.exitCode !== 0 || actual.signal || !same(actual.command, step.command)) issues.push(`Step did not complete as required: ${step.id}`);
      const stdout = `logs/${step.id}.stdout.txt`, stderr = `logs/${step.id}.stderr.txt`;
      required.push(stdout, stderr, ...(step.evidence ?? []).map(file => `workspace/${file}`));
      try {
        const parsed = proof(step.format, await fs.readFile(path.join(out, stdout), 'utf8'));
        if (!same(actual?.proof, parsed)) issues.push(`Step proof disagrees with log: ${step.id}`);
      } catch (error) { issues.push(`${step.id}: ${error.message}`); }
    }
    for (const file of required) if (!report.evidence?.[file]) issues.push(`Unbound required evidence: ${file}`);
    if (!report.evidence || !Object.keys(report.evidence).length) issues.push('Missing evidence manifest');
    for (const [file, hash] of Object.entries(report.evidence ?? {})) {
      try { if (await safeHash(out, file) !== hash) issues.push(`Evidence changed: ${file}`); }
      catch (error) { issues.push(`Evidence missing or unsafe: ${file}: ${error.message}`); }
    }
    return issues;
  } catch (error) { return [`Invalid or unreadable receipt: ${error.message}`]; }
}

export async function run(project, configFile) {
  project = await fs.realpath(project);
  const config = validateConfig(await readJSON(path.join(project, relative(configFile))), configFile);
  const parent = path.join(project, '.acceptance');
  await fs.mkdir(parent, { recursive: true });
  if (await fs.realpath(parent) !== parent) throw new Error('.acceptance must not be a symlink');
  const out = path.join(parent, `${new Date().toISOString().replace(/[:.]/g, '-')}-${randomUUID().slice(0, 8)}`);
  await fs.mkdir(out);
  const workspace = path.join(out, 'workspace'), receipt = path.join(out, 'report.json');
  await fs.mkdir(workspace); await fs.mkdir(path.join(out, 'logs'));
  const report = { schema: 1, status: 'incomplete', startedAt: new Date().toISOString(), configFile, config, inputs: {}, steps: [], evidence: {}, limits: [
    'Only the configured checks were verified; passing does not prove all requirements, scientific correctness or learning outcomes.',
    'Directory isolation is not an OS sandbox. Commands have current user permissions and share configured dependency directories.',
    'Unsigned receipts cannot resist malicious modification by the same user. Dependency fingerprints cover metadata, not all installed bytes or external runtimes.'
  ] };
  try {
    report.toolHash = await toolHash(); report.environment = await environment(project, config);
    report.inputs = await manifest(project, config);
    for (const file of Object.keys(report.inputs)) {
      const target = path.join(workspace, file);
      await fs.mkdir(path.dirname(target), { recursive: true });
      await fs.copyFile(path.join(project, file), target);
    }
    if (differences(report.inputs, await manifest(workspace, config)).length) throw new Error('Source changed while copying');
    for (const dir of config.dependencyDirs ?? []) {
      const target = path.join(workspace, dir);
      await fs.mkdir(path.dirname(target), { recursive: true });
      await fs.symlink(await fs.realpath(path.join(project, dir)), target, process.platform === 'win32' ? 'junction' : 'dir');
    }
    const env = { ...process.env, NO_COLOR: '1' }; delete env.NODE_TEST_CONTEXT;
    for (const step of config.steps) {
      console.log(`Running ${step.id}`);
      const start = Date.now();
      const [program, ...args] = step.command;
      const execution = spawnSync(program === 'node' ? process.execPath : program, args, { cwd: workspace, encoding: 'utf8', shell: false, killSignal: 'SIGKILL', timeout: step.timeoutMs ?? 180000, maxBuffer: 32 * 1024 * 1024, env });
      const actual = { id: step.id, command: step.command, exitCode: execution.status, signal: execution.signal, seconds: (Date.now() - start) / 1000, status: execution.error ? 'incomplete' : execution.status === 0 ? 'passed' : 'failed', proof: null };
      report.steps.push(actual);
      if (execution.error) actual.error = execution.error.message;
      for (const [stream, data] of [['stdout', execution.stdout], ['stderr', execution.stderr]]) {
        const file = `logs/${step.id}.${stream}.txt`; await fs.writeFile(path.join(out, file), data ?? ''); report.evidence[file] = await safeHash(out, file);
      }
      if (actual.status === 'passed') {
        try {
          actual.proof = proof(step.format, execution.stdout);
          for (const file of step.evidence ?? []) report.evidence[`workspace/${file}`] = await safeHash(workspace, file);
        } catch (error) { actual.status = 'incomplete'; actual.error = error.message; }
      }
      await writeJSON(receipt, report);
      if (actual.status !== 'passed') { report.status = actual.status; throw new Error(`${step.id}: ${actual.error ?? 'command failed; inspect logs'}`); }
    }
    if (differences(report.inputs, await manifest(workspace, config)).length) throw new Error('Checks changed frozen source or acceptance inputs');
    if (differences(report.inputs, await manifest(project, config)).length) throw new Error('Project changed during verification; results are stale');
    if (!same(report.environment, await environment(project, config)) || report.toolHash !== await toolHash()) throw new Error('Verification environment changed during the run');
    report.status = 'passed';
  } catch (error) { report.error = error.message; }
  report.finishedAt = new Date().toISOString(); await writeJSON(receipt, report);
  if (report.status === 'passed') {
    const issues = await check(project, receipt);
    if (issues.length) { report.status = 'incomplete'; report.error = issues.join('; '); await writeJSON(receipt, report); }
  }
  const title = { passed: '配置中的验收检查通过', failed: '检查失败', incomplete: '验收未完成' }[report.status];
  await fs.writeFile(path.join(out, 'REPORT.md'), [`# ${title}`, '', `项目：${config.name}`, `完成时间：${report.finishedAt}`, `输入指纹：${sha(JSON.stringify(report.inputs))}`, '', ...report.steps.map(s => `- ${s.id}: ${s.status} (${s.seconds}s)${s.proof ? ' ' + JSON.stringify(s.proof) : ''}`), '', report.error ?? '', '', '原始日志位于 logs/；声明的产物位于 workspace/；命令与文件指纹见 report.json。', '', '只说明本次配置中的检查通过，不证明全部需求或测试本身正确。目录隔离不是安全沙箱，报告未签名。分享前检查副本、日志和产物是否包含私密数据。', '', '使用 check --project 项目路径 --receipt 本目录/report.json 复核旧结果。', ''].join('\n'));
  return { status: report.status, receipt };
}
