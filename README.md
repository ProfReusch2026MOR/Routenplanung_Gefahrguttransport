# Hazardous Materials Vehicle Routing Optimization (HMVRP)

Dieses Projekt befasst sich mit der mathematischen Modellierung und algorithmischen Lösung eines Tourenplanungsproblems für Gefahrguttransporte. Ziel ist es, Lieferrouten so zu optimieren, dass das Gesamtrisiko für Bevölkerung und Infrastruktur minimiert wird, während gleichzeitig wirtschaftliche Transportkosten und Logistikrestriktionen eingehalten werden.

## 📋 Projektübersicht

In diesem Operations Research (OR) Projekt wird ein reales, multikriterielles Entscheidungsproblem für Logistikplaner gelöst: Welches Fahrzeug übernimmt welche Gefahrgutlieferung auf welcher Route? Das Problem wird als **Hazardous Materials Vehicle Routing Problem (HMVRP)** bzw. als *Multi-Objective Network Flow Problem* modelliert, um Sicherheit und Wirtschaftlichkeit mathematisch auszubalancieren.

### 🎯 Kernfokus & Optimierungsziele
* **Risikominimierung (Primärziel):** Reduzierung des Gesamtrisikos entlang der Route basierend auf Bevölkerungsdichte, Unfallwahrscheinlichkeiten und der Nähe zu kritischer Infrastruktur.
* **Kostenoptimierung (Sekundärziel):** Begrenzung der wirtschaftlichen Faktoren wie Distanz, Fahrzeit und Mautgebühren.

### ⚙️ Restriktionen & Rahmenbedingungen
* **Behördliche Einschränkungen:** Striktes Routing im Straßennetz unter Ausschluss von Gefahrgutverbotszonen, dichten Innenstädten, Wohngebieten und gesperrten Tunneln.
* **Kapazitäts- & Logistikrestriktionen:** Einhaltung von Fahrzeugkapazitäten, der begrenzten Fahrzeuganzahl sowie der lückenlosen Transportpflicht für jede Lieferung.
* **Netzwerklogistik:** Mathematische Abbildung über einen gerichteten Graphen

---

## 🗂 Inhaltsverzeichnis der Projektdokumentation

Die begleitende Projektdokumentation (PDF/Notebook) ist wie folgt gegliedert:

### 1. Einleitung
* **1.1 Motivation:** Der Konflikt zwischen ökonomischer Effizienz und nachhaltiger Logistik.
* **1.2 Problemstellung und Forschungsfrage:** Das Green Vehicle Routing Problem mit Zeitfenstern (GVRP-TW) und heterogener Flotte sowie die zentrale Fragestellung zur optimalen Routen- und Fahrzeugwahl.
* **1.3 Zielsetzung und Aufbau der Arbeit:** Minimierung der Gesamtauswirkungen und Struktur der restlichen Kapitel.

### 2. Literaturübersicht und OR-Kontext
* **2.1 Einordnung in die OR-Problemklasse:** Vom klassischen VRP zum Green VRP.
* **2.2 Aktueller Stand der Forschung:** Akademischer Stand der Technik und Emissionsmodelle (Einfluss von Last, Geschwindigkeit und Straßentyp).
* **2.3 Mathematische Modellierungsansätze:** Exakte Lösungsverfahren in der Literatur und Abgrenzung der eigenen Arbeit.
* **2.4 Heuristische Lösungsansätze:** Metaheuristiken im Kontext des GVRP.

### 3. Datenmodell und Datenquellen
* **3.1 Beschreibung des Szenarios:** Praxisnaher Anwendungsfall (urbane Logistik).
* **3.2 Eingabedaten und Netzwerkparameter:** Kundendaten, Zeitfenster, Distanz- und Geschwindigkeitsmatrizen.
* **3.3 Fahrzeugsparameter:** Spezifikation der heterogenen Flotte, Fahrzeugtypen und Kapazitäten.
* **3.4 Emissionsberechnung:** Integration von Emissionsfaktoren, Straßentypen und Beladungszuständen.
* **3.5 Datenvalidierung:** Plausibilitätsprüfungen der Eingabewerte.
* **3.6 Instanz-Generierung:** Erstellung von Small, Medium und Large Instances.

### 4. Mathematische Modellierung
* **4.1 Systemgrenzen:** Annahmen und Vereinfachungen.
* **4.2 Notation: Mengen, Parameter und Entscheidungsvariablen:** Mathematische Formalisierung des Problems.
* **4.3 Zielfunktion:** Internalisierung von Emissionskosten vs. Distanzminimierung.
* **4.4 Nebenbedingungen:** Routing, Kapazitäten, Zeitfenster und Lastflüsse.

### 5. Implementierung der Lösungsverfahren
* **5.1 Exakter Lösungsansatz**
    * **5.1.1 Solver-Wahl:** Begründung für den Einsatz von [z.B. Gurobi / CPLEX / CBC].
    * **5.1.2 Modell-Mapping:** Umsetzung des MILP in Python (Pyomo/Gurobipy).
    * **5.1.3 Konfiguration:** Solver-Parameter und Time-Limits.
* **5.2 Heuristischer Lösungsansatz**
    * **5.2.1 Heuristik-Design:** Beschreibung der algorithmischen Logik (z.B. Savings-Algorithmus oder ALNS).
    * **5.2.2 Berücksichtigung umweltspezifischer Faktoren:** „Grüne“ Anpassungen und Einbindung der Emissionsfaktoren in die Heuristik.
    * **5.2.3 Implementierung:** Python-Code und Validierung der Zulässigkeit.

### 6. Numerische Experimente und Ergebnisse
* **6.1 Solver Stresstest:** Versuchsaufbau (Hardware/Testumgebung) und Performance-Analyse über Small, Medium und Large Instances samt Solver-Gaps (Rechenzeit/Güte).
* **6.2 Methodenvergleich: Exakter vs. heuristischer Lösungsansatz:** Methodischer Vergleich von Rechenzeit vs. Lösungsqualität.
* **6.3 Analyse der Trade-offs:** Szenarienanalyse zur Sensitivität bei Laständerungen und Diskussion der Pareto-Effizienz zwischen Kosten und CO2-Ausstoß.

### 7. Fazit und Ausblick
* **7.1 Zusammenfassung der Ergebnisse:** Beantwortung der Forschungsfrage und Eignung der Methoden für den Praxiseinsatz.
* **7.2 Kritische Würdigung und Limitationen des Modells:** Modellgrenzen bezüglich Stochastik und dynamischen Faktoren.
* **7.3 Ausblick und Handlungsempfehlung für die Praxis:** Strategien für Logistikentscheider und Erweiterungspotenzial (z. B. Integration von Ladestationen für E-Fahrzeuge).

---


## 🛠 Technologien & Installation

- **Bibliotheken:** `pandas`, `numpy`, `matplotlib`, `scipy`

