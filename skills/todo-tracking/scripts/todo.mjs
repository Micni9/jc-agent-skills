#!/usr/bin/env node
// todo.mjs — TODO.md 的簡易 CRUD 工具（Node.js 18+，無外部依賴）
// 與 scripts/todo.ps1 共用同一份 TODO.md 格式，可交錯編輯同一檔案。
import fs from 'node:fs';
import path from 'node:path';

const FieldOrder = ['位置', '說明', '影響', '建議', '發現', '完成'];
const HeaderRegex = /^- \[( |x|X)\] (TODO-\d+) \[([A-Za-z0-9]+)\] (.*)$/i;
const DetailRegex = /^\s+-\s*(位置|說明|影響|建議|發現|完成)\s*[:：]\s*(.*)$/;
const MarkerNames = ['.git', 'package.json', 'pyproject.toml', 'setup.py', 'go.mod',
  'Cargo.toml', 'pom.xml', 'build.gradle', 'composer.json', 'Gemfile'];
const MarkerSuffixes = ['.sln', '.csproj'];
const ValidCommands = ['init', 'add', 'list', 'show', 'update', 'done', 'reopen',
  'remove', 'path', 'help'];
const ValidPriorities = ['P0', 'P1', 'P2', 'P3'];
const ValidStatuses = ['open', 'done', 'all'];

const Template = [
  '# TODO',
  '',
  '> 未處理問題清單。翻閱程式碼發現問題時記錄於此，與當前任務無關者不修正。',
  '> 請使用 `scripts/todo.ps1` 增刪改；沒有 PowerShell 時，直接依下列格式手動編輯。',
  '>',
  '> 格式：',
  '> 標題行   - [ ] TODO-<NNNN> [P<n>] 一句話描述問題',
  '> 說明行     - 位置: 相對路徑:行號',
  '>            - 說明: 現象與原因',
  '>            - 影響: 不修的後果（選填）',
  '>            - 建議: 建議做法（選填）',
  '>            - 發現: yyyy-MM-dd',
  '>            - 完成: yyyy-MM-dd（標記完成時填）',
  '>',
  '> 完成時把 [ ] 改成 [x]。項目依 ID 排序，項目之間空一行。',
  '',
];

// ---------- CLI parsing ----------
const rawArgs = process.argv.slice(2);
const flags = {};
const provided = new Set();
const positionals = [];
let i = 0;
while (i < rawArgs.length) {
  const a = rawArgs[i];
  if (a.startsWith('--')) {
    const eq = a.indexOf('=');
    if (eq !== -1) {
      const name = a.slice(2, eq);
      flags[name] = a.slice(eq + 1);
      provided.add(name);
      i++;
    } else {
      const name = a.slice(2);
      if (name === 'json') {
        flags.json = true;
        provided.add('json');
        i++;
      } else if (i + 1 < rawArgs.length && !rawArgs[i + 1].startsWith('--')) {
        flags[name] = rawArgs[i + 1];
        provided.add(name);
        i += 2;
      } else {
        flags[name] = '';
        provided.add(name);
        i++;
      }
    }
  } else {
    positionals.push(a);
    i++;
  }
}
const command = positionals[0] || 'help';
const targetId = positionals[1];

// Validate command/priority/status before dispatch (mirrors PS bind-time validation).
if (!ValidCommands.includes(command)) {
  fail(`未知指令: ${command}。使用 help 查看可用指令。`);
}
if (provided.has('priority') && !ValidPriorities.includes(flags.priority)) {
  fail(`Priority 必須為 P0/P1/P2/P3，收到: ${flags.priority}`);
}
if (provided.has('status') && !ValidStatuses.includes(flags.status)) {
  fail(`Status 必須為 open/done/all，收到: ${flags.status}`);
}

function fail(msg) {
  process.stderr.write(`錯誤: ${msg}\n`);
  process.exit(1);
}

function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

// ---------- path resolution ----------
function isMarkerDir(dir) {
  for (const name of MarkerNames) {
    try {
      if (fs.existsSync(path.join(dir, name))) return true;
    } catch {}
  }
  let entries;
  try {
    entries = fs.readdirSync(dir);
  } catch {
    return false;
  }
  for (const entry of entries) {
    const lower = entry.toLowerCase();
    if (MarkerSuffixes.some((s) => lower.endsWith(s))) return true;
  }
  return false;
}

function resolveTodoPath(override) {
  const ov = (override === undefined || override === null) ? '' : String(override);
  if (ov.trim() !== '') {
    return path.resolve(ov.trim());
  }
  const envFile = process.env.TODO_FILE;
  if (envFile && envFile.trim() !== '') {
    return path.resolve(envFile.trim());
  }
  const envRoot = process.env.TODO_ROOT;
  if (envRoot && envRoot.trim() !== '') {
    return path.resolve(envRoot.trim(), 'TODO.md');
  }
  let probe = process.cwd();
  while (true) {
    try {
      if (isMarkerDir(probe)) return path.join(probe, 'TODO.md');
    } catch {}
    const parent = path.dirname(probe);
    if (parent === probe) break;
    probe = parent;
  }
  return path.join(process.cwd(), 'TODO.md');
}

// ---------- read/write ----------
function splitLines(text) {
  if (text === '') return [];
  const lines = text.split(/\r?\n/);
  if (lines.length > 0 && lines[lines.length - 1] === '' && text.endsWith('\n')) {
    lines.pop();
  }
  return lines;
}

function parseTodo(text) {
  const lines = splitLines(text);
  const data = { before: [], items: [], after: [] };
  let current = null;
  let phase = 'before';
  for (const line of lines) {
    const hm = line.match(HeaderRegex);
    if (hm) {
      if (current) data.items.push(current);
      current = {
        id: hm[2],
        done: hm[1] !== ' ',
        priority: hm[3],
        title: hm[4].trim(),
        fields: {},
        extra: [],
      };
      phase = 'items';
      continue;
    }
    if (current) {
      if (line.trim() === '') {
        data.items.push(current);
        current = null;
        continue;
      }
      const dm = line.match(DetailRegex);
      if (dm) {
        current.fields[dm[1]] = dm[2].trim();
        continue;
      }
      current.extra.push(line.trimEnd());
      continue;
    }
    if (phase === 'items' && line.trim() !== '') phase = 'after';
    if (phase === 'after') data.after.push(line.trimEnd());
    else data.before.push(line.trimEnd());
  }
  if (current) data.items.push(current);
  return data;
}

function serializeTodo(data) {
  const out = [];
  const before = [...data.before];
  while (before.length && before[before.length - 1].trim() === '') before.pop();
  for (const l of before) out.push(l);
  if (out.length > 0) out.push('');
  const ordered = [...data.items].sort((a, b) => {
    const na = parseInt((a.id.split('-')[1] || '0'), 10) || 0;
    const nb = parseInt((b.id.split('-')[1] || '0'), 10) || 0;
    return na - nb;
  });
  for (const item of ordered) {
    const mark = item.done ? 'x' : ' ';
    out.push(`- [${mark}] ${item.id} [${item.priority}] ${item.title}`);
    for (const key of FieldOrder) {
      const v = item.fields[key];
      if (v !== undefined && v !== null && String(v).trim() !== '') {
        out.push(`  - ${key}: ${v}`);
      }
    }
    for (const e of item.extra) out.push(e);
  }
  const after = [...data.after];
  while (after.length && after[0].trim() === '') after.shift();
  if (after.length > 0) {
    out.push('');
    for (const l of after) out.push(l);
  }
  if (out.length === 0) return '';
  return out.join('\n') + '\n';
}

function readTodoFile(filePath) {
  if (!fs.existsSync(filePath)) {
    return { before: [], items: [], after: [] };
  }
  let raw = fs.readFileSync(filePath, 'utf8');
  if (raw.length > 0 && raw.charCodeAt(0) === 0xFEFF) raw = raw.slice(1);
  return parseTodo(raw);
}

function writeFileAtomic(filePath, content) {
  const dir = path.dirname(filePath);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  const tmp = path.join(dir, `.todo.${process.pid}.${Date.now()}.tmp`);
  fs.writeFileSync(tmp, content, { encoding: 'utf8' });
  try {
    try {
      fs.renameSync(tmp, filePath);
    } catch (e) {
      if (fs.existsSync(filePath)) fs.unlinkSync(filePath);
      fs.renameSync(tmp, filePath);
    }
  } catch (e) {
    try { fs.unlinkSync(tmp); } catch {}
    throw e;
  }
}

function getItem(data, target) {
  if (!target || String(target).trim() === '') {
    fail('需要指定項目 ID，例如 TODO-0001。');
  }
  const normalized = String(target).trim().toUpperCase();
  const found = data.items.find((it) => it.id.toUpperCase() === normalized);
  if (!found) fail(`找不到項目 ${normalized}。使用 list 查看現有 ID。`);
  return found;
}

function formatItem(item) {
  const state = item.done ? 'done' : 'open';
  const mark = item.done ? 'x' : ' ';
  const lines = [`- [${mark}] ${item.id} [${item.priority}] ${item.title}`];
  for (const key of FieldOrder) {
    const v = item.fields[key];
    if (v !== undefined && v !== null && String(v).trim() !== '') {
      lines.push(`  - ${key}: ${v}`);
    }
  }
  for (const e of item.extra) lines.push(e);
  lines.push(`  (狀態: ${state})`);
  return lines.join('\n');
}

// ---------- commands ----------
const filePath = resolveTodoPath(flags['todo-file']);

function cmdPath() {
  process.stdout.write(filePath + '\n');
}

function cmdHelp() {
  const text = `TODO.md 的簡易 CRUD 工具（Node.js 18+）。

用法:
  node todo.mjs <command> [id] [options]

指令:
  path                       印出 TODO.md 的絕對路徑
  init                       建立 TODO.md（已存在則不覆蓋）
  add                        新增項目，自動配發 ID
  list                       列出項目（預設只列未完成）
  show <id>                  顯示單一項目全文
  update <id>                修改欄位
  done <id>                  標記完成並寫入完成日期
  reopen <id>                取消完成
  remove <id>                刪除項目
  help                       顯示本說明

add 選項:
  --title <text>             一句話描述問題（必填）
  --priority P0|P1|P2|P3     預設 P1
  --location <path:line>     位置
  --note <text>              現象與原因
  --impact <text>            不修的後果
  --fix <text>               建議做法

list 選項:
  --status open|done|all     預設 open
  --priority P0|P1|P2|P3
  --json                     輸出 JSON 陣列

update 選項:
  --title <text>             空字串會被拒絕
  --priority P0|P1|P2|P3
  --location <path:line>     空字串會清除該欄位
  --note <text>              空字串會清除該欄位
  --impact <text>            空字串會清除該欄位
  --fix <text>               空字串會清除該欄位

通用選項:
  --todo-file <path>         直接指定 TODO.md，覆寫自動偵測

環境變數:
  TODO_FILE                  直接指定 TODO.md
  TODO_ROOT                  指定專案根目錄，檔案為 <TODO_ROOT>/TODO.md
`;
  process.stdout.write(text);
}

function cmdInit() {
  if (fs.existsSync(filePath)) {
    process.stdout.write(`已存在: ${filePath}\n`);
    return;
  }
  writeFileAtomic(filePath, Template.join('\n') + '\n');
  process.stdout.write(`已建立: ${filePath}\n`);
}

function cmdAdd() {
  const title = provided.has('title') ? flags.title : '';
  if (String(title).trim() === '') fail('add 需要 -Title。');
  const data = readTodoFile(filePath);
  let next = 1;
  if (data.items.length > 0) {
    const max = Math.max(...data.items.map((it) => parseInt((it.id.split('-')[1] || '0'), 10) || 0));
    next = max + 1;
  }
  const newPriority = provided.has('priority') && flags.priority ? flags.priority : 'P1';
  const item = {
    id: `TODO-${String(next).padStart(4, '0')}`,
    done: false,
    priority: newPriority,
    title: String(title).trim(),
    fields: {},
    extra: [],
  };
  if (provided.has('location') && String(flags.location).trim() !== '') item.fields['位置'] = String(flags.location).trim();
  if (provided.has('note') && String(flags.note).trim() !== '') item.fields['說明'] = String(flags.note).trim();
  if (provided.has('impact') && String(flags.impact).trim() !== '') item.fields['影響'] = String(flags.impact).trim();
  if (provided.has('fix') && String(flags.fix).trim() !== '') item.fields['建議'] = String(flags.fix).trim();
  item.fields['發現'] = today();
  data.items.push(item);
  writeFileAtomic(filePath, serializeTodo(data));
  process.stdout.write(`已新增 ${item.id}: ${item.title}\n`);
}

function cmdList() {
  const data = readTodoFile(filePath);
  let items = [...data.items];
  const status = provided.has('status') ? flags.status : 'open';
  if (status !== 'all') {
    const wantDone = (status === 'done');
    items = items.filter((it) => it.done === wantDone);
  }
  if (provided.has('priority')) {
    items = items.filter((it) => it.priority === flags.priority);
  }
  if (items.length === 0) {
    process.stdout.write('沒有符合條件的項目。\n');
    return;
  }
  if (provided.has('json')) {
    const objects = items.map((it) => ({
      id: it.id,
      status: it.done ? 'done' : 'open',
      priority: it.priority,
      title: it.title,
      location: it.fields['位置'] !== undefined ? it.fields['位置'] : null,
      note: it.fields['說明'] !== undefined ? it.fields['說明'] : null,
      impact: it.fields['影響'] !== undefined ? it.fields['影響'] : null,
      fix: it.fields['建議'] !== undefined ? it.fields['建議'] : null,
      found: it.fields['發現'] !== undefined ? it.fields['發現'] : null,
      closed: it.fields['完成'] !== undefined ? it.fields['完成'] : null,
    }));
    process.stdout.write(JSON.stringify(objects) + '\n');
    return;
  }
  for (const it of items) {
    const state = it.done ? 'done' : 'open';
    process.stdout.write(`${it.id}  [${it.priority}]  [${state}]  ${it.title}\n`);
  }
}

function cmdShow() {
  const data = readTodoFile(filePath);
  const item = getItem(data, targetId);
  process.stdout.write(formatItem(item) + '\n');
}

function cmdUpdate() {
  const data = readTodoFile(filePath);
  const item = getItem(data, targetId);
  const changed = [];
  if (provided.has('title')) {
    if (String(flags.title).trim() === '') fail('Title 不可為空。');
    item.title = String(flags.title).trim();
    changed.push('Title');
  }
  if (provided.has('priority')) {
    item.priority = flags.priority;
    changed.push('Priority');
  }
  if (provided.has('location')) {
    item.fields['位置'] = flags.location;
    changed.push('Location');
  }
  if (provided.has('note')) {
    item.fields['說明'] = flags.note;
    changed.push('Note');
  }
  if (provided.has('impact')) {
    item.fields['影響'] = flags.impact;
    changed.push('Impact');
  }
  if (provided.has('fix')) {
    item.fields['建議'] = flags.fix;
    changed.push('Fix');
  }
  if (changed.length === 0) {
    fail('update 需要至少一個欄位: -Title、-Priority、-Location、-Note、-Impact、-Fix。');
  }
  writeFileAtomic(filePath, serializeTodo(data));
  process.stdout.write(`已更新 ${item.id}: ${changed.join(', ')}\n`);
}

function cmdDone() {
  const data = readTodoFile(filePath);
  const item = getItem(data, targetId);
  item.done = true;
  item.fields['完成'] = today();
  writeFileAtomic(filePath, serializeTodo(data));
  process.stdout.write(`已標記完成 ${item.id}\n`);
}

function cmdReopen() {
  const data = readTodoFile(filePath);
  const item = getItem(data, targetId);
  item.done = false;
  delete item.fields['完成'];
  writeFileAtomic(filePath, serializeTodo(data));
  process.stdout.write(`已重新開啟 ${item.id}\n`);
}

function cmdRemove() {
  const data = readTodoFile(filePath);
  const item = getItem(data, targetId);
  data.items = data.items.filter((it) => it !== item);
  writeFileAtomic(filePath, serializeTodo(data));
  process.stdout.write(`已刪除 ${item.id}\n`);
}

// ---------- dispatch ----------
switch (command) {
  case 'path': cmdPath(); break;
  case 'help': cmdHelp(); break;
  case 'init': cmdInit(); break;
  case 'add': cmdAdd(); break;
  case 'list': cmdList(); break;
  case 'show': cmdShow(); break;
  case 'update': cmdUpdate(); break;
  case 'done': cmdDone(); break;
  case 'reopen': cmdReopen(); break;
  case 'remove': cmdRemove(); break;
}
