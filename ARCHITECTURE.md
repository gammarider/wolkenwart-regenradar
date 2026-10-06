# Architektur

Die Integration wurde als separater Quellbestand mit eigener Git-Historie angelegt.
Weder der Komponentenordner noch der Radarleser der bisherigen HA-Integration
oder der Wolkenwart-Box sind übernommen. Der bestehende DWD Reliable Fork bleibt
ein eigenes Projekt mit eigener Lizenzhistorie und eigener Updatequelle.

- `core.py`: unveränderliche Prognosefenster, Altersgrenzen und zeitbezogene Auswertung.
- `radar.py`: begrenzter HTTPS-Abruf, sichere Verarbeitung eines TAR-Archivs im Speicher,
  Prüfung der 25 HDF5-Fenster und Auslesen nur der betreffenden Rasterzelle.
- `coordinator.py`: Abrufsteuerung, Wiederholung, Diagnose und unabhängige Zeittimer.
- `config_flow.py`: Standort, doppelte Einträge verhindern, Optionen.
- Sensorplattformen: eigene Kennungen und ausschließlich lesende Entitäten.

DWD-Publikationen werden im Fünfminutenraster abgeleitet; zum Sollzeitpunkt werden
250 Sekunden Bereitstellungsverzögerung sowie ein stabiler Versatz von 0–30 Sekunden
angesetzt. Nicht verfügbare Dateien sind ein Abruffehler, kein Beweis für eine
bestimmte Ursache. Pro Koordinatortakt wird höchstens eine Anfrage gestartet.
Eine neuere fällige Ausgabe ersetzt das Ziel eines späteren Wiederholungsversuchs.

Datenquellen und Spezifikationen:

- DWD RADVOR RV: https://opendata.dwd.de/weather/radar/composite/rv/
- DWD RV-Format: https://www.dwd.de/DE/leistungen/radarprodukte/formatbeschreibung_rv.pdf?__blob=publicationFile&v=3
- DWD RADOLAN/RADVOR-Kompositformat 2.6: https://opendata.dwd.de/climate_environment/CDC/help/RADOLAN/Unterstuetzungsdokumente/RADOLAN-RADVOR-Kompositformat_2.6.pdf
- EUMETNET ODIM H5: https://www.eumetnet.eu/wp-content/uploads/2026/01/ODIM_H5_v2.4.2_final.pdf
- PROJ stereografische Projektion: https://proj.org/en/stable/operations/projections/stere.html
- Home Assistant Koordinator: https://developers.home-assistant.io/docs/integration_fetching_data/

Das DE1200-Gitter hat 1100 Spalten und 1200 Zeilen mit 1000 Metern Abstand.
Die ODIM-Metadaten beschreiben die äußere obere linke Ecke bei (-500, 500) Metern
in der angegebenen Projektion. Pixelzentren liegen auf ganzzahligen Kilometern;
Zeilen laufen von Nord nach Süd. PROJ übernimmt die WGS84-Transformation.
Nicht unterstützte Gitter/Projektionen, fehlende oder doppelte Zeitfenster,
abweichende Zeitstempel, Nodata und ungültige Werte führen zu einem Abruffehler.
Undetect wird gemäß ODIM als null Niederschlag behandelt.

Tests erzeugen synthetische ODIM-Daten einschließlich bekannter Pixelpositionen.
Die HA-Tests starten echte Config-Entries und prüfen sichtbare Entitätszustände,
Ablauf während hängender Anfragen, Wiederanlauf sowie Aufräumen beim Entladen.
Quell- und Liveprüfungen belegen keine Vorhersagegenauigkeit am Kundenstandort.
