/* Run with Playwright installed; optionally set LANDSCAPE_CHROMIUM_PATH. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

(async () => {
  const frontend = path.join(__dirname, '../custom_components/landscape/frontend');
  const yamlBytes = Buffer.from('\uFEFF# Gaszähler\r\ndefault_config:\r\n');
  const zipBytes = Buffer.from('504b0506000000000000000000000000000000000000', 'hex');
  const downloads = [];
  const server = http.createServer((request, response) => {
    const pathname = new URL(request.url, 'http://localhost').pathname;
    if (pathname === '/') {
      response.setHeader('Content-Type', 'text/html; charset=utf-8');
      response.end('<html lang="de"><style>body{margin:0;--primary-color:#007c91;--primary-background-color:#f4f6f8;--card-background-color:white;--primary-text-color:#172c38;--secondary-text-color:#54656e;--divider-color:#dce3e7}</style><body><script src="/landscape_static/assist-panel.js"></script></body></html>');
    } else if (['/landscape_static/assist-panel.js', '/landscape_static/configuration-panel.js'].includes(pathname)) {
      response.setHeader('Content-Type', 'text/javascript; charset=utf-8');
      response.end(fs.readFileSync(path.join(frontend, path.basename(pathname))));
    } else if (pathname.startsWith('/api/landscape/download/fixture/')) {
      const filename = path.basename(pathname);
      downloads.push(filename);
      response.setHeader('Content-Disposition', 'attachment; filename="' + filename + '"');
      response.setHeader('Content-Type', filename.endsWith('.zip') ? 'application/zip' : filename.endsWith('.json') ? 'application/json' : 'application/yaml');
      response.end(filename.endsWith('.zip') ? zipBytes : filename.endsWith('.json') ? '{"status":"applied"}' : yamlBytes);
    } else { response.statusCode = 404; response.end(); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true, executablePath: process.env.LANDSCAPE_CHROMIUM_PATH || undefined, args: ['--no-sandbox', '--single-process', '--no-zygote', '--disable-gpu'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:' + server.address().port);
    await page.evaluate(() => {
      // WebViews may ignore a.download; the HTTP response must supply the name.
      Object.defineProperty(HTMLAnchorElement.prototype, 'download', { get() { return ''; }, set() {} });
      const inventory = [
        ['configuration.yaml', 'configuration', false], ['automations.yaml', 'automations', true],
        ['scripts.yaml', 'scripts', true], ['packages/gasmeter.yaml', 'package', false],
        ['packages/sauna.yaml', 'package', false], ['includes/sauna.yaml', 'yaml', false],
      ].map(([path, type, merge_supported]) => ({ path, type, merge_supported, size: 1042, active: true, included_by: [], warnings: [] }));
      const content = '# Gaszähler\n- id: gas\n  alias: Gaszähler neu\n  actions: []\n';
      window.calls = [];
      let applied = false;
      const preview = { preview_id: 'preview-one', files: [{ path: 'automations.yaml', mode: 'replace', added: 2, removed: 1, context: { type: 'automations', warnings: [] }, diff: '--- aktuell/automations.yaml\n+++ import/automations.yaml\n@@ -1,2 +1,3 @@\n-  alias: Gaszähler alt\n+  alias: Gaszähler neu\n+  description: <img src=x onerror="window.injected=true">\n' }] };
      const element = document.createElement('landscape-assist-panel');
      element.style.height = '100vh'; document.body.append(element);
      element.panel = { config: { entry_id: 'test-entry' } };
      element.hass = { callWS: async msg => {
        window.calls.push(msg);
        const download = filename => ({ filename, download_url: '/api/landscape/download/fixture/' + filename + '?authSig=fixture' });
        if (msg.type === 'landscape/download_report') return download(msg.kind === 'assist' ? 'assist_apply_report.json' : 'landscape_configuration_report.json');
        if (msg.type === 'landscape/assist') return msg.action === 'export' ? { ...download('assist_landscape.zip'), entity_count: 1, source_id: 'source-one' } : { exports: [], report: { status: 'applied', applied_count: 1 } };
        if (msg.action === 'list') return { files: inventory, skipped: [], backups: applied ? [{ id: 'backup-one', created_at: '2026-09-15T10:00:00Z', status: 'applied', files: [{ path: 'automations.yaml' }], rollback_errors: [] }] : [] };
        if (msg.action === 'export') return { ...download(msg.context || msg.paths?.length !== 1 ? 'configuration.zip' : 'automations.yaml'), file_count: msg.paths?.length || inventory.length };
        if (msg.action === 'view') return { type: 'automations', content: content + '# <img src=x onerror="window.injected=true">', included_by: [{ path: 'configuration.yaml', key: 'automation', tag: '!include' }], warnings: [] };
        if (msg.action === 'inspect') {
          const suggestions = {
            'configuration_blitzer_korrigiert.yaml': { path: 'configuration.yaml', suggested_path: 'configuration.yaml', candidates: ['configuration.yaml'] },
            'gasmeter.yaml': { path: 'packages/gasmeter.yaml', candidates: ['packages/gasmeter.yaml'] },
            'sauna_korrigiert.yaml': { path: '', candidates: ['includes/sauna.yaml', 'packages/sauna.yaml'] },
            'neue_datei.yaml': { path: 'neue_datei.yaml', mode: 'create', candidates: [] },
          };
          return { files: msg.files.filter(file => file.filename.endsWith('.yaml')).map(file => ({ ...file, path: file.filename, mode: 'replace', source_matches: true, candidates: [], ...suggestions[file.filename] })) };
        }
        if (msg.action === 'preview' || msg.action === 'restore_preview') return preview;
        if (msg.action === 'apply') { applied = true; return { status: 'applied', files: [{ path: 'automations.yaml' }], validation: { warnings: [] } }; }
        if (msg.action === 'discard') return { discarded: true };
        throw Error('Unexpected API action: ' + msg.action);
      } };
    });
    await page.locator('#config-tab').click();
    const config = page.locator('landscape-configuration-panel');
    const el = id => config.locator('#' + id);
    const idle = () => page.waitForFunction(() => {
      const parent = document.querySelector('landscape-assist-panel');
      const child = parent.shadowRoot.querySelector('landscape-configuration-panel');
      return child._loaded && !child._busy;
    });
    await idle();
    assert.equal(await el('tree').locator('.file').count(), 6);
    await config.getByRole('checkbox', { name: 'automations.yaml auswählen', exact: true }).check();
    let downloadPromise = page.waitForEvent('download');
    await el('export-selection').click(); await idle();
    const yamlDownload = await downloadPromise;
    assert.equal(yamlDownload.suggestedFilename(), 'automations.yaml');
    assert.deepEqual(fs.readFileSync(await yamlDownload.path()), yamlBytes);
    assert.equal(await page.evaluate(() => window.calls.filter(x => x.action === 'export').at(-1).download), true);
    await config.getByRole('checkbox', { name: 'scripts.yaml auswählen', exact: true }).check();
    await el('context').check(); downloadPromise = page.waitForEvent('download');
    await el('export-selection').click(); await idle();
    const zipDownload = await downloadPromise;
    assert.equal(zipDownload.suggestedFilename(), 'configuration.zip');
    assert.deepEqual(fs.readFileSync(await zipDownload.path()), zipBytes);
    assert.deepEqual(await page.evaluate(() => window.calls.filter(x => x.action === 'export').at(-1).paths), ['automations.yaml', 'scripts.yaml']);
    await el('tree').locator('.file').filter({ hasText: 'automations.yaml' }).getByText('Anzeigen', { exact: true }).click(); await idle();
    assert.equal(await el('view-content').locator('img').count(), 0);
    const upload = async name => {
      await el('upload').setInputFiles({ name, mimeType: 'application/yaml', buffer: Buffer.from('{}\n') });
      await idle();
    };
    await upload('configuration_blitzer_korrigiert.yaml');
    const target = () => el('imports').getByRole('combobox', { name: /^Zieldatei für / });
    const mode = () => el('imports').getByRole('combobox', { name: /^Importart für / });
    const input = () => el('imports').getByRole('textbox');
    assert.equal(await target().inputValue(), 'configuration.yaml');
    assert.equal(await input().inputValue(), 'configuration.yaml');
    assert.equal(await mode().inputValue(), 'replace');
    assert.equal(await target().locator('option:not([value=""])').count(), 6);
    assert.match(await el('imports').innerText(), /Nach Dateiname vorausgewählt/);
    if (process.env.LANDSCAPE_SCREENSHOTS) {
      fs.mkdirSync(process.env.LANDSCAPE_SCREENSHOTS, { recursive: true });
      const section = config.locator('section:has(#upload)');
      await section.screenshot({ path: path.join(process.env.LANDSCAPE_SCREENSHOTS, 'import-target-desktop.png') });
      await page.setViewportSize({ width: 390, height: 844 });
      await section.scrollIntoViewIfNeeded();
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= 390));
      await section.screenshot({ path: path.join(process.env.LANDSCAPE_SCREENSHOTS, 'import-target-mobile.png') });
      await page.setViewportSize({ width: 1280, height: 1000 });
    }
    await el('preview-button').click(); await idle();
    assert.equal((await page.evaluate(() => window.calls.filter(x => x.action === 'preview').at(-1).files))[0].path, 'configuration.yaml');
    await target().selectOption('scripts.yaml');
    assert.equal(await input().inputValue(), 'scripts.yaml');
    assert.equal(await el('preview').isVisible(), false);
    await mode().selectOption('merge');
    await target().selectOption('packages/gasmeter.yaml');
    assert.equal(await mode().inputValue(), 'replace');
    assert.equal(await mode().locator('option[value=merge]').evaluate(el => el.disabled), true);
    await input().fill('packages/new.yaml');
    assert.equal(await target().inputValue(), '');
    assert.equal(await mode().inputValue(), 'create');
    await target().selectOption('automations.yaml');
    assert.equal(await input().inputValue(), 'automations.yaml');
    assert.equal(await mode().inputValue(), 'replace');
    await el('preview-button').click(); await idle();
    assert.equal((await page.evaluate(() => window.calls.filter(x => x.action === 'preview').at(-1).files))[0].path, 'automations.yaml');
    await upload('sauna_korrigiert.yaml');
    assert.equal(await target().inputValue(), '');
    assert.equal(await input().inputValue(), '');
    assert.match(await el('imports').innerText(), /gleich gute Treffer/);
    await target().selectOption('includes/sauna.yaml');
    assert.equal(await input().inputValue(), 'includes/sauna.yaml');
    await upload('neue_datei.yaml');
    assert.equal(await mode().inputValue(), 'create');
    await input().fill('configuration.yaml');
    assert.equal(await target().inputValue(), 'configuration.yaml');
    assert.equal(await mode().inputValue(), 'replace');
    const chooserPromise = page.waitForEvent('filechooser');
    await el('tree').locator('.file').filter({ hasText: 'scripts.yaml' }).getByRole('button', { name: 'Import / Diff' }).click();
    await (await chooserPromise).setFiles({ name: 'configuration_blitzer_korrigiert.yaml', mimeType: 'application/yaml', buffer: Buffer.from('{}\n') });
    await idle();
    assert.equal(await target().inputValue(), 'scripts.yaml');
    assert.doesNotMatch(await el('imports').innerText(), /Nach Dateiname vorausgewählt/);
    await el('upload').setInputFiles([
      { name: 'automations.yaml', mimeType: 'application/yaml', buffer: Buffer.from('- id: gas\n  actions: []\n') },
      { name: 'gasmeter.yaml', mimeType: 'application/yaml', buffer: Buffer.from('input_boolean:\n  hello:\n') },
    ]);
    await idle();
    const rows = el('imports').locator('.import');
    assert.equal(await rows.count(), 2);
    assert.equal(await rows.nth(0).locator('option[value=merge]').evaluate(el => el.disabled), false);
    assert.equal(await rows.nth(1).locator('option[value=merge]').evaluate(el => el.disabled), true);
    await rows.nth(1).locator('input[type=checkbox]').uncheck();
    await el('preview-button').click(); await idle();
    assert.equal((await page.evaluate(() => window.calls.filter(x => x.action === 'preview').at(-1).files)).length, 1);
    assert.equal(await el('diffs').locator('img').count(), 0);
    await rows.nth(0).locator('input[type=text]').fill('scripts.yaml');
    assert.equal(await el('preview').isVisible(), false);
    await rows.nth(0).locator('input[type=text]').fill('automations.yaml');
    await el('preview-button').click(); await idle();
    if (process.env.LANDSCAPE_SCREENSHOTS) {
      fs.mkdirSync(process.env.LANDSCAPE_SCREENSHOTS, { recursive: true });
      await page.screenshot({ path: path.join(process.env.LANDSCAPE_SCREENSHOTS, 'configuration-desktop.png'), fullPage: true });
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await el('preview').scrollIntoViewIfNeeded();
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= 390));
    if (process.env.LANDSCAPE_SCREENSHOTS) await page.screenshot({ path: path.join(process.env.LANDSCAPE_SCREENSHOTS, 'configuration-mobile.png') });
    await el('apply').click(); await idle();
    assert.equal(await el('result').isVisible(), true);
    const applyCall = await page.evaluate(() => window.calls.find(x => x.action === 'apply'));
    assert.equal(applyCall.preview_id, 'preview-one');
    assert.equal(applyCall.files, undefined);
    downloadPromise = page.waitForEvent('download');
    await el('download-report').click(); await idle();
    assert.equal((await downloadPromise).suggestedFilename(), 'landscape_configuration_report.json');
    assert.equal(await page.evaluate(() => JSON.parse(window.calls.filter(x => x.type === 'landscape/download_report').at(-1).report).status), 'applied');
    await el('backups').locator('summary').click();
    await el('backups').getByRole('button', { name: 'Rücksetzung prüfen' }).click(); await idle();
    assert.equal(await el('preview').isVisible(), true);
    await el('discard').click(); await idle();
    assert.equal(await el('preview').isVisible(), false);
    await page.locator('#assist-tab').click();
    assert.equal(await page.locator('#assist-main').isVisible(), true);
    downloadPromise = page.waitForEvent('download');
    await page.locator('#export').click();
    assert.equal((await downloadPromise).suggestedFilename(), 'assist_landscape.zip');
    downloadPromise = page.waitForEvent('download');
    await page.locator('#report').click();
    assert.equal((await downloadPromise).suggestedFilename(), 'assist_apply_report.json');
    assert.deepEqual(downloads, ['automations.yaml', 'configuration.zip', 'landscape_configuration_report.json', 'assist_landscape.zip', 'assist_apply_report.json']);
    assert.equal(await page.evaluate(() => window.injected), undefined);
    assert.deepEqual(errors, []);
    console.log('Configuration UI: target suggestions, manual selection, ambiguous names, new paths, explicit target priority, merge availability, review invalidation, downloads, escaping, mobile layout, apply, restore and Assist navigation passed.');
  } finally {
    await browser.close(); server.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
