const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const path = require('node:path');
const { chromium } = require('playwright');

const root = path.resolve(__dirname, '../..');
const html = execFileSync(path.join(root, '.venv', 'Scripts', 'python.exe'), [
  '-c', "from runrelay.web import _monitor_page_v2; import sys; sys.stdout.buffer.write(_monitor_page_v2())",
], { cwd: root }).toString('utf8');
let browser;
before(async () => { browser = await chromium.launch({ channel: process.env.TEST_BROWSER || 'chrome', headless: true }); });
after(async () => { await browser?.close(); });

test('whole process card drags into a named group; group picker and rename work', async t => {
  const context = await browser.newContext();
  t.after(() => context.close());
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  t.after(() => assert.deepEqual(errors, []));
  const server = { id: 'srv1', name: 'Test server', host: 'test.example', port: 22 };
  const monitors = [1, 2].map(n => ({ id: `m${n}`, server_id: 'srv1', pid: 100 + n, status: 'RUNNING', started_at: new Date().toISOString(), name: `Process ${n}`, group_id: null }));
  const groups = [];
  await page.route('http://dreamkeeper.test/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    const pathName = url.pathname;
    if (pathName === '/') return route.fulfill({ contentType: 'text/html', body: html });
    let data = {};
    if (request.method() === 'GET') {
      if (pathName === '/api/servers') data = [server];
      else if (pathName === '/api/monitors') data = monitors;
      else if (pathName === '/api/watch-groups') data = groups;
      else if (pathName.endsWith('/snapshot')) data = { gpus: [], gpu_processes: [], processes: [] };
    } else if (pathName === '/api/watch-groups') {
      data = { id: 'g1', name: '新的组合守梦', status: 'DRAFT' };
      groups.push(data);
    } else if (pathName === '/api/watch-groups/g1/rename') {
      data = groups[0];
      data.name = request.postDataJSON().name;
    } else if (pathName === '/api/watch-groups/g1/monitors') {
      data = monitors.find(m => m.id === request.postDataJSON().monitor_id);
      data.group_id = 'g1';
    } else if (pathName === '/api/watch-groups/g1/start') {
      data = groups[0];
      data.status = 'RUNNING';
    } else if (pathName === '/api/watch-groups/g1/cancel') {
      data = groups[0];
      data.status = 'CANCELLED';
      monitors.forEach(m => { if (m.group_id === 'g1') m.status = 'CANCELLED'; });
    } else if (pathName === '/api/monitors/m1/rename') {
      data = monitors[0];
      data.name = request.postDataJSON().name;
    }
    return route.fulfill({ json: data });
  });
  await page.goto('http://dreamkeeper.test/');
  await page.locator('.watch-pool .watch-process').first().waitFor();
  await page.locator('#add-watch-group').click();
  await page.locator('.watch-group .watch-rename-input').fill('双 GPU 训练');
  await page.locator('.watch-group .watch-rename-input').press('Enter');
  await page.locator('.watch-group-name').filter({ hasText: '双 GPU 训练' }).waitFor();
  await page.locator('.watch-pool .watch-process').first().dragTo(page.locator('.watch-group .watch-drop-hint'));
  await page.locator('.watch-group [data-monitor-card="m1"]').waitFor();
  await page.locator('.watch-group [data-add-to-group="g1"]').selectOption('m2');
  await page.locator('.watch-group [data-monitor-card="m2"]').waitFor();
  await page.locator('[data-find-process]').waitFor();
  await page.locator('.watch-group [data-edit-monitor="m1"]').click();
  await page.locator('.watch-group .watch-rename-input').fill('GPU 0');
  await page.locator('.watch-group .watch-rename-input').press('Enter');
  await page.locator('.watch-group .watch-process-name').filter({ hasText: 'GPU 0' }).waitFor();
  assert.equal(await page.locator('.nav a:visible').count(), 0);
  assert.equal(await page.locator('.liquid-dock .dock-item svg').count(), 4);
  await page.evaluate(() => show('monitor-msg', 'Saved', 'ok'));
  await page.locator('#monitor-msg.toast-in').waitFor();
  await page.waitForTimeout(3600);
  assert.equal(await page.locator('#monitor-msg').textContent(), '');
  await page.locator('[data-start-group="g1"]').click();
  await page.locator('[data-cancel-group="g1"]').click();
  await page.locator('.watch-group[data-group-status="CANCELLED"]').waitFor();
  assert.equal(await page.locator('[data-cancel-group="g1"]').count(), 0);
  assert.equal(monitors.filter(m => m.status === 'CANCELLED').length, 2);
});

test('connector routing selection stays readable and header keeps only language switch', async t => {
  const context = await browser.newContext();
  t.after(() => context.close());
  const page = await context.newPage();
  const serverHtml = execFileSync(path.join(root, '.venv', 'Scripts', 'python.exe'), [
    '-c', "from runrelay.web import _server_page; import sys; sys.stdout.buffer.write(_server_page())",
  ], { cwd: root }).toString('utf8');
  await page.route('http://dreamkeeper.test/**', route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/servers') return route.fulfill({ contentType: 'text/html', body: serverHtml });
    return route.fulfill({ json: url.pathname === '/api/servers' ? [] : {} });
  });
  await page.goto('http://dreamkeeper.test/servers');
  await page.locator('[data-dock="connectors"]').click();
  await page.locator('.connector-chip.active').waitFor();
  assert.equal(await page.locator('header .nav a:visible').count(), 0);
  assert.equal(await page.locator('#lang-toggle:visible').count(), 1);
  assert.equal(await page.locator('.liquid-dock .dock-item svg').count(), 3);
  const style = await page.locator('.connector-chip.active').evaluate(node => {
    const css = getComputedStyle(node);
    return { color: css.color, background: css.backgroundColor };
  });
  assert.equal(style.color, 'rgb(245, 251, 255)');
  assert.equal(style.background, 'rgb(55, 111, 142)');
});
