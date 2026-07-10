# Hazardous Materials Vehicle Routing Problem (HMVRP)

## Projektmitglieder

- Luca Siewecke (lucasiewecke)
- Timo Schöddert (timoschoeddert247)
- Maher Darweesh (maherd18)
- Jonas Beckmann (jbeckmann784)
- Fuqiang Zhang (viikly)

---

## Projektbeschreibung

Dieses Projekt befasst sich mit der mathematischen Modellierung und algorithmischen Lösung eines Tourenplanungsproblems für Gefahrguttransporte.

Ziel ist es, Lieferungen auf zulässigen Routen so zu planen, dass das Gesamtrisiko für Bevölkerung und Infrastruktur minimiert wird, während wirtschaftliche Transportkosten und logistische Restriktionen eingehalten werden.

Im Mittelpunkt steht ein Operations-Research-Ansatz für das Hazardous Materials Vehicle Routing Problem (HMVRP) mit realen und realitätsnahen Daten.

---

## Kern-Entscheidungsfrage

Welche Fahrzeuge bedienen welche Gefahrgutlieferungen auf welchen zulässigen Routen so, dass das Gesamtrisiko minimiert und wirtschaftliche Transportkosten unter allen Logistikrestriktionen eingehalten werden?

---

## Ziele des Projekts

- Entwicklung eines belastbaren HMVRP-Modells zur Risikominimierung unter wirtschaftlichen und logistischen Restriktionen
- Aufbau einer sauberen Datenbasis mit reproduzierbaren Instanzen (Small, Medium, Large)
- Umsetzung und Vergleich eines exakten Solver-Ansatzes und einer Heuristik hinsichtlich Laufzeit, Lösbarkeit und Lösungsqualität
- Durchführung nachvollziehbarer Experimente als Grundlage für belastbare Entscheidungsunterstützung

---

## Projektstruktur und zentrale Dateien

Die Projektstruktur ist entlang der Kernbereiche Daten, Modellierung, Heuristik und Experimente aufgebaut.

### Root-Ebene

- `README.md`: Zentrale Projektübersicht mit Zielbild, Rollen, Status und Literatur
- `review_meeting_progress.md`: Laufender Projektstatus, Aufgabenverteilung, Risiken und To-dos
- `requirements.current-venv.txt`: Python-Abhängigkeiten der aktiven Entwicklungsumgebung

### `data/`

- `data/raw/`: Rohdaten und Vorverarbeitung (u. a. Notebooks zur Datenerzeugung/-bereinigung)
- `data/processed/`: Modellnahe, aufbereitete Datensätze
- Weitere Projektdaten liegen zentral in unserer Sciebo-Cloud.

### `models/`

- `models/math_model/Math_Model_Hazmat_CVRP-MT.ipynb`: Mathematische Modellierung
- `models/Gefahrgut_Routenplanung_MILP-pulp.mps`: Exportiertes MILP-Modell
- `models/Gefahrgut_Routenplanung_MILP-pulp.sol`: Beispielhafte Solver-Lösung

### `heuristics/`

- `heuristics/real_data_path_heuristic.py`: Heuristischer Pfadansatz auf realen Daten
- `heuristics/real_data_adapter.py`: Adapter zwischen Daten und Heuristik
- `heuristics/risk_cost_path_heuristic_toy.py`: Vereinfachter Risiko-Kosten-Ansatz (Toy)
- `heuristics/test_real_data_path_heuristic.py`: Tests für zentrale Heuristikkomponenten
- `heuristics/heuristic_design.md`: Designnotizen zur Heuristik

### `experiments/`

- `experiments/`: Experimentcode und Auswertungsskripte (laufender Aufbau)

### `literature/`

- `literature/literature_summary.md`: Strukturierte Zusammenfassung der relevanten Fachliteratur

---

## Rollen und Aufgabenverteilung

### Luca - Projektkoordination, Präsentation, GitHub-Management

- Repository-Struktur und Dokumentation pflegen
- README, Projektstatus und Meeting-Dokumentation aktualisieren
- GitHub-Issues planen und verfolgen
- Pull Requests reviewen und Integration steuern
- Unterstützung bei Solver-Implementierung

### Timo - Datenmodell und Datengenerierung

- Datenmodell für Knoten, Kanten, Lieferungen, Fahrzeuge und Risikofaktoren definieren
- Datenquellen recherchieren und Annahmen strukturieren
- Instanzen in Small, Medium, Large erzeugen
- Plausibilitätschecks für Vollständigkeit und Konsistenz aufsetzen
- Reproduzierbare Eingabedaten für Tests bereitstellen

### Maher - Mathematisches Modell

- Mengen, Parameter und Entscheidungsvariablen formal definieren
- Zielfunktion mit Risiko (primär) und Kosten (sekundär) formulieren
- Nebenbedingungen für Routing, Kapazität, Fluss und Zulässigkeit modellieren
- Annahmen, Systemgrenzen und Notation dokumentieren
- Abstimmung mit Datenstruktur und Solver-Mapping

### Jonas - Solver-Implementierung

- Modell in Python umsetzen (z. B. Pyomo/Gurobi/OR-Tools/PuLP)
- Exakten MILP/LP-Ansatz implementieren
- Solver-Parameter, Time-Limits und Laufprotokolle konfigurieren
- Kleine Instanzen als erste Validierung lösen
- Runtime, Gap und Lösungsqualität dokumentieren

### Fuqiang - Heuristik und Literatur

- Literaturrecherche zu HMVRP-Risikomodellen
- Strukturierte Literatursummary erstellen
- Erste heuristische Verfahren entwickeln und implementieren
- Bewertungslogik für Solver-vs-Heuristik definieren
- Ergebnisse im Forschungskontext einordnen

---

## Aktuelle Literatur

- Erkut, E. & Verter, V. (1998): Risk modeling for hazardous-material transport
- Holeczek, N. (2019): Classification and literature review of hazardous-material truck transportation
- Zografos, K. G. & Androutsopoulos, K. N. (2004): Heuristic algorithm for hazardous-material distribution problems
- Androutsopoulos, K. N. & Zografos, K. G. (2012): Bi-objective time-dependent routing and scheduling for hazardous-material distribution
- Bula, G. A. et al. (2016): MILP model for hazardous-material vehicle routing
- Bula, G. A. et al. (2017): Variable Neighborhood Search for hazardous-material vehicle routing
- Cuneo, D. et al. (2018): Risk-based multi-objective vehicle routing in fuel logistics

---

## Hinweise zur technischen Umgebung

- Empfohlen: Python-Umgebung mit den in `requirements.current-venv.txt` hinterlegten Paketen
- Bestehende Modell- und Heuristikdateien sind als Ausgangspunkt für die nächsten Iterationen vorbereitet

