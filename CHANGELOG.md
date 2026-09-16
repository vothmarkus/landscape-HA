# Änderungen

## 0.3.3

- Die Bereiche heißen jetzt „Entitäten“ und „YAML-Dateien“.
- Entitäten-Export und Import der Änderungen klar benannt; die YAML-Abschnitte
  heißen einheitlich „YAML exportieren“ und „YAML importieren“.
- Upload im separat geöffneten KI-Chat und Rückimport in Landscape ausdrücklich
  unterschieden; missverständliches „hier“ aus den Oberflächentexten entfernt.
- Hinweise auf API-Anbindung und lokale KI aus Oberfläche, Einrichtung und
  aktueller Anleitung entfernt.
- README an die neuen Bereichsnamen angepasst. Funktionen und Austauschformate
  bleiben unverändert.

## 0.3.2

- Export und Import in den Überschriften und Erklärungstexten beider Arbeitsbereiche
  sichtbar gemacht; Configuration beginnt jetzt mit „YAML exportieren“.
- README auf den teilautomatisierten Dateiaustausch mit KI-Chats ausgerichtet:
  exportieren, im Chat bearbeiten, importieren, prüfen und übernehmen.
- Dateiformate, Kontextdateien und konkrete Abläufe für einzelne YAML-Dateien,
  Dateiauswahlen, neue Packages und Assist-Optimierungen erklärt.
- Einrichtungsbeschreibungen auf Deutsch und Englisch um Assist und Configuration
  ergänzt; die CSV-Bestandsaufnahme als ergänzenden Export eingeordnet.
- Dokumentation von CSV-Maskierung, Vorschaugültigkeit, Inventargrenzen und
  Rückgabeformaten an das tatsächliche Verhalten angeglichen.
- Funktionsumfang, Dateiformate und Import-/Exportlogik bleiben unverändert.

## 0.3.1

- Zusätzliches Dropdown mit allen vorhandenen YAML-Zieldateien beim Import.
- Automatische Vorauswahl nach dem passendsten Dateinamen, auch mit Zusätzen wie
  `configuration_blitzer_korrigiert.yaml` oder `gasmeter_neu.yaml`.
- Passende Namen stehen zuerst; gleich gute Treffer erfordern eine eigene Auswahl.
- Zielpfad, Importart und verfügbare Zusammenführung folgen der Zielauswahl.
- Explizite Ziele, Kontext-Prüfsummen und ZIP-Pfade behalten Vorrang; Zieländerungen
  erfordern weiterhin eine neue Diff-Prüfung.

## 0.3.0

- Gemeinsames Landscape-Panel mit den Bereichen Assist und Configuration.
- YAML-Dateibaum mit Ansicht, Suche und Export als Einzeldatei, Auswahl oder Bundle.
- Optionaler Kontext mit Include-Rolle, Referenzen und Original-Prüfsumme.
- Import mit überprüfbarem Zielpfad, Dateiauswahl und vollständigem Diff.
- Ersetzen, neu anlegen und Zusammenführen per Automation-/Szenen-ID oder Skriptschlüssel.
- Unterstützung verschachtelter Includes und Packages; Prüfung der Containerform.
- Native HA-Prüfung plus strikte Automation-/Skriptprüfung; Rücksetzung bei neuen Problemen.
- Private Originalbackups, Journal, Konfliktprüfung und Rücksetzung mit Vorschau.
- Wiederherstellung unterbrochener Importe; Schutz vor Browserabbrüchen.
- YAML-Tags und Kommentare beim Export erhalten; keine Geheimnisauflösung.
- Bestehende Assist- und CSV-Funktionen bleiben verfügbar.

## 0.2.0

- Offline-Optimierung für Home Assistant Assist mit ZIP-Export und JSON-Patch.
- Eigene Administrator-Oberfläche für Import, Diff und selektive Übernahme.
- Namen, explizite Aliase, Bereichszuordnung und Assist-Freigabe ändern.
- Etagenzuordnung je Bereich mit vollständiger Anzeige der betroffenen Entitäten.
- Strikte Validierung und Prüfung gegen gespeicherte Exportstände.
- Bestehende Entity-IDs und automatische HA-Aliase erhalten.
- Ergebnisprotokoll und Rücksetzversuch bei fehlgeschlagenen Schreiboperationen.
- Assist-Downloads über die angemeldete Sitzung; CSV-Export weiterhin verfügbar.

## 0.1.1

- Vollständige CSV-Bestandsaufnahme, Downloadlink und Löschen des Exports.
