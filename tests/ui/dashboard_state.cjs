// Run with node --test tests/ui/dashboard_state.cjs (requires playwright and Edge).
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { existsSync } = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const root = path.resolve(__dirname, '../..');
const venvPython = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const python = process.env.PYTHON || (existsSync(venvPython) ? venvPython : 'python');
const html = execFileSync(python, ['-c', "import sys; sys.path.insert(0, 'src'); from runrelay.web import _monitor_page_v2; sys.stdout.buffer.write(_monitor_page_v2())"], { cwd: root }).toString('utf8');
const servers = ['alpha', 'beta', 'gamma'].map(id => ({ id, name: id, host: `${id}.example.test`, port: 22, username: 'researcher' }));
let browser;
before(async () => { browser = await chromium.launch({ channel: process.env.TEST_BROWSER || 'msedge', headless: true }); });
after(async () => { await browser?.close(); });

async function dashboard(t) {
  const context = await browser.newContext();
  t.after(() => context.close());
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  t.after(() => assert.deepEqual(errors, [], 'no browser script errors'));
  await page.clock.install();
  await page.route('http://dreamkeeper.test/**', async route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
    let data = [];
    if (url.pathname === '/api/servers') data = servers;
    else if (url.pathname === '/api/connectors/feishu') data = {};
    else if (url.pathname.endsWith('/snapshot')) data = {
      hostname: url.pathname.split('/')[3], system: 'Test Linux', gpu_processes: [],
      gpus: [{ index: 0, name: 'Test GPU', memory_used_mib: 128, memory_total_mib: 8192, utilization_percent: 1 }],
    };
    return route.fulfill({ json: data });
  });
  await page.goto('http://dreamkeeper.test/');
  await page.waitForFunction(() => document.querySelectorAll('[data-dream]').length === 3);
  return page;
}

const openCards = page => page.locator('details.dream-overview-card[open] h3').allTextContents();
async function assertNavigation(page, expected) {
  assert.equal(await page.locator('.console-sidebar .console-nav-item.active').count(), 1);
  assert.equal(await page.locator('.console-sidebar [aria-current]').count(), 1);
  assert.equal(await page.locator(expected).getAttribute('aria-current'), 'page');
  assert.equal(await page.locator(expected).evaluate(node => node.classList.contains('active')), true);
}

test('GPU refresh preserves multiple expanded cards, all-closed state and browser reload', async t => {
  const page = await dashboard(t);
  await page.locator('[data-console-view="dreams"]').click();
  await page.waitForFunction(() => document.querySelectorAll('details.dream-overview-card').length === 3);
  await page.locator('details.dream-overview-card').nth(1).locator('summary').click();
  assert.deepEqual(await openCards(page), ['alpha', 'beta']);
  await page.evaluate(() => loadDreamOverview());
  assert.deepEqual(await openCards(page), ['alpha', 'beta']);
  await page.clock.runFor(16000);
  await page.evaluate(() => loadAll());
  assert.deepEqual(await openCards(page), ['alpha', 'beta']);
  await page.reload();
  await page.waitForFunction(() => document.querySelectorAll('details.dream-overview-card').length === 3);
  assert.deepEqual(await openCards(page), ['alpha', 'beta']);
  await page.locator('details.dream-overview-card').nth(0).locator('summary').click();
  await page.locator('details.dream-overview-card').nth(1).locator('summary').click();
  await page.evaluate(() => loadDreamOverview());
  assert.deepEqual(await openCards(page), []);
  await page.reload();
  await page.waitForFunction(() => document.querySelectorAll('details.dream-overview-card').length === 3);
  assert.deepEqual(await openCards(page), []);
});

test('sidebar highlights only the current view after every refresh and language switch', async t => {
  const page = await dashboard(t);
  for (const selector of ['[data-console-view="tasks"]', '[data-console-view="dreams"]', '[data-dream="beta"]', '[data-console-view="connectors"]']) {
    await page.locator(selector).click();
    await page.evaluate(async () => { await loadMonitors(); await loadAll(); });
    await page.clock.runFor(16000);
    await assertNavigation(page, selector);
    await page.evaluate(() => { lang = lang === 'zh' ? 'en' : 'zh'; window.renderPage(); });
    await assertNavigation(page, selector);
  }
  await page.locator('[data-dream="beta"]').click();
  await page.reload();
  await page.waitForFunction(() => document.querySelectorAll('[data-dream]').length === 3);
  await assertNavigation(page, '[data-dream="beta"]');
});

test('GPU refresh retains cards while loading and accepts toggles during an in-flight request', async t => {
  const page = await dashboard(t);
  await page.locator('[data-console-view="dreams"]').click();
  await page.waitForFunction(() => document.querySelectorAll('details.dream-overview-card').length === 3);
  await page.evaluate(() => {
    const originalApi = api;
    let release;
    const pending = new Promise(resolve => { release = resolve; });
    api = async (...args) => { if (args[0].endsWith('/snapshot')) await pending; return originalApi(...args); };
    window.pendingRefresh = loadDreamOverview();
    window.releaseRefresh = () => { api = originalApi; release(); };
  });
  assert.equal(await page.locator('details.dream-overview-card').count(), 3);
  await page.locator('details.dream-overview-card').nth(1).locator('summary').click();
  await page.evaluate(async () => { window.releaseRefresh(); await window.pendingRefresh; });
  assert.deepEqual(await openCards(page), ['alpha', 'beta']);
});

test('late snapshot responses cannot overwrite a newer GPU refresh', async t => {
  const page = await dashboard(t);
  await page.locator('[data-console-view="dreams"]').click();
  await page.waitForFunction(() => document.querySelectorAll('details.dream-overview-card').length === 3);
  await page.evaluate(() => {
    const originalApi = api;
    let release;
    const pending = new Promise(resolve => { release = resolve; });
    api = async (...args) => {
      const data = await originalApi(...args);
      if (!args[0].endsWith('/snapshot')) return data;
      await pending;
      return { ...data, gpus: data.gpus.map(gpu => ({ ...gpu, name: 'Outdated GPU' })) };
    };
    window.oldRefresh = loadDreamOverview();
    window.releaseOldRefresh = release;
    api = originalApi;
  });
  await page.evaluate(() => loadDreamOverview());
  await page.evaluate(async () => { window.releaseOldRefresh(); await window.oldRefresh; });
  assert.equal(await page.locator('.dream-gpu-card-head strong').first().textContent(), 'GPU 0 · Test GPU');
});
