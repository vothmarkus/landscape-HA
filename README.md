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
