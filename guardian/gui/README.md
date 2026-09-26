# gui/ — Phase 4

Noch nicht implementiert. Geplant laut Aufgabenstellung: Dashboard
(Status, Bedrohungen heute, gescannte Dateien, überwachte Prozesse) sowie
die Bereiche Dashboard/Scan/Protection/Quarantine/Events/Rules/Settings
mit den Aktionen Quick/Full/Custom Scan.

Die Phase-1-CLI (`cli/`) liefert bereits alle Daten, die ein Dashboard
brauchen würde (`guardian status`, `guardian events`, `guardian quarantine
list`) — die GUI wird ein Client dieser bestehenden Logik, keine
Neuimplementierung.
