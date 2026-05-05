# Umwelftfreundliche_Routenplanung

# Green Vehicle Routing Optimization (GVRP-TW)

Dieses Projekt befasst sich mit der mathematischen Modellierung und algorithmischen Lösung eines umweltorientierten Tourenplanungsproblems (Green Vehicle Routing Problem). Ziel ist es, Lieferrouten unter Berücksichtigung von Emissionen, Last, Straßentypen und Zeitfenstern zu optimieren und den Zielkonflikt zwischen Kosten und Nachhaltigkeit zu analysieren.

## 📋 Projektübersicht

In diesem Operations Research (OR) Projekt wird ein reales Entscheidungsproblem gelöst: Wie kann eine heterogene Fahrzeugflotte so eingesetzt werden, dass die CO2-Emissionen minimiert werden, ohne die Servicequalität (Zeitfenster) oder die wirtschaftliche Effizienz zu gefährden?

**Kernfokus:**
- **Mathematische Modellierung:** Formulierung als Mixed-Integer Linear Program (MILP).
- **Heterogene Flotte:** Einsatz unterschiedlicher Fahrzeugtypen mit variierenden Emissionsprofilen.
- **Emissionsmodell:** Berücksichtigung von Fahrzeuggewicht (Ladung), Geschwindigkeit und Straßentypen.
- **Methodenvergleich:** Gegenüberstellung eines exakten Solvers und einer selbst entwickelten Heuristik.

---

## 🗂 Inhaltsverzeichnis der Projektdokumentation

Die begleitende Projektdokumentation (PDF/Notebook) ist wie folgt gegliedert:

### 1. Einleitung und Fragestellung
* **1.1 Motivation:** Der Konflikt zwischen ökonomischer Effizienz und nachhaltiger Logistik.
* **1.2 Problemstellung:** Das Green Vehicle Routing Problem mit Zeitfenstern (GVRP-TW) und heterogener Flotte.
* **1.3 Zentrale Fragestellung:** Optimale Routen- und Fahrzeugwahl zur Minimierung der Gesamtauswirkungen.
* **1.4 Aufbau der Arbeit.**

### 2. Literaturübersicht und OR-Kontext
* **2.1 Einordnung in die OR-Problemklasse:** Vom klassischen VRP zum Green VRP.
* **2.2 Akademischer Stand der Technik:** Emissionsmodelle (Einfluss von Last, Geschwindigkeit und Straßentyp).
* **2.3 Mathematische Modellierungsansätze:** Exakte Lösungsverfahren in der Literatur.
* **2.4 Heuristische Lösungsansätze:** Metaheuristiken im Kontext des GVRP.
* **2.5 Abgrenzung der eigenen Arbeit.**

### 3. Datenmodell und Datenquellen
* **3.1 Szenariobeschreibung:** Praxisnaher Anwendungsfall (urbane Logistik).
* **3.2 Parameter:** Kundendaten, Zeitfenster, Distanz- und Geschwindigkeitsmatrizen.
* **3.3 Spezifikation der Flotte:** Fahrzeugtypen, Kapazitäten, Emissionsfaktoren.
* **3.4 Emissionsberechnung:** Integration von Straßentypen und Beladungszuständen.
* **3.5 Datenvalidierung:** Plausibilitätsprüfungen der Eingabewerte.
* **3.6 Instanz-Generierung:** Erstellung von Small, Medium und Large Instances.

### 4. Mathematische Modellierung
* **4.1 Systemgrenzen:** Annahmen und Vereinfachungen.
* **4.2 Notation:** Mengen, Parameter und Entscheidungsvariablen.
* **4.3 Zielfunktion:** Internalisierung von Emissionskosten vs. Distanzminimierung.
* **4.4 Nebenbedingungen:** Routing, Kapazitäten, Zeitfenster und Lastflüsse.

### 5. Implementierung: Exakter Löser
* **5.1 Solver-Wahl:** Begründung für den Einsatz von [z.B. Gurobi / CPLEX / CBC].
* **5.2 Modell-Mapping:** Umsetzung des MILP in Python (Pyomo/Gurobipy).
* **5.3 Konfiguration:** Solver-Parameter und Time-Limits.

### 6. Implementierung: Heuristisches Verfahren
* **6.1 Heuristik-Design:** Beschreibung der algorithmischen Logik (z.B. Savings-Algorithmus oder ALNS).
* **6.2 "Grüne" Anpassungen:** Berücksichtigung der Emissionsfaktoren in der Heuristik.
* **6.3 Implementierung:** Python-Code und Validierung der Zulässigkeit.

### 7. Numerische Experimente (Stresstest)
* **7.1 Versuchsaufbau:** Hardware und Testumgebung.
* **7.2 Ergebnisse:** Performance-Analyse über Small, Medium und Large Instances.
* **7.3 Solver-Gaps:** Analyse der Rechenzeit und Güte bei steigender Komplexität.

### 8. Vergleich und Entscheidungsunterstützung
* **8.1 Methodischer Vergleich:** Rechenzeit vs. Lösungsqualität (Solver vs. Heuristik).
* **8.2 Szenarienanalyse:** Sensitivität der Ergebnisse auf Laständerungen.
* **8.3 Trade-off Diskussion:** Pareto-Effizienz zwischen Kosten und CO2-Ausstoß.
* **8.4 Handlungsempfehlungen:** Strategien für Logistikentscheider.

### 9. Limitationen & Ausblick
* **9.1 Modellgrenzen:** Stochastik und dynamische Faktoren.
* **9.2 Erweiterungspotenzial:** Integration von Ladestationen für E-Fahrzeuge.

### 10. Fazit
* **10.1 Zusammenfassung:** Beantwortung der Forschungsfrage.
* **10.2 Schlussfolgerung:** Eignung der Methoden für den Praxiseinsatz.

---

## 🛠 Technologien & Installation

- **Sprache:** Python 3.x
- **Optimierung:** [Gurobi / CPLEX / OR-Tools]
- **Bibliotheken:** `pandas`, `numpy`, `matplotlib`, `scipy`

```bash
# Repository klonen
git clone [https://github.com/nutzername/green-vrp-optimization.git](https://github.com/nutzername/green-vrp-optimization.git)

# Abhängigkeiten installieren
pip install -r requirements.txt
