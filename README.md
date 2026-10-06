# Wolkenwart Regenradar

Radarbasierte Regenvorhersage für Home Assistant. Eigene Integration mit eigener
technischer Kennung `wolkenwart_regenradar` und einem neu implementierten DWD-Leser.

**Version 0.1.0b1 — erste Testversion.** Sie lässt sich parallel zu bestehenden
Wetterintegrationen betreiben. Vor der Anbindung an eine Schutzautomation die
Prognosen am eigenen Standort beobachten und das Verhalten bei Ausfällen prüfen.
Bestehende Integrationen, Entitäten und Automationen werden nicht umgestellt.

## Was sie liefert

- Zwei Stunden DWD-RADVOR-RV-Prognose in fünfminütigen Abschnitten.
- Erwarteter Regenbeginn und geplanter Schutzzeitpunkt mit einstellbarem Vorlauf.
- Binärsensoren „Niederschlag erwartet“ und „Regenschutz fällig“.
- Niederschlagsmenge und maximale Intensität für die nächste Stunde.
- DWD-Ausgabe, Datenalter und Status: aktuell, zwischengespeichert, abgelaufen oder keine Daten.
- Deutsche und englische Oberfläche. Mehrere Standorte möglich.

Es werden keine Motorbefehle ausgeführt. Die Integration liefert Informationen,
an die eine eigene Automation angeschlossen werden kann. Es werden weder ein
Wolkenwart-Konto noch eine Box oder ein zusätzlicher Wetterdienst benötigt.
Home Assistant braucht Internetzugang zum DWD.

## Installation über HACS

1. In HACS unter **Benutzerdefinierte Repositories** diese Adresse als Integration hinzufügen:
   `https://github.com/evgparen/wolkenwart-regenradar`
2. Vorabversionen anzeigen und **0.1.0b1** herunterladen.
3. Home Assistant neu starten.
4. Unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** nach
   **Wolkenwart Regenradar** suchen und den Standort eingeben.

Voraussetzung: Home Assistant 2026.9 oder neuer. Für eine manuelle Installation
den Ordner `custom_components/wolkenwart_regenradar` in das gleichnamige
Verzeichnis unter `/config/custom_components` kopieren und Home Assistant neu starten.

## Optionen und Datenalter

| Option | Standard | Bereich |
| --- | --- | --- |
| Regenschwelle | 0,1 mm/h | 0–100 mm/h |
| Schutzvorlauf | 15 Minuten | 0–60 Minuten |
| Maximales Quelldatenalter | 20 Minuten | 10–20 Minuten |

Die Altersgrenze zählt ab dem **Beginn des ersten Messfensters**, fünf Minuten
vor dem Ausgabezeitpunkt. Sie wird bei Fehlern nicht verlängert. Nach einem
Abruffehler wird frühestens nach 60 Sekunden erneut angefragt; der 30-Sekunden-
Koordinatortakt kann den nächsten Versuch entsprechend verzögern.

Eine gültige zwischengespeicherte Prognose einschließlich Schutzzeitpunkt bleibt
bei einem kurzen Ausfall erhalten. Eine frische korrigierte Prognose ersetzt sie.
Am Ablaufzeitpunkt werden Wetter- und Schutzsensoren unabhängig von laufenden
Netzwerkanfragen nicht verfügbar. Alte Trockenwerte gelten dann nicht mehr als
Entwarnung. Die drei Diagnosesensoren bleiben sichtbar. Ohne ersten erfolgreichen
Abruf starten die Wettersensoren nicht verfügbar; Diagnosen zeigen „Keine Daten“.

Das Datenalter wird mindestens alle 30 Sekunden aktualisiert; der Ablauf und ein
anstehender Schutzzeitpunkt haben zusätzlich eigene Timer. Ein Neustart lädt
keine alte Wetterprognose von der Festplatte.

## Grenzen dieser Version

Deutschland und angrenzendes DWD-Radargebiet. Radarprognosen beschreiben erwarteten
Niederschlag in der Rasterzelle; sie sind kein Nachweis für tatsächlichen Regen
an der Pergola. Die nächste Stundenmenge gewichtet angeschnittene Fünfminutenfenster
zeitanteilig. Der Beginn eines nassen Fünfminutenfensters ist die konservative
Zeitangabe für den erwarteten Regenbeginn.

Version 0.1 konzentriert sich auf Regenvorhersage und Schutzvorlauf. Niederschlagsart
(HymecNG), gemessene RADOLAN-Tagesmengen und Trockenzeitstatistik sind nicht enthalten.
Sie ist kein vollständiger Funktionsersatz für die bisherige DWD-Integration.
Reale Langzeit- und Motorabnahme stehen aus. Es gibt keine automatische Migration.

## Entwicklung

```sh
python -m venv .venv
.venv/bin/pip install '.[test]'
.venv/bin/python -m pytest -q
```

[Architektur und Datenquellen](ARCHITECTURE.md) · [Lizenz](LICENSE) · [Hinweise](NOTICE)
