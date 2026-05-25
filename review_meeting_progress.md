Operations Research
# Review Meeting Progress

## 1) Titel des Projekts
Hazardous Materials Vehicle Routing Problem (HMVRP)

## 2) Teammitglieder
- Luca Siewecke
- Timo Schöddert
- Maher Darweesh
- Jonas Beckmann
- Fuqiang Zhang

## 3) Kern-Entscheidungsfrage
Welche Fahrzeuge bedienen welche Gefahrgutlieferungen auf welchen zulässigen Routen so, dass das Gesamtrisiko minimiert und wirtschaftliche Transportkosten unter allen Logistikrestriktionen eingehalten werden?

## 4) Detaillierte Aufgabenteilung
### Luca - Projektkoordination, Praesentation, GitHub-Management
- Verantwortet die Repository-Struktur inkl. klarer Ordner- und Dateiorganisation.
- Pflegt und aktualisiert README, Projektstatus und Meeting-Dokumentation.
- Verwaltet GitHub-Issues (Planung, Priorisierung, Nachverfolgung).
- Führt Pull-Request-Reviews durch und steuert die Integration aller Teilbeiträge.
- Übernimmt Integrationsmanagement zwischen Daten, Modell, Solver und Heuristik.

### Timo - Datenmodell und Datengenerierung
- Definiert das Datenmodell für Knoten, Kanten, Lieferungen, Fahrzeuge und Risikofaktoren.
- Recherchiert und strukturiert geeignete Datenquellen und Annahmen für Instanzparameter.
- Erzeugt künstliche Instanzen in den Grössen Small, Medium und Large.
- Implementiert Plausibilitätschecks für Wertebereiche, Vollständigkeit und Konsistenz.
- Bereitet reproduzierbare Eingabedaten für Solver- und Heuristiktests vor.

### Maher - Mathematisches Modell
- Definiert Mengen (Sets), Parameter und Entscheidungsvariablen formal und konsistent.
- Formuliert Zielfunktion mit Risiko als Primärziel und Kosten als Sekundärziel.
- Modelliert Nebenbedingungen (Routing, Kapazitäten, Zeitfenster, Fluss-/Zulässigkeitsbedingungen).
- Dokumentiert Modellannahmen, Systemgrenzen und Notation sauber in Markdown/Notebook.
- Stimmt das mathematische Modell eng mit Datenstruktur und Solver-Mapping ab.

### Jonas - Solver-Implementierung
- Setzt die Modellimplementierung in Python um (z. B. Pyomo/Gurobi/OR-Tools/PuLP).
- Implementiert den exakten MILP/LP-Ansatz gemäss Modellbeschreibung.
- Konfiguriert Solver-Parameter, Time-Limits und auswertbare Laufprotokolle.
- Löst kleine Instanzen als erste Validierung der Modellumsetzung.
- Dokumentiert Runtime, Gap und Lösungsqualität für spätere Vergleichsauswertung.

### Fuqiang - Heuristik und Literatur
- Führt Literaturrecherche zu HMVRP Risikomodellen durch.
- Erstellt strukturierte Literatursummary mit relevanten Methoden und Erkenntnissen.
- Entwickelt und implementiert erste heuristische Verfahren (z. B. Greedy, Local Search).
- Definiert Vergleichsideen und Bewertungslogik für Solver vs. Heuristik.
- Unterstützt die Einordnung der experimentellen Ergebnisse in den Forschungskontext.

## 5) Aktueller Status der Kernbausteine
*   **Daten:**  Probleme mit Downloads von Streetview Straßen wegen Fehlendem Speicher (RAM), Unfallorte die bisher passiert sind verfügbar, Nicht alle Daten Formatiert für das Modell

*   **Modell:** Soweit Implementiert

*   **Solver:** Implementiert, Daten müssen noch eingebunden werden

*   **Heuristik:** Literatur rausgesucht, Ansatz noch suchen

*   **Experimente:** tbd

## 6) To-Dos
### Offene Aufgaben
*   [ ] Streetview Daten bekommen -Timo, Jonas
*   [ ] Implementation in Pulp -Jonas
*   [ ] Literatur recherchieren -Fuqiang
*   [ ] Heurstischen Ansatz entwerfen für HMVRP -Fuqiang

### Abgeschlossene Aufgaben
*   [x] Erste Idee Mathematisches Modell -Maher
*   [x] Projektstruktur auf Github initialisieren (Github Issues, review_meeting_progress) -Luca
*   [x] Datenquellen finden -Timo, Jonas

## 7) Aktuelle Literatur

*   Erkut & Verter (1998): Risk modeling for hazardous-material transport
*   Holeczek (2019): Classification and literature review of hazardous-material truck transportation
*   Zografos & Androutsopoulos (2004): Heuristic algorithm for hazardous-material distribution problems
*   Androutsopoulos & Zografos (2012): Bi-objective time-dependent routing and scheduling for hazardous-material distribution
*   Bula et al. (2016): MILP model for hazardous-material vehicle routing
*   Bula et al. (2017): Variable Neighborhood Search for hazardous-material vehicle routing
*   Cuneo et al. (2018): Risk-based multi-objective vehicle routing in fuel logistics

## 8) Bekannte Probleme, Risiken & Fragen für Feedback
*   **Bekannte Probleme/Risiken:** Daten runterladen dauert zu lange und bricht ab durch zu wenig Speicher

*   **Fragen für Feedback:**
    1. tbd
