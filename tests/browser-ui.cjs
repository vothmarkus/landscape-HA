/* Run with Playwright installed; optionally set LANDSCAPE_CHROMIUM_PATH. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

(async () => {
  const frontend = path.join(__dirname, '../custom_components/landscape/frontend');
  const bytes = Buffer.from([0, 255, 128, 13, 10]);
  const server = http.createServer((request, response) => {
    const pathname = new URL(request.url, 'http://localhost').pathname;
    if (pathname === '/') {
      response.setHeader('Content-Type', 'text/html; charset=utf-8');
      response.end('<html lang="de"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0;--primary-color:#007c91;--primary-background-color:#f4f6f8;--card-background-color:white;--primary-text-color:#172c38;--secondary-text-color:#54656e;--divider-color:#dce3e7}</style><body><script src="/landscape_static/assist-panel.js"></script></body></html>');
    } else if (pathname.startsWith('/landscape_static/')) {
      response.setHeader('Content-Type', 'text/javascript; charset=utf-8');
      response.end(fs.readFileSync(path.join(frontend, path.basename(pathname))));
    } else if (pathname.startsWith('/download/')) {
      response.setHeader('Content-Type', 'application/octet-stream');
      response.setHeader('Content-Disposition', 'attachment; filename="' + path.basename(pathname) + '"');
      response.end(bytes);
    } else { response.statusCode = 404; response.end(); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({ headless: true, executablePath: process.env.LANDSCAPE_CHROMIUM_PATH || undefined, args: ['--no-sandbox', '--single-process', '--no-zygote', '--disable-gpu', '--use-angle=swiftshader', '--use-gl=angle', '--in-process-gpu'] });
    const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:' + server.address().port);
    await page.evaluate(() => {
      const inventory = ['configuration.yaml', 'root.bin', 'large.bin', 'www/app.js', 'www/settings.json', 'www/icon.png', 'custom_components/example/__init__.py'].map(path => ({ path, type: path.split('.').at(-1), size: path === 'large.bin' ? 1000001 : 100, modified_at: '2026-10-28T10:00:00Z', available: path !== 'large.bin', merge_supported: false }));
      window.calls = []; let applied = false;
      const element = document.createElement('landscape-assist-panel'); element.style.height = '100vh'; document.body.append(element);
      element.panel = { config: { entry_id: 'test' } };
      element.hass = { callWS: async msg => {
        window.calls.push(msg);
        if (msg.type === 'landscape/assist') return { exports: [] };
        if (msg.type === 'landscape/download_report') return { filename: 'landscape_browser_report.json', download_url: '/download/landscape_browser_report.json' };
        if (!msg.scope) return { files: [], backups: [], skipped: [] };
        if (msg.scope !== 'browser') throw Error('Wrong scope');
        if (msg.action === 'list') return { files: inventory, directories: ['www', 'www/empty', 'custom_components', 'custom_components/example'], backups: applied ? [{ id: 'backup', status: 'applied', created_at: '2026-10-28T10:00:00Z', files: [{ path: 'www/icon.png' }, { path: 'www/app.js' }] }] : [] };
        if (msg.action === 'view') return { type: 'file', size: 5, sha256: 'a'.repeat(64), binary: msg.path.endsWith('.png'), content: '<img src=x onerror="window.injected=true">' };
        if (msg.action === 'export') { const name = msg.paths?.length === 1 ? msg.paths[0].split('/').at(-1) : 'landscape_browser.zip'; return { filename: name, download_url: '/download/' + name, file_count: msg.paths?.length || inventory.length }; }
        if (msg.action === 'inspect') return { files: (msg.files || [{ filename: 'www/icon.png', content: 'AP+A', encoding: 'base64' }]).map(file => ({ ...file, path: file.filename, mode: 'replace', source_matches: true, candidates: [] })) };
        if (msg.action === 'preview' || msg.action === 'restore_preview') return { preview_id: 'review', files: [{ path: 'www/icon.png', context: { type: 'png', warnings: [] }, binary: true, added: 0, removed: 0, diff: '', before_size: 5, after_size: 3, before_hash: 'a'.repeat(64), after_hash: 'b'.repeat(64) }] };
        if (msg.action === 'apply') { applied = true; return { status: 'applied', files: [{ path: 'www/icon.png' }], validation: { warnings: [] } }; }
        if (msg.action === 'discard') return { discarded: true };
        throw Error('Unexpected action: ' + msg.action);
      } };
    });
    await page.locator('#browser-tab').click();
    const panel = page.locator('landscape-browser-panel');
    const el = id => panel.locator('#' + id);
    const idle = () => page.waitForFunction(() => {
      const panel = document.querySelector('landscape-assist-panel').shadowRoot.querySelector('landscape-browser-panel');
      return panel._loaded && !panel._busy;
    });
    await idle();
    assert.equal(await page.locator('#browser-tab').getAttribute('aria-pressed'), 'true');
    assert.equal(await page.locator('landscape-configuration-panel').isVisible(), false);
    assert.equal(await panel.getByRole('checkbox', { name: 'large.bin auswählen', exact: true }).isDisabled(), true);
    await panel.getByRole('button', { name: '📁 www', exact: true }).click();
    assert.equal(await el('tree').locator('input[type=checkbox]').count(), 3);
    assert.match(await el('breadcrumbs').innerText(), /www/);
    let downloadWait = page.waitForEvent('download');
    await el('export-all').click(); await idle();
    await downloadWait;
    assert.deepEqual(await page.evaluate(() => window.calls.filter(x => x.action === 'export').at(-1).paths), ['www/app.js', 'www/settings.json', 'www/icon.png']);
    await el('tree').locator('.file').filter({ hasText: 'icon.png' }).getByRole('button', { name: 'Anzeigen', exact: true }).click(); await idle();
    assert.match(await el('view-content').innerText(), /Binärdatei/);
    await el('tree').locator('.file').filter({ hasText: 'app.js' }).getByRole('button', { name: 'Anzeigen', exact: true }).click(); await idle();
    assert.equal(await el('view-content').locator('img').count(), 0);
    assert.match(await el('view-content').innerText(), /<img/);
    const chooserWait = page.waitForEvent('filechooser');
    await el('tree').locator('.file').filter({ hasText: 'icon.png' }).getByRole('button', { name: 'Import / Diff', exact: true }).click();
    await (await chooserWait).setFiles({ name: 'new-image.bin', mimeType: 'application/octet-stream', buffer: bytes }); await idle();
    let call = await page.evaluate(() => window.calls.filter(x => x.action === 'inspect').at(-1));
    assert.equal(call.files[0].filename, 'www/icon.png');
    assert.equal(call.files[0].content, bytes.toString('base64'));
    await el('preview-button').click(); await idle();
    assert.match(await el('diffs').innerText(), /SHA-256/);
    assert.match(await el('diffs').innerText(), /Vorher: 5 Bytes/);
    assert.equal(await page.evaluate(() => window.calls.filter(x => x.action === 'preview').at(-1).files[0].encoding), 'base64');
    await el('apply').click(); await idle();
    assert.match(await el('result-text').innerText(), /übernommen/);
    await el('tree').locator('.file').filter({ hasText: 'icon.png' }).getByRole('button', { name: 'Historie', exact: true }).click();
    assert.match(await el('history-filter').innerText(), /www\/icon.png/);
    await el('backups').locator('summary').first().click();
    await panel.getByRole('button', { name: 'Rücksetzung prüfen', exact: true }).click(); await idle();
    assert.equal(await page.evaluate(() => window.calls.at(-1).action), 'restore_preview');
    await el('discard').click(); await idle();
    await el('upload').setInputFiles({ name: 'new.js', mimeType: 'application/octet-stream', buffer: Buffer.from('const text = "Grüße";\r\n') }); await idle();
    call = await page.evaluate(() => window.calls.filter(x => x.action === 'inspect').at(-1));
    assert.equal(call.files[0].filename, 'www/new.js');
    assert.equal(Buffer.from(call.files[0].content, 'base64').toString(), 'const text = "Grüße";\r\n');
    await el('upload').setInputFiles({ name: 'bundle.zip', mimeType: '', buffer: bytes }); await idle();
    assert.equal(await page.evaluate(() => window.calls.filter(x => x.action === 'inspect').at(-1).archive), bytes.toString('base64'));
    await el('unpack').uncheck();
    await el('upload').setInputFiles({ name: 'archive.zip', mimeType: '', buffer: bytes }); await idle();
    assert.equal(await page.evaluate(() => window.calls.filter(x => x.action === 'inspect').at(-1).files[0].filename), 'www/archive.zip');
    await el('folder-path').fill('www/empty'); await panel.getByRole('button', { name: 'Pfad öffnen', exact: true }).click();
    assert.match(await el('tree').innerText(), /leer/);
    await el('breadcrumbs').getByRole('button', { name: '/config', exact: true }).click();
    await el('search').fill('__init__.py');
    assert.equal(await el('tree').locator('.file').count(), 1);
    await el('all').click();
    assert.match(await el('count').innerText(), /1 ausgewählt/);
    await el('search').fill('nothing-matches');
    assert.match(await el('tree').innerText(), /Keine passenden/);
    await el('search').fill('');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: '/tmp/landscape-browser-mobile.png', fullPage: true });
    const overflow = await panel.evaluate(element => element.shadowRoot.querySelector('main').scrollWidth > element.clientWidth);
    assert.equal(overflow, false, 'Browser must fit a phone viewport');
    await page.locator('#config-tab').click(); await page.locator('#browser-tab').click(); await idle();
    assert.equal(await el('breadcrumbs').isVisible(), true);
    assert.deepEqual(errors, []);
    assert.equal(await page.evaluate(() => window.injected), undefined);
    console.log('Browser UI passed: navigation, search, binary downloads/imports, ZIP mode, diff, history, restore, mobile layout, and tab switching.');
  } finally { if (browser) await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
