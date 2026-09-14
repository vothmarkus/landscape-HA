<p align="center">
  <img src="custom_components/landscape/brand/icon@2x.png" alt="HA Landscape" width="160">
</p>

# HA Landscape

HA Landscape erstellt auf Knopfdruck eine vollständige CSV-Bestandsaufnahme
der Entitäten einer Home-Assistant-Installation. Die Datei eignet sich unter
anderem dazu, einem KI-Assistenten den vorhandenen Aufbau für die Erstellung
passender Automatisierungen zu übergeben.

## Funktionen

- erfasst aktive, nicht verfügbare, deaktivierte und aktuell zustandslose
  Registry-Entitäten
- exportiert Zustand, Attribute, Geräte-, Bereichs-, Integrations- und
  Registry-Informationen
- enthält technische IDs, Anzeigenamen und Labels
- maskiert Tokens, Passwörter, API-Schlüssel und ähnliche Zugangsdaten
- erzeugt Excel-taugliches UTF-8-CSV mit Semikolon als Trennzeichen
- ersetzt bei jedem Export die vorherige Datei vollständig
- bietet einen eigenen Löschknopf für die veröffentlichte Datei
- lässt sich über die Oberfläche einrichten; kein YAML nötig

## Assist mit ChatGPT optimieren (ab 0.2.0)

In der Seitenleiste steht Administratoren **Landscape Assist** zur Verfügung.

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
