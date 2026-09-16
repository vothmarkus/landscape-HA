<p align="center">
  <img src="custom_components/landscape/brand/icon@2x.png" alt="HA Landscape" width="160">
</p>

# HA Landscape

**Die dateibasierte Verbindung zwischen Home Assistant und KI-Chats.**

HA Landscape schafft eine teilautomatisierte Schnittstelle zu KI-Chats wie
ChatGPT: Du exportierst den benötigten Bestand, lässt ihn im Chat analysieren
oder überarbeiten und importierst das Ergebnis zur Prüfung zurück.
Landscape bereitet die Daten auf, zeigt Änderungen an und übernimmt die von dir
freigegebenen Vorschläge. Den Dateitransfer zum Chat und die Freigabe steuerst du.

**Exportieren → im KI-Chat bearbeiten → importieren → prüfen → übernehmen.**

Dafür benötigt Landscape keine direkte LLM-API-Anbindung, keinen API-Schlüssel
eines KI-Anbieters und kein lokales Modell. Du verwendest den KI-Chat separat und
lädst die Dateien selbst hoch. Erst damit gibst du ihren Inhalt an den gewählten
Chat-Anbieter weiter. Der Chat muss die jeweiligen Dateien lesen und das
Rückgabeformat erzeugen können; Landscape bindet dich an keinen bestimmten Anbieter.

## Welcher Bereich passt zur Aufgabe?

| Bereich | Aufgabe | Export | Rückgabe an Landscape |
| --- | --- | --- | --- |
| [**Configuration**](#configuration-yaml-exportieren-und-importieren) | YAML prüfen, reparieren oder erweitern, etwa Automationen, Templates und Packages | Einzelne YAML, Dateiauswahl oder YAML-Bundle; optional mit Kontext | Vollständige YAML-Dateien oder Configuration-ZIP; Diff, Dateiübernahme, HA-Prüfung und Backups |
| [**Assist**](#assist-daten-exportieren-und-optimierungen-importieren) | Namen, Aliase, Assist-Freigaben und räumliche Zuordnungen verbessern | Assist-ZIP mit Bestand, Anleitung und JSON-Schema | `assist_optimized.json`; einzelne Vorschläge prüfen und in HA übernehmen |
| [**CSV-Bestand**](#csv-bestand-exportieren) | Entitäten und Geräte analysieren oder zusätzlichen Kontext für den Chat liefern | `ha_entitaeten.csv` | Analyse im Chat; für CSV gibt es keinen Rückimport |

Die beiden Arbeitsbereiche **Assist** und **Configuration** stehen nach der
[Einrichtung](#installation-mit-hacs) Administratoren in der Seitenleiste unter
**HA Landscape** zur Verfügung. Den ergänzenden CSV-Export findest du an den
Entitäten des Geräts **HA Landscape**.

## So läuft die Zusammenarbeit mit dem KI-Chat ab

1. Den passenden Bereich wählen und die für die Aufgabe benötigten Daten
   exportieren. Für eine einzelne YAML-Korrektur reicht häufig eine Datei mit Kontext.
2. Den Export im KI-Chat hochladen und die gewünschte Änderung oder den Fehler
   beschreiben. Fehlermeldungen und das gewünschte Verhalten helfen bei der Analyse.
3. Das Ergebnis als Datei herunterladen: vollständige YAML für **Datei ersetzen**
   oder den JSON-Patch für **Assist**. Eine reine Erklärung oder ein Diff ist keine
   importierbare Ersatzdatei.
4. Das Ergebnis im zugehörigen Landscape-Bereich importieren, Ziel und Vorschau
   prüfen und die gewünschten Änderungen freigeben.
5. Nach einer erfolgreichen YAML-Übernahme die betroffenen Bereiche in HA neu
   laden oder HA neu starten. Assist-Änderungen schreibt Landscape direkt in die
   entsprechenden HA-Einstellungen.

Die Analyse findet im gewählten KI-Chat statt. Landscape prüft Dateiformate,
Ausgangsstände und die jeweils unterstützten Änderungen lokal in Home Assistant.
Die inhaltliche Entscheidung, welche Vorschläge sinnvoll sind, bleibt bei dir.

## Configuration: YAML exportieren und importieren

**HA Landscape → Configuration** öffnet den durchsuchbaren YAML-Dateibaum.
Alle Dateiaktionen sind ausschließlich für angemeldete HA-Administratoren verfügbar.

### Export

- **Einzeldatei:** An einer Datei **Exportieren** anklicken. Ohne Kontext entsteht
  direkt eine `.yaml`/`.yml`, standardmäßig mit unverändertem Dateinamen. Optional
  wird das Datum ergänzt, beispielsweise `automations_2026-09-15.yaml`.
- **Dateiauswahl:** Gewünschte Dateien anhaken und **Auswahl exportieren** wählen.
  Mehrere Dateien werden als ZIP mit ihren relativen Pfaden heruntergeladen.
- **Komplett-Bundle exportieren:** Alle zugänglichen YAML-Dateien des
  Configuration-Bereichs exportieren, einschließlich noch nicht eingebundener
  eigener YAML-Dateien.
- **Mit Kontext:** ZIP mit YAML und je einer `.landscape.json`. Die Begleitdatei
  enthält Zielpfad, erkannte Rolle, Includes, übergeordnete Einbindung, textuell
  gefundene Entitäts-/Aktionsreferenzen und die SHA-256-Prüfsumme des Originals.
  Dynamisch erzeugte Referenzen in Templates können unvollständig sein.

**Mit Kontext** gilt auch beim Export einer einzelnen Datei: Du erhältst ein ZIP
mit der YAML und ihrer Begleitdatei, beispielsweise `gasmeter.yaml` und
`gasmeter.landscape.json`. Beim Rückimport die originale Begleitdatei unverändert
mitgeben, damit Landscape Änderungen am Ausgangsstand seit dem Export erkennen
kann. Sie ist optional; eine einzelne YAML lässt sich auch ohne Kontext importieren.
Der Kontext enthält Referenzen und Einbindungen, aber weder die Inhalte aller
referenzierten Dateien noch einen vollständigen Entitätsbestand oder Live-Zustände.

`!secret`, `!env_var`, Kommentare und vorhandene Zeilenenden bleiben beim Export
erhalten. **YAML wird nicht automatisch geschwärzt:** Direkt eingetragene Passwörter
bleiben enthalten. `secrets.yaml`/`secrets.yml`, versteckte Verzeichnisse, `.storage`,
`www`, `custom_components`, `deps`, `esphome`, `blueprints`, `tts`, Backup- und
Programmverzeichnisse werden nicht angeboten. Das Bundle ist ein YAML-Arbeitsstand,
kein vollständiges Home-Assistant-Systembackup.

### Typische Arbeitsabläufe im KI-Chat

**Eine bestehende Datei korrigieren:** An `automations.yaml` **Exportieren**
wählen, bei Bedarf zuvor **Mit Kontext** aktivieren. Datei oder ZIP im Chat
hochladen und zum Beispiel diesen Auftrag ergänzen:

```text
Prüfe in automations.yaml die Automatisierung für den Gaszähler.
Fehlermeldung und gewünschtes Verhalten: [hier beschreiben].
Verwende den mitgelieferten Kontext und frage nach fehlenden Informationen.
Gib die vollständige überarbeitete YAML-Datei zum Herunterladen zurück.
Erhalte bestehende Entity-IDs, Automations-IDs, !include-/!secret-Verweise
und nicht betroffene Abschnitte. Verändere die .landscape.json-Begleitdatei nicht.
Erkläre die vorgenommenen Änderungen zusätzlich kurz.
```

Die Rückgabe unter **YAML importieren und prüfen** auswählen und **Datei ersetzen**
verwenden. Zusätze im Dateinamen sind erlaubt: Landscape kann etwa
`configuration_blitzer_korrigiert.yaml` der vorhandenen `configuration.yaml`
zuordnen. Ziel und vollständigen Diff vor der Übernahme prüfen.

**Mehrere zusammenhängende Dateien überarbeiten:** Beispielsweise
`configuration.yaml`, `templates.yaml` und `automations.yaml` gemeinsam anhaken
und **Auswahl exportieren** wählen. Im Chat für jede geänderte Datei den
vollständigen Inhalt und die Beibehaltung der relativen Pfade verlangen.
Die Rückgabe kann aus mehreren YAML-Dateien oder einem ZIP bestehen. In Landscape
die gewünschten Dateien für eine gemeinsame Vorschau und Übernahme auswählen.

**Ein neues Package erstellen:** Dem Chat die benötigten Entitäten und das
gewünschte Verhalten geben, gegebenenfalls mit CSV-Bestand als zusätzlichem Kontext.
Eine vollständige Package-YAML zurückgeben lassen. Beim Import zum Beispiel
`packages/stromzaehler_neu.yaml` als Zielpfad eintragen und **Als neue Datei
importieren** wählen. Die Einbindung in die HA-Konfiguration anschließend prüfen.

### Import und Diff

1. Bei einer vorhandenen Datei **Import / Diff** anklicken, oder unten eine oder
   mehrere YAML-Dateien, passende Kontextdateien oder ein Configuration-ZIP wählen.
2. Im Dropdown **Vorhandene Zieldatei** das Ziel und darunter die Importart prüfen.
   Landscape wählt anhand des passendsten Dateinamens vor: etwa
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
Bei **Datei ersetzen** muss der Chat die gesamte Zieldatei liefern: Fehlende
Abschnitte würden entfernt. Ein einzelner YAML-Ausschnitt gehört nur dann in
**Einträge zusammenführen**, wenn er vollständige, eindeutig zuordenbare Einträge
einer unterstützten Struktur enthält. Die Vorschau wählt ganze Dateien aus;
einzelne Diff-Zeilen lassen sich nicht separat übernehmen.

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
- Die Vorschau ist 30 Minuten für den jeweiligen Administrator gültig. Nach
  Ablauf oder einem Neustart die Importdateien erneut prüfen.
- Originaldateien und Journal liegen privat in
  `/config/.storage/landscape_configuration/<Backup-ID>/`. Die `.bin`-Dateien
  enthalten die unveränderten Originalbytes; `manifest.json` ordnet die Pfade zu.
  Im Abschnitt **Backups** lässt sich eine Rücksetzung zuerst prüfen und danach
  übernehmen. Dabei werden auch neu angelegte Dateien wieder entfernt.
- Unterbrochene Importe werden beim nächsten Laden von Landscape anhand des
  Journals zurückgesetzt. Browserabbrüche beenden eine laufende Transaktion nicht.
  Backups bleiben auch nach dem Entfernen der Integration erhalten.

Grenzen: 1 MB je YAML-Datei, 2 MB je Import/Export einschließlich Kontext und
entpacktem ZIP, bis zu 250 YAML-Dateien und 40 MB im Inventar. Ist ein Transfer zu
groß, eine kleinere Dateiauswahl verwenden. Die Inventargrenzen gelten für den
gesamten zugänglichen YAML-Bestand. Die Oberfläche zeigt die letzten 20 Backups;
ältere Backups werden nicht automatisch gelöscht. Symlinks werden nicht verfolgt.

## Assist: Daten exportieren und Optimierungen importieren

In der Seitenleiste steht Administratoren **HA Landscape → Assist** zur Verfügung.

1. **Assist-ZIP herunterladen** anklicken.
2. ZIP in einem KI-Chat wie ChatGPT hochladen und **„Landscape Assist optimieren.
   Beachte die Anleitung und das Schema im ZIP.“** schreiben.
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

Die Anleitung gilt auch für andere KI-Chats, die diese Dateien verarbeiten können.
Zurückgegeben wird ein **JSON-Patch** mit Änderungsvorschlägen nach dem mitgelieferten
Schema. `landscape.json` bleibt der ursprüngliche Export; `source_id` und alte
Werte im Patch müssen zu ihm passen. Die Datei `assist_optimized.json` wird im
Bereich **Assist** importiert.

So kann ein KI-Chat helfen, ähnliche Geräte sprachlich besser unterscheidbar zu
machen. Das in HA konfigurierte Sprach- oder Gesprächsmodell wird durch Landscape
nicht geändert; es arbeitet anschließend mit den übernommenen Namen, Aliasen und
Freigaben weiter.

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

Der Assist-Export wird über die angemeldete Administrator-Sitzung geladen
und **nicht** im öffentlichen `www`-Ordner abgelegt. Die Exportstände und das
letzte Ergebnisprotokoll bleiben in HA gespeichert, bis sie ersetzt oder die
Integration gelöscht wird. Geräte- und Raumnamen sowie reduzierte Zustände können
private Informationen enthalten; den Export vor dem Hochladen im Chat prüfen.

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

## Aktualisieren

Das Update in HACS herunterladen oder den Integrationsordner durch die neue
Version ersetzen. Home Assistant anschließend neu starten und das Landscape-Panel
neu öffnen. Falls noch alte Oberflächentexte angezeigt werden, die HA-Seite neu laden.

## CSV-Bestand exportieren

Die CSV ergänzt die beiden Arbeitsbereiche um eine breite Bestandsaufnahme für
Analysen im Chat oder in einer Tabellenkalkulation. Sie erfasst aktive, nicht
verfügbare, deaktivierte und aktuell zustandslose Registry-Entitäten sowie Geräte-,
Bereichs- und Integrationsinformationen. Zustände sind eine Momentaufnahme;
Verlauf und Langzeitstatistiken gehören nicht zum Export.

Die Datei verwendet Excel-taugliches UTF-8 mit Semikolon als Trennzeichen. Ein
neuer Export ersetzt die vorherige CSV vollständig. Geänderte CSV-Dateien lassen
sich nicht in Landscape zurückimportieren; Änderungen an YAML oder Assist-Daten
laufen über die jeweiligen Arbeitsbereiche und Dateiformate.

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
> entfernt werden. Die Maskierung bekannter Zugangsdaten in Zustandsattributen
> anonymisiert nicht den gesamten Export. Zustände, Geräte- und Bereichsnamen
> können private Informationen enthalten.

### Aktionen für Skripte und Automatisierungen

Zusätzlich zu den Schaltflächen stehen folgende Aktionen für Skripte und
Automatisierungen bereit:

```yaml
action: landscape.export_csv
```

```yaml
action: landscape.delete_csv
```

### Exportierte Spalten

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

### Maskierung im CSV

Innerhalb der Zustandsattribute (`attributes_json`) werden bekannte
Zugangsdatenfelder wie `access_token`, `password`, `api_key`, `secret` und `pin`
rekursiv durch `<redacted>` ersetzt. Bekannte Token-Parameter in dort enthaltenen
URLs werden ebenfalls maskiert. Diese Filterung erfasst nicht pauschal alle
CSV-Spalten oder beliebige Geheimnisse in Freitexten. Namen, Kennungen und weitere
Registry-Daten bleiben enthalten; die Datei vor der Weitergabe prüfen.

## Hinweise bei Problemen im Dateiaustausch

- **Der KI-Chat kann kein ZIP lesen:** Die enthaltenen Dateien entpacken und
  gemeinsam übergeben. Beim Assist-Export gehören Bestand, Schema und Anleitung
  zusammen.
- **Dem Chat fehlt Kontext:** Bei Änderungen über mehrere Includes hinweg die
  zugehörigen YAML-Dateien mitgeben. Ein Assist- oder CSV-Export kann zusätzliche
  Informationen über tatsächlich vorhandene Entitäten liefern.
- **„Seit dem Export geändert“:** Den aktuellen Stand mit neuem Kontext exportieren
  und die gewünschten Änderungen damit abgleichen lassen. Die Begleitdateien
  unverändert lassen. Eine neue Diff-Vorschau desselben veralteten Imports löst
  den Konflikt nicht auf.
- **YAML-Import abgelehnt oder zurückgesetzt:** Die Prüfmeldung bzw. das
  Ergebnisprotokoll zusammen mit den betroffenen Dateien im KI-Chat analysieren
  lassen und die Korrektur erneut prüfen. Bei einem gemeldeten Rücksetzungskonflikt
  zunächst die genannten Dateien und ihr Backup abgleichen.

Versionsänderungen stehen im [Changelog](CHANGELOG.md).

## Lizenz

[MIT](LICENSE)
