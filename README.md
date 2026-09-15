<p align="center">
  <img src="custom_components/landscape/brand/icon@2x.png" alt="HA Landscape" width="160">
</p>

# HA Landscape

HA Landscape erstellt auf Knopfdruck eine vollständige CSV-Bestandsaufnahme
der Entitäten einer Home-Assistant-Installation. Die Datei eignet sich unter
anderem dazu, einem KI-Assistenten den vorhandenen Aufbau für die Erstellung
passender Automatisierungen zu übergeben.
Zusätzlich lassen sich Namen, Aliase und Assist-Freigaben über einen geprüften
Dateiaustausch mit ChatGPT optimieren und gezielt übernehmen.
Ab Version **0.3.0** verwaltet der Bereich **Configuration** außerdem einzelne
YAML-Dateien, Dateiauswahlen und Configuration-Bundles mit Importvorschau,
Home-Assistant-Prüfung und Backups.

## Funktionen

- erfasst aktive, nicht verfügbare, deaktivierte und aktuell zustandslose
  Registry-Entitäten
- exportiert Zustand, Attribute, Geräte-, Bereichs-, Integrations- und
  Registry-Informationen
- enthält technische IDs, Anzeigenamen und Labels
- maskiert im CSV Tokens, Passwörter, API-Schlüssel und ähnliche Zugangsdaten
- erzeugt Excel-taugliches UTF-8-CSV mit Semikolon als Trennzeichen
- ersetzt bei jedem Export die vorherige Datei vollständig
- bietet einen eigenen Löschknopf für die veröffentlichte Datei
- lässt sich über die Oberfläche einrichten; kein YAML nötig

## Configuration: YAML exportieren und importieren (ab 0.3.0)

**HA Landscape → Configuration** öffnet den durchsuchbaren YAML-Dateibaum.
Alle Dateiaktionen sind ausschließlich für angemeldete HA-Administratoren verfügbar.

### Export

- **Einzeldatei:** An einer Datei **Exportieren** anklicken. Ohne Kontext entsteht
  direkt eine `.yaml`/`.yml`, standardmäßig mit unverändertem Dateinamen. Optional
  wird das Datum ergänzt, beispielsweise `automations_2026-09-15.yaml`.
- **Dateiauswahl:** Gewünschte Dateien anhaken und **Auswahl exportieren** wählen.
  Mehrere Dateien werden als ZIP mit ihren relativen Pfaden heruntergeladen.
- **Komplett-Bundle:** Alle zugänglichen YAML-Dateien des Configuration-Bereichs
  exportieren, einschließlich noch nicht eingebundener eigener YAML-Dateien.
- **Mit Kontext:** ZIP mit YAML und je einer `.landscape.json`. Die Begleitdatei
  enthält Zielpfad, erkannte Rolle, Includes, übergeordnete Einbindung, textuell
  gefundene Entitäts-/Aktionsreferenzen und die SHA-256-Prüfsumme des Originals.
  Dynamisch erzeugte Referenzen in Templates können unvollständig sein.

`!secret`, `!env_var`, Kommentare und vorhandene Zeilenenden bleiben beim Export
erhalten. **YAML wird nicht automatisch geschwärzt:** Direkt eingetragene Passwörter
bleiben enthalten. `secrets.yaml`/`secrets.yml`, versteckte Verzeichnisse, `.storage`,
`www`, `custom_components`, `deps`, `esphome`, `blueprints`, `tts`, Backup- und
Programmverzeichnisse werden nicht angeboten. Das Bundle ist ein YAML-Arbeitsstand,
kein vollständiges Home-Assistant-Systembackup.

### Import und Diff

1. Bei einer vorhandenen Datei **Import / Diff** anklicken, oder unten eine oder
   mehrere YAML-Dateien, passende Kontextdateien oder ein Configuration-ZIP wählen.
2. Im Dropdown **Vorhandene Zieldatei** das Ziel und darunter die Importart prüfen.
   Ab **0.3.1** wählt Landscape anhand des passendsten Dateinamens vor: etwa
   `configuration_blitzer_korrigiert.yaml` → `configuration.yaml` oder
   `gasmeter_neu.yaml` → `packages/gasmeter.yaml`. Ein Umbenennen vor dem Upload
   ist nicht erforderlich. Alle vorhandenen YAML-Zielpfade bleiben auswählbar;
   passende Namen stehen oben. Für neue Dateien den relativen Pfad unter `/config`
   eingeben und **Als neue Datei importieren** wählen.
3. Dateien für den Import auswählen und **Prüfen und Diff anzeigen** anklicken.
4. Vollständige Diffs, Zeilenzahlen und Dateikontext prüfen; erst danach
   **Änderungen übernehmen** wählen. Eine Änderung der Auswahl oder Ziele macht
   die Vorschau ungültig und erfordert eine neue Prüfung.

Die Vorauswahl bevorzugt identische Dateinamen, anschließend den längsten
passenden Namen aus vollständigen Namensbestandteilen. Groß-/Kleinschreibung,
Unterstriche, Bindestriche, Leerzeichen und Zusätze wie Datum oder „korrigiert“
stehen der Erkennung nicht im Weg. `gas` allein passt dabei nicht auf `gasmeter`.
Bei gleich guten Treffern, beispielsweise gleichnamigen Dateien in zwei Ordnern,
bleibt das Ziel leer und muss im Dropdown gewählt werden. Ein explizit über
**Import / Diff** gewähltes Ziel, passende Kontextdateien und ZIP-Pfade haben
Vorrang vor der Namensvermutung. Die Vorauswahl ändert noch keine Datei.

| Importart | Verhalten |
| --- | --- |
| Datei ersetzen | Bestehende Datei vollständig durch den hochgeladenen Inhalt ersetzen. |
| Als neue Datei importieren | Datei am gewählten relativen Pfad anlegen; vorhandene Dateien werden abgelehnt. |
| Einträge zusammenführen | Automation-/Szenenlisten über eindeutige `id`, Skript-Zuordnungen über ihre Schlüssel zusammenführen. |

Zusammenführen ersetzt passende **ganze Einträge**, ergänzt neue und erhält die
übrigen Einträge. Es ist kein rekursiver Feld-Merge. Kommentare innerhalb ersetzter
Einträge stammen aus dem Import. YAML-Anker, mehrdeutige IDs und ungeeignete
Strukturen werden abgelehnt. Für Packages wird dieser Modus nicht angeboten.

Neue Dateien werden nicht automatisch in `configuration.yaml` eingetragen.
Eine neue `.yaml` in einem bereits per `!include_dir_named` eingebundenen
Package-Verzeichnis gehört dagegen durch diese bestehende Einbindung dazu.
Die Rolle wird aus dem Include-Kontext ermittelt, nicht aus dem Dateinamen.
Verschachtelte Includes, Packages und die vier `!include_dir_*`-Varianten werden
berücksichtigt. Wie in HA gelten Verzeichnis-Includes nur für `.yaml`; `.yml`
kann direkt per `!include` eingebunden werden.

### Prüfung, Backups und Rücksetzung

- Die Vorschau prüft YAML-Syntax, doppelte Schlüssel, zulässige Tags/Pfade,
  Include-Ziele und erwartete Containerformen. `automations.yaml` als einzelnes
  Objekt wird bei einer Listeneinbindung bereits hier abgelehnt.
- Beim Übernehmen prüft Landscape den unveränderten Ausgangsstand erneut, sichert
  die betroffenen Originaldateien und ersetzt sie einzeln atomar. Anschließend
  läuft die native HA-Konfigurationsprüfung. Automationen und Skripte werden
  zusätzlich mit den Validatoren geprüft, die HA für das Bearbeiten verwendet;
  als deaktiviert zurückgegebene ungültige Einträge werden so nicht übersehen.
- Fehler und neue Prüfwarnungen führen zur Rücksetzung des gesamten Imports.
  Bereits vorhandene, unveränderte Warnungen erscheinen im Protokoll. Ein Import
  darf bestehende Fehler beheben, muss die anschließende Prüfung aber bestehen.
- Während der Prüfung wird HA nicht automatisch neu geladen. Erst nach einem
  erfolgreichen Ergebnis die passenden YAML-Bereiche neu laden oder HA neu starten.
  Eine Konfigurationsprüfung garantiert nicht das Verhalten realer Geräte.
- Bei Änderungen seit der Vorschau wird die Übernahme abgelehnt. Mit Kontextdatei
  erkennt Landscape zusätzlich Änderungen seit dem Export; einer nackten YAML
  fehlt diese Exportbasis. Beim Rücksetzen werden externe Änderungen nie blind
  überschrieben, sondern mit betroffenem Pfad als Konflikt gemeldet.
- Originaldateien und Journal liegen privat in
  `/config/.storage/landscape_configuration/<Backup-ID>/`. Die `.bin`-Dateien
  enthalten die unveränderten Originalbytes; `manifest.json` ordnet die Pfade zu.
  Im Abschnitt **Backups** lässt sich eine Rücksetzung zuerst prüfen und danach
  übernehmen. Dabei werden auch neu angelegte Dateien wieder entfernt.
- Unterbrochene Importe werden beim nächsten Laden von Landscape anhand des
  Journals zurückgesetzt. Browserabbrüche beenden eine laufende Transaktion nicht.
  Backups bleiben auch nach dem Entfernen der Integration erhalten.

Grenzen: 1 MB je YAML-Datei, 2 MB je Import/Export einschließlich Kontext und
entpacktem ZIP, bis zu 250 YAML-Dateien und 40 MB im Inventar. Größere Dateimengen
in kleineren Auswahlen bearbeiten. Die Oberfläche zeigt die letzten 20 Backups;
ältere Backups werden nicht automatisch gelöscht. Symlinks werden nicht verfolgt.

## Assist mit ChatGPT optimieren (ab 0.2.0)

In der Seitenleiste steht Administratoren **HA Landscape → Assist** zur Verfügung.

1. **Assist-ZIP herunterladen** anklicken.
2. ZIP in ChatGPT hochladen und **„Landscape Assist optimieren.“** schreiben.
3. Die erzeugte **assist_optimized.json** herunterladen und in Landscape auswählen.
4. Vorschau prüfen: jede Namensänderung, jeder Alias, jede Assist-Freigabe und
   jede Bereichs-/Etagenzuweisung hat eine eigene Checkbox.
5. **Ausgewählte übernehmen**, **Alle übernehmen** oder **Verwerfen** wählen.

Das ZIP enthält:

- **landscape.json**: Namen, Originalnamen, explizite Aliase, Gerät mit Hersteller
  und Modell, verwandte Geräteentitäten, Bereich, Etage, Assist-Freigabe,
  Aktivierungsstatus sowie ausgewählte technische Attribute und reduzierte Zustände.
- **optimization_schema.json**: das verbindliche Patch-Format.
- **CHATGPT_INSTRUCTIONS.md**: die vollständige deutsche Optimierungsanleitung.

Es werden keine KI-Dienste aus Home Assistant aufgerufen. Weder ein API-Schlüssel
noch Ollama oder ein lokales Modell wird benötigt.

### Vorschau und Übernahme

- Entity-IDs und Geräte-IDs sind unveränderlich. Unbekannte Felder und Ziele,
  doppelte JSON-Schlüssel, falsche Datentypen und falsche alte Werte werden abgelehnt.
- Namen werden als benutzerdefinierter Registry-Name gesetzt; `null` stellt
  den HA-Standard wieder her. Die Vorschau zeigt dazu den bisherigen Namen.
- Aliase können einzeln ergänzt oder entfernt werden. Automatisch erzeugte
  HA-Aliase und die nicht ausgewählten Einstellungen bleiben erhalten.
- Freigaben betreffen ausschließlich **Assist / conversation**.
- Bereiche werden über vorhandene Bereichs-IDs zugeordnet. `null` entfernt
  die explizite Entitätszuweisung, sodass der Gerätebereich geerbt wird.
- Eine Etage gehört in HA zum **Bereich**. Etagenänderungen zeigen deshalb alle
  betroffenen Entitäten und sind zunächst abgewählt. **Alle übernehmen** schließt
  ausdrücklich auch übernehmbare Etagenänderungen ein.
- Zustandsänderungen wie „an/aus“ machen den Patch nicht ungültig. Geänderte Namen,
  Aliase oder räumliche Zuordnungen werden dagegen vor dem Schreiben erneut
  geprüft. Eine Auswahl mit Konflikten führt zu keiner Übernahme.
- Ohne Registry-Eintrag kann nur die Assist-Freigabe geändert werden.
- Vor dem Schreiben wird ein Ergebnisprotokoll mit den alten und neuen Werten
  gespeichert. Bei einem Fehler während der Übernahme versucht Landscape,
  begonnene Änderungen zurückzusetzen. Fehler beim Zurücksetzen werden einzeln
  im Protokoll angezeigt. Dieses lässt sich als JSON herunterladen.
- Nach einem HA-Neustart sind die letzten **drei Exporte** weiterhin importierbar.
  Eine Vorschau ist für den jeweiligen Administrator eine Stunde gültig und
  wird nach einer Übernahme verbraucht. Bei Ablauf die Datei erneut prüfen.

Der neue Assist-Export wird über die angemeldete Administrator-Sitzung geladen
und **nicht** im öffentlichen `www`-Ordner abgelegt. Die Exportstände und das
letzte Ergebnisprotokoll bleiben in HA gespeichert, bis sie ersetzt oder die
Integration gelöscht wird. Der vorhandene CSV-Export funktioniert weiterhin.

### Patch-Beispiel

Die `source_id` und alten Werte müssen zum konkreten Export passen:

```json
{
  "schema_version": 1,
  "source_id": "ID_AUS_DEM_EXPORT",
  "changes": [
    {
      "entity_id": "light.schlafzimmer_decke",
      "name": {"old": "Decke", "new": "Deckenlicht"},
      "aliases": {"add": ["Deckenlampe", "Licht an der Decke"]},
      "assist": {"exposed": true},
      "reason": "Eindeutige Unterscheidung vom Ambientelicht."
    }
  ]
}
```

Freie Beschreibungen werden als **Begründung** im Patch geführt: HA besitzt
hierfür kein allgemeines beschreibbares Entitätsfeld. Abhängigkeitsanalyse und
Entity-ID-Umbenennungen sind nicht Bestandteil dieser Version.

## Installation mit HACS

1. In HACS **Integrationen** öffnen.
2. Über das Menü **Benutzerdefinierte Repositories** wählen.
3. `https://github.com/vothmarkus/landscape-HA` als Repository der Kategorie
   **Integration** hinzufügen.
4. **HA Landscape** herunterladen.
5. Home Assistant neu starten.
6. Unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** nach
   **HA Landscape** suchen und die Einrichtung bestätigen.

## Manuelle Installation

Den Ordner `custom_components/landscape` nach
`/config/custom_components/landscape` kopieren und Home Assistant neu starten.
Danach die Integration über **Einstellungen → Geräte & Dienste** hinzufügen.

## Verwendung

Nach der Einrichtung existieren drei Entitäten am Gerät **HA Landscape**:

- **CSV-Export erstellen** erstellt die aktuelle Datei.
- **CSV-Datei löschen** entfernt sie wieder.
- **Letzter CSV-Export** zeigt Zeitstempel, Anzahl, Dateigröße und Verfügbarkeit.

Der Export liegt auf dem Home-Assistant-System unter:

```text
/config/www/ha_entitaeten.csv
```

Er ist im Browser erreichbar unter:

```text
https://DEINE-HA-ADRESSE/local/ha_entitaeten.csv
```

Nach erfolgreichem Export erscheint zusätzlich eine Home-Assistant-Meldung mit
einem direkten Download-Link.

Am Gerät **HA Landscape** zeigt Home Assistant außerdem den anklickbaren Link
**Besuchen** an. Nach dem ersten Export führt er direkt zur CSV-Datei. Der
vollständige Link steht zusätzlich im Attribut `download_url` des Sensors
**Letzter CSV-Export** und wird in der Erfolgsmeldung verwendet. Die Integration
bevorzugt die unter **Einstellungen → System → Netzwerk** hinterlegte interne
Home-Assistant-URL. Soll beispielsweise `https://ha.home` verwendet werden,
muss diese Adresse dort als interne URL eingetragen sein.

> [!WARNING]
> Dateien in `/config/www` werden von Home Assistant ohne Anmeldung
> ausgeliefert. Jeder, der die genaue URL erreichen kann, kann die CSV laden.
> Die Datei sollte deshalb nach dem Herunterladen mit **CSV-Datei löschen**
> entfernt werden. Zugangsdaten werden zwar automatisch maskiert, Zustände,
> Geräte- und Bereichsnamen können dennoch private Informationen enthalten.

## Dienste

Zusätzlich zu den Schaltflächen stehen folgende Aktionen für Skripte und
Automatisierungen bereit:

```yaml
action: landscape.export_csv
```

```yaml
action: landscape.delete_csv
```

## Exportierte Spalten

Die CSV enthält unter anderem:

- `entity_id`, Anzeigename, Domain, Zustand und Verfügbarkeit
- Einheit, Geräteklasse, Zustandsklasse, Icon und unterstützte Funktionen
- Aktivierungs-, Deaktivierungs- und Ausblendungsstatus
- `unique_id`, Plattform, Integration, Konfigurationseintrag und deren IDs
- Gerät mit ID, Name, Hersteller, Modell, Versionen und Kennungen
- Entitäts-, Geräte- und effektiver Bereich mit ID und Name
- Entitäts- und Geräte-Labels jeweils als ID und Klarname
- Zeitpunkte der letzten Zustandsänderung und Aktualisierung
- sämtliche Zustandsattribute als JSON in `attributes_json`

## Datenschutz und Maskierung

Bekannte Zugangsdatenfelder wie `access_token`, `password`, `api_key`,
`secret` und `pin` werden rekursiv durch `<redacted>` ersetzt. Token-Parameter
in URLs werden ebenfalls maskiert. Die Filterung ersetzt keine Prüfung der
Datei vor der Weitergabe.

## Lizenz

[MIT](LICENSE)
