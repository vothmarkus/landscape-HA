/* YAML travels only through authenticated Home Assistant WebSockets. */
class LandscapeConfigurationPanel extends HTMLElement {
  constructor() {
    super(); this.attachShadow({ mode: "open" });
    this._selected = new Set(); this._files = []; this._imports = [];
    this._busy = false; this._preview = null;
  }
  set hass(value) { this._hass = value; this._load(); }
  set panel(value) { this._panel = value; this._load(); }
  connectedCallback() { if (!this._built) this._build(); this._load(); }
  _el(id) { return this.shadowRoot.getElementById(id); }

  _build() {
    this._built = true;
    this.shadowRoot.innerHTML = `
      <style>
        :host{display:block;color:var(--primary-text-color,#172c38);font-family:system-ui}*{box-sizing:border-box}
        main{max-width:1200px;margin:auto;padding:24px 20px 60px}h2{font-size:20px;margin:0 0 12px}p{line-height:1.5}
        .muted,small{color:var(--secondary-text-color,#596a73)}small{display:block;margin-top:6px;overflow-wrap:anywhere}
        section{border:1px solid var(--divider-color,#ddd);border-radius:12px;padding:20px;margin-bottom:20px;background:var(--card-background-color,white)}
        button,input,select{font:inherit;color:inherit}button,select,input[type=text],input[type=search]{border:1px solid var(--divider-color,#aaa);border-radius:8px;padding:10px 12px;background:var(--card-background-color,white)}
        button{cursor:pointer;font-weight:600}button.primary{background:var(--primary-color,#007c91);color:white;border-color:transparent}button:disabled{opacity:.45;cursor:default}
        input[type=checkbox]{width:18px;height:18px;accent-color:var(--primary-color,#007c91)}input[type=search]{width:100%}input[type=file]{max-width:100%}
        .actions{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:12px 0}.actions label{display:flex;align-items:center;gap:6px}
        .status{padding:12px;border-radius:8px;background:var(--secondary-background-color,#edf2f4);white-space:pre-line;overflow-wrap:anywhere;margin:0 0 16px}
        .error{color:var(--error-color,#b00020)}.tree{max-height:55vh;overflow:auto;margin-top:12px}details{margin:8px 0}summary{cursor:pointer;padding:8px 0;overflow-wrap:anywhere}
        .folder{padding-left:16px;border-left:1px solid var(--divider-color,#ddd)}.file{display:flex;gap:10px;align-items:flex-start;padding:12px 0;border-bottom:1px solid var(--divider-color,#ddd)}
        .file-name{flex:1;min-width:130px;overflow-wrap:anywhere}.file .actions{margin:0}.file button{padding:7px 10px;font-size:13px}
        .import{padding:12px 0;border-bottom:1px solid var(--divider-color,#ddd);overflow-wrap:anywhere}.import label{display:block;margin:10px 0}.import input[type=text],.import select{display:block;width:100%;min-width:0;max-width:100%;margin-top:6px}
        pre{margin:12px 0;white-space:pre;overflow:auto;max-height:52vh;padding:16px;font:13px/1.6 ui-monospace,monospace;background:var(--secondary-background-color,#eef2f4);border-radius:8px}
        .diff-add{color:var(--success-color,#18783e)}.diff-remove{color:var(--error-color,#b00020)}.diff-hunk{color:var(--primary-color,#007c91)}
        [hidden]{display:none!important}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid var(--primary-color,#007c91)}
        @media(max-width:700px){main{padding:16px 12px}section{padding:14px}.file{flex-wrap:wrap}.file .actions{width:100%;margin-left:28px}.actions button{flex:1}.folder{padding-left:10px}pre{max-width:100%}}
      </style>
      <main>
        <p>Einzelne YAML-Dateien bearbeiten, eine Auswahl teilen oder die YAML-Konfiguration als Bundle sichern.</p>
        <div id="message" class="status" role="status" aria-live="polite" hidden></div>
        <section>
          <h2>Configuration</h2>
          <p class="muted">Dateien unter /config. secrets.yaml, interne Speicherdateien und Programmverzeichnisse sind ausgenommen. Direkt eingetragene Passwörter bleiben im YAML enthalten; vor dem Teilen prüfen.</p>
          <div class="actions"><button id="refresh">Aktualisieren</button><button id="all">Alle auswählen</button><button id="none">Auswahl aufheben</button></div>
          <input id="search" type="search" placeholder="Dateipfad oder Typ suchen" aria-label="YAML-Dateien suchen">
          <div id="tree" class="tree"></div><p id="count" class="muted"></p>
          <div class="actions"><label><input id="context" type="checkbox">Mit Kontext (ZIP mit Begleitdateien)</label><label><input id="dated" type="checkbox">Datum im Einzeldateinamen</label></div>
          <div class="actions"><button id="export-selection" class="primary">Auswahl exportieren</button><button id="export-all">Komplett-Bundle</button></div>
        </section>
        <section id="viewer" hidden><h2 id="view-title"></h2><p id="view-info" class="muted"></p><pre id="view-content"></pre><button id="close-view">Schließen</button></section>
        <section>
          <h2>YAML importieren</h2>
          <p>Eine oder mehrere YAML-Dateien auswählen, optional mit .landscape.json, oder ein Configuration-ZIP hochladen. Ziel und Importart anschließend prüfen.</p>
          <input id="upload" type="file" multiple accept=".yaml,.yml,.json,.zip" aria-label="Konfigurationsdateien importieren">
          <p id="target-hint" class="muted"></p><div id="imports"></div>
          <button id="preview-button" class="primary" hidden>Prüfen und Diff anzeigen</button>
        </section>
        <section id="preview" hidden>
          <h2>Änderungen prüfen</h2><p id="preview-summary"></p>
          <p class="muted">YAML und Einbindung sind vorgeprüft. Beim Übernehmen werden Backups erstellt und die gesamte HA-Konfiguration geprüft. Neue Prüfprobleme führen zur automatischen Rücksetzung.</p>
          <div id="diffs"></div>
          <div class="actions"><button id="apply" class="primary">Änderungen übernehmen</button><button id="discard">Verwerfen</button></div>
        </section>
        <section id="result" hidden><h2>Ergebnis</h2><p id="result-text"></p><pre id="result-details" hidden></pre><button id="download-report">Protokoll herunterladen</button></section>
        <section><h2>Backups</h2><p class="muted">Jede Übernahme sichert die Originaldateien. Zum Zurücksetzen zuerst die Vorschau öffnen. Zwischenzeitlich geänderte Dateien sind vor Überschreiben geschützt.</p><div id="backups"></div></section>
      </main>`;
    this._el("refresh").onclick = () => this._run(() => this._refresh());
    this._el("all").onclick = () => { this._selected = new Set(this._files.map(x => x.path)); this._renderTree(); };
    this._el("none").onclick = () => { this._selected.clear(); this._renderTree(); };
    this._el("search").oninput = () => this._renderTree();
    this._el("export-selection").onclick = () => this._run(() => this._export([...this._selected]));
    this._el("export-all").onclick = () => this._run(() => this._export(null));
    this._el("upload").onchange = event => this._run(() => this._upload([...event.target.files]));
    this._el("upload").addEventListener("cancel", () => { this._target = null; this._el("target-hint").textContent = ""; });
    this._el("preview-button").onclick = () => this._run(() => this._makePreview());
    this._el("apply").onclick = () => this._run(async () => {
      this._show("Backup, Übernahme und HA-Konfigurationsprüfung laufen …");
      const report = await this._call("apply", { preview_id: this._preview.preview_id });
      this._report = report; this._clearPreview(); this._el("result").hidden = false;
      const labels = {
        applied: "Dateien übernommen und HA-Prüfung abgeschlossen. Passende YAML-Bereiche anschließend in Home Assistant neu laden; falls erforderlich Home Assistant neu starten.",
        unchanged: "Keine Dateiänderungen erforderlich.",
        rolled_back: "Import zurückgesetzt. Die ursprünglichen Dateien sind wiederhergestellt.",
        recovery_required: "Rücksetzung unvollständig. Die genannten Dateien anhand des Backups prüfen, bevor Home Assistant neu gestartet wird.",
      };
      this._el("result-text").textContent = labels[report.status] || report.status;
      const details = [report.error, ...(report.validation?.warnings || []), ...(report.rollback_errors || [])].filter(Boolean).join("\n");
      this._el("result-details").hidden = !details; this._el("result-details").textContent = details;
      this._show(labels[report.status] || report.status, !["applied", "unchanged"].includes(report.status));
      this._imports = []; this._renderImports(); this._el("upload").value = "";
      await this._refresh(); this._el("result").scrollIntoView({ block: "start", behavior: "smooth" });
    });
    this._el("discard").onclick = () => this._run(async () => {
      await this._call("discard", { preview_id: this._preview.preview_id });
      this._clearPreview(); this._show("Vorschau verworfen. Keine Datei geändert.");
    });
    this._el("close-view").onclick = () => { this._el("viewer").hidden = true; };
    this._el("download-report").onclick = () => this._download("landscape_configuration_report.json", JSON.stringify(this._report, null, 2), "application/json");
  }
  _load() {
    if (!this._built || !this._hass || !this._panel || this._loaded) return;
    this._loaded = true; this._run(() => this._refresh());
  }
  _call(action, fields = {}) { return this._hass.callWS({ type: "landscape/configuration", entry_id: this._panel.config.entry_id, action, ...fields }); }
  async _run(task) {
    if (this._busy) return;
    this._busy = true; this._setBusy();
    try { await task(); } catch (error) { this._show(error.message || String(error), true); }
    finally { this._busy = false; this._setBusy(); }
  }
  _setBusy() {
    this.shadowRoot.querySelectorAll("button,input,select").forEach(el => { el.disabled = this._busy; });
    this._el("export-selection").disabled = this._busy || !this._selected.size;
    this._el("apply").disabled = this._busy || !this._preview?.files.length;
  }
  _show(message, error = false) { const box = this._el("message"); box.hidden = false; box.textContent = message; box.classList.toggle("error", error); }
  _clearPreview() { this._preview = null; this._el("preview").hidden = true; this._setBusy(); }
  _button(label, callback) { const button = document.createElement("button"); button.textContent = label; button.onclick = callback; return button; }
  async _refresh() {
    const result = await this._call("list"); this._files = result.files;
    this._selected = new Set([...this._selected].filter(path => this._files.some(file => file.path === path)));
    this._renderTree(); this._renderImports(); this._renderBackups(result.backups || []);
    if (result.skipped?.length) this._show("Nicht lesbare oder ausgeschlossene Dateien:\n" + result.skipped.join("\n"), true);
  }
  _renderTree() {
    const root = this._el("tree"); root.replaceChildren();
    const query = this._el("search").value.toLocaleLowerCase("de-DE");
    const folders = new Map([["", root]]);
    const folder = path => {
      if (folders.has(path)) return folders.get(path);
      const parts = path.split("/"); const name = parts.pop(); const parent = folder(parts.join("/"));
      const details = document.createElement("details"); details.open = true;
      const summary = document.createElement("summary"); summary.textContent = "📁 " + name;
      const children = document.createElement("div"); children.className = "folder";
      details.append(summary, children); parent.append(details); folders.set(path, children); return children;
    };
    for (const file of this._files) {
      if (query && !(file.path + " " + file.type).toLocaleLowerCase("de-DE").includes(query)) continue;
      const row = document.createElement("div"); row.className = "file";
      const choice = document.createElement("input"); choice.type = "checkbox"; choice.checked = this._selected.has(file.path);
      choice.setAttribute("aria-label", file.path + " auswählen");
      choice.onchange = () => { if (choice.checked) this._selected.add(file.path); else this._selected.delete(file.path); this._count(); };
      const label = document.createElement("div"); label.className = "file-name";
      const title = document.createElement("strong"); title.textContent = "📄 " + file.path.split("/").pop();
      const meta = document.createElement("small"); meta.textContent = file.type + " · " + Math.ceil(file.size / 1024) + " KB" + (file.active ? " · eingebunden" : " · nicht eingebunden");
      if (file.syntax_error) { meta.textContent += " · " + file.syntax_error; meta.className = "error"; }
      label.append(title, meta);
      const actions = document.createElement("div"); actions.className = "actions";
      actions.append(
        this._button("Anzeigen", () => this._run(() => this._view(file.path))),
        this._button("Exportieren", () => this._run(() => this._export([file.path]))),
        this._button("Import / Diff", () => { this._target = file.path; this._el("target-hint").textContent = "Zieldatei: /config/" + file.path; this._el("upload").value = ""; this._el("upload").click(); }),
      );
      row.append(choice, label, actions);
      const parts = file.path.split("/"); parts.pop(); folder(parts.join("/")).append(row);
    }
    this._count();
  }
  _count() { this._el("count").textContent = this._files.length + " YAML-Dateien · " + this._selected.size + " ausgewählt"; this._setBusy(); }
  async _view(path) {
    const file = await this._call("view", { path });
    this._el("viewer").hidden = false; this._el("view-title").textContent = "/config/" + path;
    this._el("view-info").textContent = file.type + " · " + (file.included_by.map(item => item.path + " → " + item.key + " (" + item.tag + ")").join("; ") || "Keine übergeordnete Einbindung") + (file.warnings?.length ? " · " + file.warnings.join("; ") : "");
    this._el("view-content").textContent = file.content; this._el("viewer").scrollIntoView({ block: "start", behavior: "smooth" });
  }
  async _export(paths) {
    const fields = { context: this._el("context").checked, dated: this._el("dated").checked };
    if (paths !== null) fields.paths = paths;
    const result = await this._call("export", fields);
    this._download(result.filename, Uint8Array.from(atob(result.content), char => char.charCodeAt(0)), result.mime);
    this._show(result.file_count + " Datei(en) exportiert.");
  }
  async _upload(files) {
    if (!files.length) return;
    this._clearPreview(); this._imports = []; this._renderImports();
    const target = this._target; this._target = null; this._el("target-hint").textContent = "";
    if (files.reduce((sum, file) => sum + file.size, 0) > 2000000) throw new Error("Import darf höchstens 2 MB groß sein.");
    const zip = files.find(file => file.name.toLowerCase().endsWith(".zip"));
    let fields;
    if (zip) {
      if (files.length !== 1) throw new Error("Bitte ein ZIP allein auswählen.");
      const bytes = new Uint8Array(await zip.arrayBuffer()); let binary = "";
      for (let start = 0; start < bytes.length; start += 8192) binary += String.fromCharCode(...bytes.subarray(start, start + 8192));
      fields = { archive: btoa(binary) };
    } else fields = { files: await Promise.all(files.map(async file => ({ filename: file.name, content: await file.text() }))) };
    const result = await this._call("inspect", fields);
    if (target && result.files.length === 1) { result.files[0].path = target; result.files[0].mode = "replace"; result.files[0].suggested_path = null; }
    this._imports = result.files.map(file => ({ ...file, selected: true }));
    this._renderImports(); this._show("Importziel und Importart prüfen, dann den Diff öffnen.");
  }
  _renderImports() {
    const container = this._el("imports"); container.replaceChildren();
    this._el("preview-button").hidden = !this._imports.length;
    for (const file of this._imports) {
      const row = document.createElement("div"); row.className = "import";
      const choice = document.createElement("input"); choice.type = "checkbox"; choice.checked = file.selected;
      choice.setAttribute("aria-label", file.filename + " importieren"); choice.onchange = () => { file.selected = choice.checked; this._clearPreview(); };
      const title = document.createElement("strong"); title.textContent = " " + file.filename;
      const existing = document.createElement("label"); existing.textContent = "Vorhandene Zieldatei";
      const targets = document.createElement("select"); targets.setAttribute("aria-label", "Zieldatei für " + file.filename);
      const placeholder = document.createElement("option"); placeholder.value = ""; placeholder.textContent = "Zieldatei wählen oder Pfad unten eingeben"; placeholder.disabled = true; targets.append(placeholder);
      const candidates = file.candidates || [];
      const paths = this._files.map(item => item.path);
      const matching = candidates.filter(path => paths.includes(path));
      for (const [name, items] of [["Passende Dateinamen", matching], [matching.length ? "Weitere YAML-Dateien" : "YAML-Dateien", paths.filter(path => !matching.includes(path)).sort()]]) {
        if (!items.length) continue;
        const group = document.createElement("optgroup"); group.label = name;
        for (const path of items) {
          const option = document.createElement("option"); option.value = path; option.textContent = "/config/" + path; group.append(option);
        }
        targets.append(group);
      }
      existing.append(targets);
      const target = document.createElement("label"); target.append(document.createTextNode("Ziel unter /config (relativer Pfad)"));
      const input = document.createElement("input"); input.type = "text"; input.value = file.path; input.placeholder = "packages/stromzaehler_neu.yaml"; input.setAttribute("aria-label", "Zielpfad für " + file.filename); target.append(input);
      const label = document.createElement("label"); label.textContent = "Importart ";
      const select = document.createElement("select"); select.setAttribute("aria-label", "Importart für " + file.filename);
      for (const [value, text] of [["replace", "Datei ersetzen"], ["create", "Als neue Datei importieren"], ["merge", "Einträge zusammenführen (IDs / Skriptschlüssel)"]]) {
        const option = document.createElement("option"); option.value = value; option.textContent = text; select.append(option);
      }
      select.value = file.mode;
      const note = document.createElement("small");
      const updateNote = () => {
        const notes = [];
        if (!file.path) notes.push(candidates.length > 1 && !file.suggested_path ? "Mehrere gleich gute Treffer. Bitte die Zieldatei im Dropdown auswählen." : "Bitte eine Zieldatei auswählen oder einen neuen Zielpfad eingeben.");
        else if (file.suggested_path === file.path && file.mode !== "create") notes.push("Nach Dateiname vorausgewählt: /config/" + file.path);
        if (file.mode === "merge") notes.push("Passende Einträge werden vollständig ersetzt, neue ergänzt und übrige beibehalten. Kommentare innerhalb ersetzter Einträge stammen aus dem Import.");
        const stale = !file.source_matches && file.source_path === file.path;
        if (stale) notes.push("Die Datei wurde seit dem Kontext-Export geändert.");
        note.textContent = notes.join(" ");
        note.classList.toggle("error", stale); note.hidden = !note.textContent;
      };
      const updateMerge = () => {
        const supported = this._files.find(item => item.path === file.path)?.merge_supported;
        const option = select.querySelector('option[value="merge"]'); option.hidden = !supported; option.disabled = !supported;
        if (!supported && file.mode === "merge") { file.mode = "replace"; select.value = "replace"; }
      };
      const updateTarget = () => { targets.value = paths.includes(file.path) ? file.path : ""; };
      const changeTarget = path => {
        file.path = path; input.value = path;
        file.mode = paths.includes(path) ? file.mode === "merge" ? "merge" : "replace" : "create";
        select.value = file.mode; updateTarget(); updateMerge(); updateNote(); this._clearPreview();
      };
      updateTarget(); updateMerge(); updateNote();
      targets.onchange = () => changeTarget(targets.value);
      input.oninput = () => changeTarget(input.value);
      select.onchange = () => { file.mode = select.value; updateNote(); this._clearPreview(); }; label.append(select);
      row.append(choice, title, existing, target, label, note); container.append(row);
    }
  }
  async _makePreview() {
    this._clearPreview();
    const files = this._imports.filter(file => file.selected).map(({ path, mode, content, source_sha256, source_path }) => ({ path, mode, content, source_sha256, source_path }));
    this._renderPreview(await this._call("preview", { files }));
  }
  _renderPreview(result) {
    this._preview = result; this._el("preview").hidden = false;
    this._el("preview-summary").textContent = result.files.length + " geänderte Datei(en) · +" + result.files.reduce((sum, file) => sum + file.added, 0) + " / −" + result.files.reduce((sum, file) => sum + file.removed, 0) + " Zeilen";
    const diffs = this._el("diffs"); diffs.replaceChildren();
    for (const file of result.files) {
      const details = document.createElement("details"); details.open = true;
      const summary = document.createElement("summary"); summary.textContent = file.path + " · " + file.context.type + " · +" + file.added + " / −" + file.removed;
      const warnings = document.createElement("p"); warnings.className = "muted"; warnings.textContent = file.context.warnings.join(" ");
      const pre = document.createElement("pre");
      for (const line of file.diff.split("\n")) { const span = document.createElement("span"); span.textContent = line + "\n"; span.className = line.startsWith("+") ? "diff-add" : line.startsWith("-") ? "diff-remove" : line.startsWith("@@") ? "diff-hunk" : ""; pre.append(span); }
      details.append(summary, warnings, pre); diffs.append(details);
    }
    this._el("preview").scrollIntoView({ block: "start", behavior: "smooth" });
  }
  _renderBackups(backups) {
    const container = this._el("backups"); container.replaceChildren();
    if (!backups.length) { container.textContent = "Noch keine Dateiänderungen übernommen."; return; }
    const labels = { applied: "übernommen", rolled_back: "zurückgesetzt", prepared: "vorbereitet", pending: "unterbrochen", recovery_required: "manuell prüfen" };
    for (const backup of backups.slice(0, 20)) {
      const details = document.createElement("details"); const summary = document.createElement("summary");
      summary.textContent = (backup.created_at ? new Date(backup.created_at).toLocaleString("de-DE") : "Backup") + " · " + (labels[backup.status] || backup.status) + " · " + backup.files.length + " Datei(en)";
      const paths = document.createElement("p"); paths.textContent = backup.files.map(file => file.path).join(", ");
      const location = document.createElement("small"); location.textContent = "Backup: /config/.storage/landscape_configuration/" + backup.id;
      details.append(summary, paths, location);
      if (backup.status === "applied") details.append(this._button("Rücksetzung prüfen", () => this._run(async () => { this._clearPreview(); this._renderPreview(await this._call("restore_preview", { backup_id: backup.id })); })));
      if (backup.rollback_errors?.length) { const error = document.createElement("p"); error.className = "error"; error.textContent = "Manuell prüfen: " + backup.rollback_errors.join(", "); details.append(error); }
      container.append(details);
    }
  }
  _download(filename, content, type) {
    const url = URL.createObjectURL(new Blob([content], { type }));
    const link = document.createElement("a"); link.href = url; link.download = filename;
    this.shadowRoot.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 30000);
  }
}
customElements.define("landscape-configuration-panel", LandscapeConfigurationPanel);
