#!/usr/bin/env node
import path from 'node:path';
import { run, check } from '../lib/acceptance.mjs';

const help = `Acceptance Kit 0.1.2 — 本地项目验收

node bin/acceptance.mjs run --project PATH [--config acceptance.config.json]
node bin/acceptance.mjs check --project PATH --receipt PATH

需要 Node.js 22+。命令在项目副本中执行；这不是操作系统安全沙箱。
每轮执行全部配置检查；结果写入项目 .acceptance/。未通过或过期返回非零。
示例：node bin/acceptance.mjs run --project /项目路径`;

try {
  if (Number(process.versions.node.split('.')[0]) < 22) throw new Error('Node.js 22+ required');
  const args = process.argv.slice(2);
  if (!args.length || (args.length === 1 && ['--help', '-h'].includes(args[0]))) console.log(help);
  else if (args.length === 1 && args[0] === '--version') console.log('0.1.2');
  else {
    const command = args.shift(), options = {};
    while (args.length) {
      const key = args.shift();
      if (!['--project', '--config', '--receipt'].includes(key) || key in options || !args.length || args[0].startsWith('--')) throw new Error('Invalid or duplicate arguments');
      options[key] = args.shift();
    }
    if (!options['--project']) throw new Error('--project is required');
    const project = path.resolve(options['--project']);
    if (command === 'run' && !options['--receipt']) {
      const result = await run(project, options['--config'] ?? 'acceptance.config.json');
      console.log(`${result.status}: ${result.receipt}`);
      process.exitCode = result.status === 'passed' ? 0 : 1;
    } else if (command === 'check' && options['--receipt'] && !options['--config']) {
      const issues = await check(project, path.resolve(options['--receipt']));
      console.log(JSON.stringify({ current: issues.length === 0, issues }, null, 2));
      process.exitCode = issues.length ? 1 : 0;
    } else throw new Error(help);
  }
} catch (error) { console.error(error.message); process.exitCode = 1; }
