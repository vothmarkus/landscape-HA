/* File navigation extends the same reviewed import workflow as the YAML tab. */
class LandscapeBrowserPanel extends customElements.get("landscape-configuration-panel") {
  constructor() {
    super();
    this._scope = "browser"; this._directory = ""; this._directories = []; this._backups = [];
  }
  _build() {
    super._build();
    const main = this.shadowRoot.querySelector("main");
    const style = document.createElement("style");
    style.textContent = 'p,h2{overflow-wrap:anywhere}#folder-path{min-width:0;max-width:100%;flex:1 1 220px}#breadcrumbs button{min-width:0;overflow-wrap:anywhere}@media(max-width:700px){.file .actions{width:calc(100% - 28px)}.actions label{min-width:0;max-width:100%}}';
    this.shadowRoot.append(style);
    main.querySelector("p").textContent = "Dateien unter /config durchsuchen, exportieren und nach einer Diff-Prüfung importieren. Text- und Binärdateien werden unterstützt.";
    const sections = main.querySelectorAll(":scope > section");
    sections[0].querySelector("h2").textContent = "Dateibrowser";
    const paragraphs = sections[0].querySelectorAll("p");
    paragraphs[0].textContent = "Ordner öffnen, Dateien suchen und einzeln, als Auswahl oder als Ordner-Bundle exportieren. Mit Kontext enthält das ZIP die ursprünglichen Pfade und Prüfsummen.";
    paragraphs[1].textContent = "secrets.yaml/.yml, versteckte Dateien und Verzeichnisse, Laufzeitdatenbanken, Logs, Backups und Abhängigkeitsordner sind geschützt. Inhalte werden nicht geschwärzt. Grenze: 1 MB je Datei, 2 MB und 250 Dateien je Transfer.";
    this._el("search").placeholder = "In diesem Ordner und Unterordnern nach Pfad oder Typ suchen";
    this._el("search").setAttribute("aria-label", "Dateien suchen");
    this._el("export-all").textContent = "Ordner-Bundle exportieren";
    this._el("all").textContent = "Treffer auswählen";
    this._el("all").onclick = () => {
      for (const file of this._matchingFiles(true).filter(file => file.available)) this._selected.add(file.path);
      this._renderTree();
    };
    const navigation = document.createElement("nav"); navigation.id = "breadcrumbs"; navigation.className = "actions";
    navigation.setAttribute("aria-label", "Ordnerpfad");
    this._el("search").before(navigation);
    const jump = document.createElement("div"); jump.className = "actions";
    const path = document.createElement("input"); path.type = "text"; path.id = "folder-path"; path.placeholder = "z. B. www/community";
    path.setAttribute("aria-label", "Ordner unter /config öffnen");
    const open = () => {
      const value = path.value.replace(/^\/config(?:\/|$)/, "").replace(/^\/+|\/+$/g, "");
      if (value && !this._directories.includes(value)) { this._show("Ordner nicht gefunden: " + value, true); return; }
      this._openDirectory(value);
    };
    path.onkeydown = event => { if (event.key === "Enter") open(); };
    jump.append(path, this._button("Pfad öffnen", open)); navigation.after(jump);
    sections[2].querySelector("h2").textContent = "Dateien importieren";
    sections[2].querySelector("p").textContent = "Überarbeitete oder neue Dateien auswählen. Bei Einzeldateien dient der geöffnete Ordner als Ziel; ZIP-Bundles behalten ihre Pfade ab /config. Ziel und Importart anschließend im Diff prüfen.";
    const unpack = document.createElement("label"); unpack.className = "actions";
    const checkbox = document.createElement("input"); checkbox.type = "checkbox"; checkbox.id = "unpack"; checkbox.checked = true;
    unpack.append(checkbox, document.createTextNode("ZIP als Dateibundle entpacken (für eine ZIP-Datei als Datei abwählen)"));
    this._el("upload").before(unpack);
    this._el("preview").querySelector(".muted").textContent = "JSON, Python und YAML werden auf Syntax geprüft; HA-YAML zusätzlich auf seine Einbindung. Für andere Dateitypen gibt es keine Inhaltsprüfung. Beim Übernehmen folgen Backup und HA-Konfigurationsprüfung; neue HA-Probleme führen zur Rücksetzung. JavaScript oder Integrationscode werden durch die HA-Prüfung nicht vollständig getestet.";
    const history = sections[sections.length - 1]; history.id = "history";
    history.querySelector("h2").textContent = "Historie und Backups";
    history.querySelector("p").textContent = "Hier erscheinen über Landscape übernommene Browser-Importe. „Historie“ an einer Datei filtert ihre Änderungen. Eine Rücksetzung betrifft jeweils den gesamten angezeigten Import und wird zuerst als Diff geprüft.";
    const filter = document.createElement("p"); filter.id = "history-filter";
    const clear = this._button("Gesamte Historie", () => { this._historyPath = null; this._renderBackups(this._backups); });
    this._el("backups").before(filter, clear);
  }
  async _refresh() {
    const result = await this._call("list");
    this._files = result.files; this._directories = result.directories || [];
    if (this._directory && !this._directories.includes(this._directory)) this._directory = "";
    this._selected = new Set([...this._selected].filter(path => this._files.some(file => file.path === path && file.available)));
    this._renderTree(); this._renderImports(); this._renderBackups(result.backups || []);
  }
  _openDirectory(path) {
    if (this._busy) return;
    this._directory = path; this._el("search").value = ""; this._renderTree();
  }
  _matchingFiles(recursive = false) {
    const prefix = this._directory ? this._directory + "/" : "";
    const query = this._el("search").value.trim().toLocaleLowerCase("de-DE");
    return this._files.filter(file => file.path.startsWith(prefix) &&
      (query ? (file.path + " " + file.type).toLocaleLowerCase("de-DE").includes(query) : recursive || !file.path.slice(prefix.length).includes("/")));
  }
  _renderTree() {
    const root = this._el("tree"); root.replaceChildren();
    const crumbs = this._el("breadcrumbs"); crumbs.replaceChildren(this._button("/config", () => this._openDirectory("")));
    let current = "";
    for (const part of this._directory.split("/").filter(Boolean)) {
      current += (current ? "/" : "") + part; const path = current;
      crumbs.append(document.createTextNode(" / "), this._button(part, () => this._openDirectory(path)));
    }
    this._el("folder-path").value = this._directory;
    const prefix = this._directory ? this._directory + "/" : "";
    const query = this._el("search").value.trim();
    if (!query) for (const path of this._directories.filter(path => path.startsWith(prefix) && !path.slice(prefix.length).includes("/"))) {
      const row = document.createElement("div"); row.className = "file";
      const label = this._button("📁 " + path.slice(prefix.length), () => this._openDirectory(path));
      label.className = "file-name";
      const members = this._files.filter(file => file.available && file.path.startsWith(path + "/"));
      const select = this._button("Ordner auswählen", () => { for (const file of members) this._selected.add(file.path); this._renderTree(); });
      row.append(label, select); root.append(row);
    }
    const files = this._matchingFiles();
    for (const file of files) {
      const row = document.createElement("div"); row.className = "file";
      const choice = document.createElement("input"); choice.type = "checkbox"; choice.checked = this._selected.has(file.path);
      choice.dataset.available = String(file.available); choice.setAttribute("aria-label", file.path + " auswählen");
      choice.onchange = () => { if (choice.checked) this._selected.add(file.path); else this._selected.delete(file.path); this._count(); };
      const label = document.createElement("div"); label.className = "file-name";
      const title = document.createElement("strong"); title.textContent = "📄 " + (query ? file.path : file.path.slice(prefix.length));
      const meta = document.createElement("small"); meta.textContent = file.type + " · " + file.size.toLocaleString("de-DE") + " Bytes · " + new Date(file.modified_at).toLocaleString("de-DE") + (file.available ? "" : " · größer als 1 MB: kein Transfer");
      label.append(title, meta);
      const actions = document.createElement("div"); actions.className = "actions";
      if (file.available) actions.append(
        this._button("Anzeigen", () => this._run(() => this._view(file.path))),
        this._button("Exportieren", () => this._run(() => this._export([file.path]))),
        this._button("Import / Diff", () => { this._target = file.path; this._el("target-hint").textContent = "Zieldatei: /config/" + file.path; this._el("upload").value = ""; this._el("upload").click(); }),
      );
      actions.append(this._button("Historie", () => { this._historyPath = file.path; this._renderBackups(this._backups); this._el("history").scrollIntoView({ block: "start", behavior: "smooth" }); }));
      row.append(choice, label, actions); root.append(row);
    }
    if (!root.childElementCount) root.textContent = query ? "Keine passenden Dateien gefunden." : "Dieser Ordner ist leer.";
    this._count();
  }
  _count() {
    this._el("count").textContent = this._files.length + " Dateien insgesamt · " + this._matchingFiles().length + " angezeigt · " + this._selected.size + " ausgewählt";
    this._setBusy();
  }
  _setBusy() {
    super._setBusy();
    this.shadowRoot.querySelectorAll('input[data-available="false"]').forEach(input => { input.disabled = true; });
  }
  async _view(path) {
    const file = await this._call("view", { path });
    this._el("viewer").hidden = false; this._el("view-title").textContent = "/config/" + path;
    this._el("view-info").textContent = file.type + " · " + file.size + " Bytes · SHA-256: " + file.sha256;
    this._el("view-content").textContent = file.binary ? "Binärdatei. Zum Anzeigen exportieren; Import / Diff vergleicht Größe und Prüfsummen." : file.content;
    this._el("viewer").scrollIntoView({ block: "start", behavior: "smooth" });
  }
  async _export(paths) {
    const bundle = paths === null;
    if (paths === null && this._directory) paths = this._files.filter(file => file.available && file.path.startsWith(this._directory + "/")).map(file => file.path);
    await super._export(paths, bundle);
  }
  async _upload(files) {
    if (!files.length) return;
    this._clearPreview(); this._imports = []; this._renderImports();
    const target = this._target; this._target = null; this._el("target-hint").textContent = "";
    if (target && files.length !== 1) throw new Error("Für eine bestimmte Zieldatei bitte genau eine Datei auswählen.");
    if (files.reduce((sum, file) => sum + file.size, 0) > 2000000) throw new Error("Import darf höchstens 2 MB groß sein.");
    const encoded = async file => {
      const bytes = new Uint8Array(await file.arrayBuffer()); let binary = "";
      for (let start = 0; start < bytes.length; start += 8192) binary += String.fromCharCode(...bytes.subarray(start, start + 8192));
      return btoa(binary);
    };
    const zip = files.find(file => file.name.toLowerCase().endsWith(".zip"));
    let fields;
    if (zip && this._el("unpack").checked && !target) {
      if (files.length !== 1) throw new Error("Bitte ein ZIP-Bundle allein auswählen.");
      fields = { archive: await encoded(zip) };
    } else {
      if (files.some(file => file.size > 1000000)) throw new Error("Eine Datei darf höchstens 1 MB groß sein.");
      fields = { files: await Promise.all(files.map(async file => ({ filename: target || (this._directory ? this._directory + "/" : "") + file.name, content: await encoded(file), encoding: "base64" }))) };
    }
    const result = await this._call("inspect", fields);
    if (target) { result.files[0].path = target; result.files[0].mode = "replace"; result.files[0].suggested_path = null; }
    this._imports = result.files.map(file => ({ ...file, selected: true }));
    this._renderImports(); this._show("Importziel und Importart prüfen, dann den Diff öffnen.");
  }
  _renderBackups(backups) {
    this._backups = backups;
    this._el("history-filter").textContent = this._historyPath ? "Datei: /config/" + this._historyPath : "Alle Browser-Importe";
    super._renderBackups(this._historyPath ? backups.filter(backup => backup.files.some(file => file.path === this._historyPath)) : backups);
  }
}
customElements.define("landscape-browser-panel", LandscapeBrowserPanel);
