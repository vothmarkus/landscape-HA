/* HA Landscape Assist: no external libraries, network clients or AI calls. */
class LandscapeAssistPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._selected = new Set();
    this._busy = false;
    this._preview = null;
    this._report = null;
    this._raw = null;
  }

  set hass(value) {
    this._hass = value;
    if (this._configurationLoaded) this._el("configuration").hass = value;
    this._maybeLoad();
  }
  get hass() { return this._hass; }
  set panel(value) {
    this._panel = value;
    this._maybeLoad();
  }

  connectedCallback() {
    if (!this._built) this._build();
    this._maybeLoad();
  }

  _build() {
    this._built = true;
    this.shadowRoot.innerHTML =
      '<style>' +
      ':host{display:block;height:100%;overflow:auto;color:var(--primary-text-color);background:var(--primary-background-color);font-family:var(--paper-font-body1_-_font-family,system-ui)}' +
      '*{box-sizing:border-box}header{display:flex;gap:16px;align-items:center;padding:12px 20px;background:var(--app-header-background-color,var(--primary-color));color:var(--app-header-text-color,white)}' +
      'header button{background:transparent;color:inherit;border:0;font-size:24px;padding:6px}h1{font-size:22px;margin:0}main{max-width:1200px;margin:auto;padding:24px 20px 60px}' +
      'h2{font-size:18px;margin:0 0 12px}p{line-height:1.5;margin:8px 0 16px}.muted{color:var(--secondary-text-color)}' +
      '.steps{display:grid;grid-template-columns:1fr 1fr;gap:16px}section{padding:20px;border:1px solid var(--divider-color,#ddd);border-radius:12px;background:var(--card-background-color,white);margin-bottom:20px}' +
      'button,.file-label{font:inherit;font-weight:600;border:1px solid var(--divider-color,#aaa);border-radius:8px;padding:10px 14px;cursor:pointer;background:var(--card-background-color,white);color:var(--primary-text-color)}' +
      'button.primary,nav button[aria-pressed=true]{background:var(--primary-color,#03a9f4);color:var(--text-primary-color,white);border-color:transparent}button:disabled{opacity:.45;cursor:default}' +
      'input[type=checkbox]{width:18px;height:18px;vertical-align:middle;accent-color:var(--primary-color)}input[type=search]{font:inherit;padding:10px;border:1px solid var(--divider-color,#aaa);border-radius:8px;width:100%;color:inherit;background:var(--card-background-color,white)}' +
      '.actions,.filters{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin:12px 0}.filters label{display:flex;gap:6px;align-items:center}' +
      '.scroll{overflow:auto;max-height:62vh}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:12px 8px;border-bottom:1px solid var(--divider-color,#ddd);vertical-align:top}th{position:sticky;top:0;background:var(--card-background-color,white);z-index:1}' +
      'td small{display:block;margin-top:5px;overflow-wrap:anywhere}.conflict{color:var(--error-color,#b00020)}.unchanged{opacity:.65}.status{white-space:pre-line;overflow-wrap:anywhere;padding:12px;border-radius:8px;background:var(--secondary-background-color,#eee);margin-bottom:16px}' +
      '.reason{max-width:340px;min-width:190px;overflow-wrap:anywhere}[hidden]{display:none!important}details{margin-top:8px}summary{cursor:pointer}button:focus-visible,input:focus-visible{outline:3px solid var(--primary-color)}' +
      '@media(max-width:700px){.steps{grid-template-columns:1fr}main{padding:16px 12px}section{padding:14px}td,th{padding:10px 6px}.actions button{flex:1}h1{font-size:20px}}' +
      '@media(max-width:700px){table,tbody{display:block;width:100%}thead{display:none}tr{display:grid;grid-template-columns:28px minmax(0,1fr);border:1px solid var(--divider-color,#ddd);border-radius:8px;padding:10px;margin:10px 0}td{display:block;grid-column:2;border:0;padding:5px 0;min-width:0;overflow-wrap:anywhere}td:first-child{grid-column:1;grid-row:1 / 7}td:nth-child(2){font-weight:600}td:nth-child(n+3)::before{content:attr(data-label);display:block;font-size:12px;color:var(--secondary-text-color);font-weight:600;margin-bottom:3px}td.reason{min-width:0;max-width:none}.scroll{max-height:70vh;overflow-y:auto;overflow-x:hidden}}' +
      '</style>' +
      '<header><button id="menu" aria-label="Seitenmenü öffnen">☰</button><h1>HA Landscape</h1></header>' +
      '<nav class="actions" aria-label="Landscape-Bereiche" style="padding:0 20px"><button id="assist-tab" aria-pressed="true">Entitäten</button><button id="config-tab" aria-pressed="false">YAML-Dateien</button></nav>' +
      '<landscape-configuration-panel id="configuration" hidden></landscape-configuration-panel>' +
      '<main id="assist-main"><p>Entitätsdaten exportieren, im KI-Chat optimieren lassen und die Änderungen in Landscape importieren. Namen, Aliase, Assist-Freigaben und räumliche Zuordnungen prüfst du vor der Übernahme.</p>' +
      '<div id="message" class="status" role="status" aria-live="polite" hidden></div>' +
      '<div class="steps"><section><h2>1. Entitäten exportieren</h2><p>ZIP mit Entitätsdaten, Gerätebeziehungen, Bereichen, Etagen und der Optimierungsanleitung herunterladen.</p>' +
      '<button id="export" class="primary">Entitäten exportieren</button><p id="export-info" class="muted"></p>' +
      '<p class="muted">Das ZIP enthält Geräte- und Raumnamen. Prüfe den Inhalt vor der Weitergabe.</p></section>' +
      '<section><h2>2. Änderungen importieren</h2><p>Einen KI-Chat wie ChatGPT öffnen, dort das exportierte ZIP hochladen und schreiben: <strong>„Optimiere die Entitätsdaten nach der Anleitung und dem Schema im ZIP.“</strong></p>' +
      '<p>Die zurückgegebene <strong>assist_optimized.json</strong> herunterladen und anschließend in Landscape importieren.</p>' +
      '<input id="file" type="file" accept=".json,application/json" aria-label="Optimierte JSON-Datei auswählen">' +
      '<div class="actions"><button id="recheck" hidden>Datei erneut prüfen</button></div></section></div>' +
      '<section id="preview" hidden><h2>3. Prüfen und übernehmen</h2><p id="summary"></p><p class="muted">Entity-IDs bleiben unverändert. Etagenänderungen betreffen einen ganzen Bereich und sind zunächst abgewählt.</p>' +
      '<div id="filters" class="filters"></div><input id="search" type="search" placeholder="Entität, Bereich oder Vorschlag suchen" aria-label="Vorschläge durchsuchen">' +
      '<p id="selection" class="muted"></p><div class="scroll"><table><thead><tr><th>Auswahl</th><th>Entität / Bereich</th><th>Änderung</th><th>Aktuell</th><th>Vorschlag</th><th>Begründung / Status</th></tr></thead><tbody id="rows"></tbody></table></div>' +
      '<div class="actions"><button id="apply" class="primary">Ausgewählte übernehmen</button><button id="apply-all">Alle übernehmen</button><button id="discard">Verwerfen</button></div></section>' +
      '<section id="report-section" hidden><h2>Ergebnisprotokoll</h2><p id="report-info"></p><button id="report">Protokoll herunterladen</button></section></main>';

    this._el("menu").addEventListener("click", () => {
      this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true }));
    });
    this._el("assist-tab").onclick = () => this._switchMode(false);
    this._el("config-tab").onclick = () => this._switchMode(true);
    this._el("export").addEventListener("click", () => this._run(async () => {
      const result = await this._call("export", { download: true });
      this._download(result.filename, result.download_url);
      this._show(result.entity_count + " Entitäten exportiert. ZIP in einem KI-Chat wie ChatGPT hochladen.");
      this._el("export-info").textContent = "Export-ID: " + result.source_id;
    }));
    this._el("file").addEventListener("change", (event) => this._run(async () => {
      const file = event.target.files[0];
      if (!file) return;
      this._clearPreview();
      this._raw = null;
      this._el("recheck").hidden = true;
      if (file.size > 2000000) throw new Error("Die Importdatei darf höchstens 2 MB groß sein.");
      this._raw = await file.text();
      this._el("recheck").hidden = false;
      await this._loadPreview();
    }));
    this._el("recheck").addEventListener("click", () => this._run(() => this._loadPreview()));
    this._el("search").addEventListener("input", () => this._renderRows());
    this._el("apply").addEventListener("click", () => this._run(() => this._apply(false)));
    this._el("apply-all").addEventListener("click", () => this._run(() => this._apply(true)));
    this._el("discard").addEventListener("click", () => this._run(async () => {
      await this._call("discard", { preview_id: this._preview.preview_id });
      this._clearPreview();
      this._raw = null;
      this._el("file").value = "";
      this._el("recheck").hidden = true;
      this._show("Vorschläge verworfen.");
    }));
    this._el("report").addEventListener("click", () => this._run(async () => {
      const result = await this._hass.callWS({ type: "landscape/download_report", kind: "assist", report: JSON.stringify(this._report, null, 2) });
      this._download(result.filename, result.download_url);
    }));
  }

  _el(id) { return this.shadowRoot.getElementById(id); }

  async _switchMode(configuration) {
    if (configuration && !customElements.get("landscape-configuration-panel")) {
      try { await import("/landscape_static/configuration-panel.js?v=0.3.4"); }
      catch (error) { this._show("YAML-Dateien konnten nicht geladen werden: " + error.message, true); return; }
    }
    this._el("assist-main").hidden = configuration;
    this._el("configuration").hidden = !configuration;
    this._el("assist-tab").setAttribute("aria-pressed", String(!configuration));
    this._el("config-tab").setAttribute("aria-pressed", String(configuration));
    if (configuration) {
      this._configurationLoaded = true;
      this._el("configuration").hass = this._hass;
      this._el("configuration").panel = this._panel;
    }
  }

  _maybeLoad() {
    if (!this._built || !this._hass || !this._panel || this._loaded) return;
    this._loaded = true;
    this._run(async () => {
      const result = await this._call("status");
      if (result.exports.length) {
        this._el("export-info").textContent =
          "Letzter Export: " + new Date(result.exports[0].exported_at).toLocaleString("de-DE") +
          ". Die letzten drei Exporte sind importierbar.";
      }
      if (result.report) this._showReport(result.report);
    });
  }

  _call(action, fields = {}) {
    return this._hass.callWS({
      type: "landscape/assist", entry_id: this._panel.config.entry_id, action, ...fields,
    });
  }

  async _run(task) {
    if (this._busy) return;
    this._busy = true;
    this._setBusy();
    try {
      await task();
    } catch (error) {
      this._show(error.message || String(error), true);
    } finally {
      this._busy = false;
      this._setBusy();
    }
  }

  _setBusy() {
    this.shadowRoot.querySelectorAll("button,input").forEach((element) => {
      if (element.id !== "menu" && element.id !== "search") element.disabled = this._busy;
    });
    if (this._preview) {
      this._el("apply").disabled = this._busy || !this._selected.size;
      this._el("apply-all").disabled = this._busy || !this._ready().length;
      this._el("rows").querySelectorAll("input").forEach((input) => {
        input.disabled = this._busy || input.dataset.ready !== "true";
      });
    }
  }

  _show(message, error = false) {
    const box = this._el("message");
    box.hidden = false;
    box.textContent = message;
    box.classList.toggle("conflict", error);
  }

  _ready() {
    return this._preview.operations.filter((item) => item.status === "ready");
  }

  async _loadPreview() {
    if (!this._raw) return;
    this._clearPreview();
    this._preview = await this._call("preview", { patch: this._raw });
    this._selected = new Set(this._ready().filter((item) => item.field !== "floor_id").map((item) => item.id));
    this._el("preview").hidden = false;
    this._el("search").value = "";
    const operations = this._preview.operations;
    const conflicts = operations.filter((item) => item.status === "conflict").length;
    const unchanged = operations.filter((item) => item.status === "unchanged").length;
    this._el("summary").textContent = this._ready().length + " übernehmbare Änderungen, " +
      conflicts + " Konflikte, " + unchanged + " bereits erfüllt. Export: " +
      new Date(this._preview.exported_at).toLocaleString("de-DE");
    this._buildFilters();
    this._renderRows();
    this._show(operations.length ? "Datei geprüft. Wähle die gewünschten Änderungen aus." : "Der Patch enthält keine Änderungen.");
  }

  _buildFilters() {
    const container = this._el("filters");
    container.replaceChildren();
    const labels = { name: "Namen", aliases: "Aliase", assist: "Assist-Freigaben", area_id: "Bereiche", floor_id: "Etagen" };
    for (const [field, text] of Object.entries(labels)) {
      const relevant = this._ready().filter((item) => item.field === field);
      if (!relevant.length) continue;
      const label = document.createElement("label");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.dataset.field = field;
      checkbox.checked = relevant.every((item) => this._selected.has(item.id));
      checkbox.addEventListener("change", () => {
        relevant.forEach((item) => checkbox.checked ? this._selected.add(item.id) : this._selected.delete(item.id));
        this._renderRows();
      });
      label.append(checkbox, document.createTextNode(text));
      container.append(label);
    }
  }

  _syncSelection() {
    this._el("selection").textContent = this._selected.size + " ausgewählt (einschließlich ausgeblendeter Suchtreffer).";
    this._el("apply").textContent = "Ausgewählte übernehmen (" + this._selected.size + ")";
    this._el("apply-all").textContent = "Alle " + this._ready().length + " übernehmen";
    this._el("filters").querySelectorAll("input").forEach((checkbox) => {
      const relevant = this._ready().filter((item) => item.field === checkbox.dataset.field);
      const count = relevant.filter((item) => this._selected.has(item.id)).length;
      checkbox.checked = count === relevant.length;
      checkbox.indeterminate = count > 0 && count < relevant.length;
    });
    this._setBusy();
  }

  _renderRows() {
    if (!this._preview) return;
    const body = this._el("rows");
    body.replaceChildren();
    const query = this._el("search").value.toLocaleLowerCase("de-DE");
    const fields = { name: "Name", aliases: "Alias", assist: "Assist-Freigabe", area_id: "Bereich", floor_id: "Etage des Bereichs" };
    const fragment = document.createDocumentFragment();
    for (const item of this._preview.operations) {
      if (query && ![item.target, item.label, item.reason, item.alias, item.after, item.display_after]
        .join(" ").toLocaleLowerCase("de-DE").includes(query)) continue;
      const row = document.createElement("tr");
      row.className = item.status;
      const choose = document.createElement("td");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.dataset.ready = String(item.status === "ready");
      checkbox.checked = this._selected.has(item.id);
      checkbox.setAttribute("aria-label", item.label + ": " + fields[item.field] + (item.alias ? " " + item.alias : ""));
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) this._selected.add(item.id); else this._selected.delete(item.id);
        this._syncSelection();
      });
      choose.append(checkbox);
      row.append(choose);
      const target = this._cell(item.label);
      const identifier = document.createElement("small");
      identifier.className = "muted";
      identifier.textContent = item.target;
      target.append(identifier);
      row.append(target, this._cell(fields[item.field]));
      let before = item.current;
      let after = item.after;
      if (item.field === "aliases") {
        before = item.current ? item.alias : "Nicht vorhanden";
        after = item.after ? "+ " + item.alias : "− " + item.alias;
      } else if (item.field === "assist") {
        before = item.current ? "Exponiert" : "Nicht exponiert";
        after = item.after ? "Exponieren" : "Nicht exponieren";
      } else {
        if (item.current === item.before && "display_before" in item) before = item.display_before;
        if ("display_after" in item) after = item.display_after;
        if (before === null) before = "HA-Standard";
        if (after === null) after = "HA-Standard";
      }
      row.append(this._cell(String(before)), this._cell(String(after)));
      const reason = this._cell(item.reason);
      reason.className = "reason";
      const status = document.createElement("small");
      status.textContent = item.conflict || (item.status === "unchanged" ? "Bereits erfüllt" : "Übernehmbar");
      reason.append(status);
      if (item.affected_entity_ids) {
        const details = document.createElement("details");
        const summary = document.createElement("summary");
        summary.textContent = "Ganzer Bereich: " + item.affected_entity_ids.length + " Entitäten betroffen";
        const list = document.createElement("p");
        list.textContent = item.affected_entity_ids.join(", ");
        details.append(summary, list);
        if (item.additional_entity_ids && item.additional_entity_ids.length) {
          const additional = document.createElement("p");
          additional.textContent = "Zusätzlich bei Übernahme der Bereichsvorschläge: " + item.additional_entity_ids.join(", ");
          details.append(additional);
        }
        reason.append(details);
      }
      row.append(reason);
      const labels = ["Auswahl", "Entität / Bereich", "Änderung", "Aktuell", "Vorschlag", "Begründung / Status"];
      Array.from(row.cells).forEach((cell, index) => { cell.dataset.label = labels[index]; });
      fragment.append(row);
    }
    body.append(fragment);
    this._syncSelection();
  }

  _cell(text) {
    const cell = document.createElement("td");
    cell.textContent = text;
    return cell;
  }

  async _apply(all) {
    const selected = all ? this._ready().map((item) => item.id) : [...this._selected];
    const report = await this._call("apply", { preview_id: this._preview.preview_id, selected });
    this._clearPreview();
    this._showReport(report);
  }

  _clearPreview() {
    this._preview = null;
    this._selected.clear();
    this._el("preview").hidden = true;
  }

  _showReport(report) {
    this._report = report;
    this._el("report-section").hidden = false;
    const messages = {
      applied: report.applied_count + " Änderungen übernommen.",
      unchanged: "Die ausgewählten Einstellungen waren bereits erfüllt.",
      rolled_back: "Übernahme abgebrochen. Bereits begonnene Änderungen wurden zurückgesetzt.",
      partial: "Übernahme fehlgeschlagen. Einige Änderungen konnten nicht zurückgesetzt werden. Bitte das Protokoll prüfen.",
      pending: "Die letzte Übernahme wurde unterbrochen. Das Protokoll enthält die geplanten Änderungen; bitte die aktuellen Einstellungen prüfen.",
    };
    let text = messages[report.status] || report.status;
    if (report.error) text += " " + report.error;
    if (report.persistence_error) text += " " + report.persistence_error;
    this._el("report-info").textContent = text;
    this._show(text, !["applied", "unchanged"].includes(report.status) || !!report.persistence_error);
  }

  _download(filename, url) {
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.target = "_blank";
    link.rel = "noopener";
    document.body.append(link);
    link.click();
    link.remove();
  }
}

if (!customElements.get("landscape-assist-panel")) {
  customElements.define("landscape-assist-panel", LandscapeAssistPanel);
}
