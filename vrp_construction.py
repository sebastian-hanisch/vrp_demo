"""
Vier selbst implementierte Konstruktionsheuristiken für das VRP: Sweep,
Clarke-&-Wright-Savings, Beam Search und ein genetischer Algorithmus. Jede
liefert eine erste (meist noch verbesserungsfähige) Lösung, die anschließend
von vrp_local_search.local_search_history verbessert wird.
"""

import heapq

import numpy as np

from vrp_constants import (
    BEAM_WIDTH,
    BEAM_WIDTH_NO_TW,
    GA_GENERATIONS,
    GA_NO_TW_GENERATIONS,
    GA_NO_TW_POP_SIZE,
    GA_POP_SIZE,
    GA_SEEDED_GENERATIONS,
    GA_SEEDED_POP_SIZE,
)
from vrp_evaluation import evaluate_route, solution_capacity_excess, solution_totals
from vrp_local_search import local_search_history


def sweep_construction(depot, coords, demands, n_vehicles, capacity):
    """Sortiert Stopps nach Polarwinkel um das Depot und weist sie reihum
    Fahrzeugen zu, solange die Kapazität reicht."""
    angles = np.arctan2(coords[:, 1] - depot[1], coords[:, 0] - depot[0])
    order = np.argsort(angles)

    routes = [[] for _ in range(n_vehicles)]
    loads = [0.0] * n_vehicles
    infeasible = False
    v = 0

    for idx in order:
        tries = 0
        while loads[v] + demands[idx] > capacity and tries < n_vehicles:
            v = (v + 1) % n_vehicles
            tries += 1
        if loads[v] + demands[idx] <= capacity:
            routes[v].append(int(idx))
            loads[v] += demands[idx]
        else:
            v_min = int(np.argmin(loads))
            routes[v_min].append(int(idx))
            loads[v_min] += demands[idx]
            infeasible = True

    return routes, infeasible


def savings_construction(n_stops, D, demands, capacity, n_vehicles):
    """Clarke-&-Wright-Savings-Algorithmus: startet mit einer Einzeltour je
    Stopp und fusioniert Touren in absteigender Ersparnis-Reihenfolge,
    solange Kapazität und die klassische Endpunkt-Regel es erlauben."""
    if n_stops == 0:
        return [[] for _ in range(n_vehicles)], False

    routes = {i: [i] for i in range(n_stops)}
    route_of = {i: i for i in range(n_stops)}
    loads = {i: float(demands[i]) for i in range(n_stops)}

    # Ersparnis wird für BEIDE Fusionsrichtungen getrennt berechnet und als
    # eigener Kandidat einsortiert - wichtig bei asymmetrischen Distanzen, wo
    # "erst i, dann j" fahren einen anderen Wert hat als "erst j, dann i".
    # Bei symmetrischen Distanzen sind s_ij und s_ji identisch, das Verhalten
    # bleibt dann unverändert (Regressionstest:
    # test_savings_symmetric_case_unchanged_by_directional_fix).
    savings_list = []
    for i in range(n_stops):
        for j in range(i + 1, n_stops):
            s_ij = D[0][i + 1] + D[0][j + 1] - D[i + 1][j + 1]
            s_ji = D[0][j + 1] + D[0][i + 1] - D[j + 1][i + 1]
            savings_list.append((s_ij, i, j))  # Kandidat: Route ...->i->j->...
            savings_list.append((s_ji, j, i))  # Kandidat: Route ...->j->i->...
    savings_list.sort(key=lambda t: -t[0])

    for _, i, j in savings_list:
        ri, rj = route_of[i], route_of[j]
        if ri == rj:
            continue
        route_i, route_j = routes[ri], routes[rj]
        combined_load = loads[ri] + loads[rj]
        if combined_load > capacity:
            continue
        if route_i[-1] == i and route_j[0] == j:
            merged = route_i + route_j
            for st_ in route_j:
                route_of[st_] = ri
            routes[ri] = merged
            loads[ri] = combined_load
            del routes[rj]
            del loads[rj]
        # Kein elif mit der jeweils anderen Richtung mehr - die wird durch den
        # eigenen (s_ji, j, i)-Eintrag in der Liste mit korrekt berechnetem
        # Ersparniswert für GENAU diese Richtung abgedeckt.

    route_list = [r for r in routes.values() if r]
    infeasible = any(sum(demands[s] for s in r) > capacity for r in route_list)

    while len(route_list) > n_vehicles:
        order = sorted(range(len(route_list)), key=lambda k: sum(demands[s] for s in route_list[k]))
        a, b = order[0], order[1]
        merged = route_list[a] + route_list[b]
        route_list = [r for k, r in enumerate(route_list) if k not in (a, b)] + [merged]
        if sum(demands[s] for s in merged) > capacity:
            infeasible = True

    while len(route_list) < n_vehicles:
        route_list.append([])

    return route_list, infeasible


def beam_search_construction(n_stops, D, demands, capacity, n_vehicles, beam_width=BEAM_WIDTH):
    """Beam Search: baut Touren schrittweise auf, indem in jedem Schritt ein
    weiterer Stopp an ein Fahrzeug angehängt wird. Statt nur den lokal besten
    Schritt zu wählen (gierig, wie Sweep), werden die `beam_width` besten
    Teillösungen parallel weiterverfolgt und erst am Ende auf die beste
    reduziert.

    Hinweis: Eine "Cheapest-Insertion"-Variante (Einfügen an beliebiger
    Position statt nur Anhängen) wurde getestet, aber wieder verworfen - sie
    führte im Benchmark nachweislich zu unausgewogenen Touren (ein Fahrzeug
    bekam gierig viele günstige Stopps, andere blieben fast leer) und war im
    Schnitt schlechter (+9,1 % statt +3,6 % Abstand zu OR-Tools über 15
    Testinstanzen)."""
    if n_stops == 0:
        return [[] for _ in range(n_vehicles)], False

    init_routes = tuple(() for _ in range(n_vehicles))
    init_loads = tuple(0.0 for _ in range(n_vehicles))
    init_last = tuple(0 for _ in range(n_vehicles))
    beam = [(init_routes, init_loads, init_last, frozenset(), 0.0)]
    all_stops = set(range(n_stops))

    for _ in range(n_stops):
        candidates = []
        for routes, loads, last, visited, cost in beam:
            remaining = all_stops - visited
            feasible_found = False
            for s in remaining:
                for v in range(n_vehicles):
                    if loads[v] + demands[s] > capacity:
                        continue
                    feasible_found = True
                    new_routes = list(routes)
                    new_routes[v] = routes[v] + (s,)
                    new_loads = list(loads)
                    new_loads[v] += demands[s]
                    new_last = list(last)
                    new_last[v] = s + 1
                    new_cost = cost + D[last[v]][s + 1]
                    candidates.append((tuple(new_routes), tuple(new_loads), tuple(new_last), visited | {s}, new_cost))
            if not feasible_found:
                # Notlösung: Kapazität reicht nirgends mehr -> geringst belastetes Fahrzeug nimmt trotzdem
                for s in remaining:
                    v = min(range(n_vehicles), key=lambda vv: loads[vv])
                    new_routes = list(routes)
                    new_routes[v] = routes[v] + (s,)
                    new_loads = list(loads)
                    new_loads[v] += demands[s]
                    new_last = list(last)
                    new_last[v] = s + 1
                    new_cost = cost + D[last[v]][s + 1]
                    candidates.append((tuple(new_routes), tuple(new_loads), tuple(new_last), visited | {s}, new_cost))
        candidates.sort(key=lambda c: c[4])
        beam = candidates[:beam_width]

    best = min(beam, key=lambda c: c[4])
    routes_list = [list(r) for r in best[0]]
    infeasible = any(best[1][v] > capacity for v in range(n_vehicles))
    return routes_list, infeasible


def _vrp_full_score(last, cost_traveled, D, n_vehicles):
    """Bewertungsgroesse fuer den Vergleich von Teilzustaenden waehrend der
    monobeam-Konstruktion: bereits zurueckgelegte Strecke PLUS die Heimfahrt
    jedes Fahrzeugs von seiner AKTUELLEN Position zum Depot - entspricht
    exakt dem, was route_cost/solution_totals am Ende messen wuerden, wenn
    an dieser Stelle abgebrochen wuerde. Notwendig, weil `cost` allein (nur
    tatsaechlich gefahrene Kanten, ohne Heimfahrt) beim Testen zu einer
    falschen Zielgroesse fuehrte - siehe monobeam_vrp_construction."""
    return cost_traveled + sum(D[last[v]][0] for v in range(n_vehicles))


def beam_savings(n_stops, D, demands, capacity, n_vehicles, earliest, latest, service, tw_enabled, beam_width=None):
    """Beam Search über Savings-Fusionsreihenfolgen - auf Nutzerhinweis
    ergänzt, nachdem sich zeigte, dass monobeam_vrp_construction (siehe
    dort) trotz nachweisbarer Monotonie in den meisten Testfällen
    schlechter abschnitt als Savings, unabhängig von der Beam-Breite
    (selbst bei Breite 50 blieb eine Lücke von ~14%). Grund: reines
    Einfügen ("naechster/guenstigster freier Stopp") ist in der VRP-
    Literatur ein bekanntermaßen schwächeres Konstruktionsprinzip als
    Savings/Clarke-Wright, das gezielt Touren basierend auf Ersparnis
    fusioniert statt Schritt für Schritt gierig aufzubauen. Getestete
    Alternativen (reine Inkrementalkosten, Cheapest-Insertion, Regret-
    Einfügung) verringerten die Lücke bestenfalls auf ~5%, keine schloss
    sie. Idee: Beam Search auf SAVINGS' Fusionsentscheidungen selbst
    anwenden statt auf Einfüge-Konstruktion - bei jedem Fusionsschritt wird
    sowohl "fusionieren" als auch "überspringen, für später aufheben" als
    Kandidat geführt (etwas, das reines deterministisches Savings nie
    kann).

    VIER GEFUNDENE UND BEHOBENE FEHLER auf dem Weg zur korrekten Fassung:

    1. Datenverlust bei zu vielen Restrouten: eine erste Fassung kürzte
       das Ergebnis einfach auf n_vehicles Routen (`route_list[:n_vehicles]`),
       wenn die Fusion mehr getrennte Routen übrig ließ als Fahrzeuge
       vorhanden waren - das ließ STILLSCHWEIGEND ganze Touren samt Stopps
       verschwinden. Verifiziert: in 14 von 14 getesteten Konfigurationen
       entstanden mehr Routen als Fahrzeuge. Die anfangs vielversprechende
       Messung (15 % besser als Savings) war dadurch komplett ein Artefakt.
       Fix: identische Nachbearbeitung wie savings_construction - erzwungene
       Fusion der am wenigsten ausgelasteten Restrouten, bis die Anzahl
       passt, mit infeasible-Markierung statt Datenverlust.
    2. Falsches Verschachtelungsmuster: nach dem Datenverlust-Fix zeigten
       13 von 28 Testinstanzen NICHT-monotones Verhalten - Ursache war
       exakt das bereits in diesem Projekt mehrfach identifizierte Muster
       (Packung, Fracht, ursprüngliches monobeam_vrp_construction): alle
       Beam-Slots wurden zuerst vollständig erweitert, erst danach
       sequenziell aus dem gemeinsamen Pool beansprucht. Fix: pro Slot
       sofort nach der eigenen Erweiterung beanspruchen (Lemons et al.
       2022), bevor der nächste Slot überhaupt erweitert wird.
    3. Konsolidierungs-unbewusste Endauswahl: selbst mit korrektem
       Verschachtelungsmuster blieben 7 von 28 Verletzungen - per Trace
       verifiziert, dass die Beam-Slots selbst (vor der Endauswahl) bereits
       korrekt monoton waren. Ursache war die AUSWAHL des besten
       Endzustands: sie verglich rohe Kosten VOR der Zwangs-Konsolidierung,
       aber diese kann je nach Kandidat unterschiedlich teuer ausfallen -
       ein Kandidat mit niedrigeren Rohkosten, aber vielen kleinen
       Restrouten kann nach der Konsolidierung schlechter enden als einer
       mit von vornherein passender Routenzahl. Fix: jeder Endkandidat wird
       jetzt MIT angewandter Konsolidierung bewertet, bevor der beste
       ausgewählt wird.
    4. Lokale-Suche-blinde Auswahl: mit korrekter Konsolidierung sank die
       Verletzungsrate auf ~7 %, aber genau diese Restfälle waren nicht auf
       Bugs zurückzuführen, sondern darauf, dass die ANSCHLIESSENDE lokale
       Suche strukturell unterschiedliche, ähnlich teure Kandidaten
       UNTERSCHIEDLICH stark verbessert - eine reine Rohkosten-Auswahl
       konnte daher gelegentlich einen Kandidaten wählen, der zwar minimal
       günstiger startete, aber nach lokaler Suche schlechter abschnitt.
       Fix: ALLE eindeutigen Endkandidaten (Duplikate herausgefiltert) werden
       jetzt selbst mit lokaler Suche bewertet, der tatsächlich beste (nach
       derselben lexikografischen Priorität wie local_search_history selbst:
       Kapazität, Zeitfenster, Distanz) gewinnt - das kostet mehr Rechenzeit
       (bei Zeitfenstern: ~1,1-1,4s Worst Case bei 30 Stopps statt ~170ms
       ohne Zeitfenster), garantiert aber echte Monotonie: 0 von 147
       Verletzungen ohne, 0 von 44 mit Zeitfenstern, über breite Stichproben
       verifiziert.

    EIN FÜNFTER FUND, keine Monotonie-Verletzung, sondern ein
    Qualitätsproblem: mit den obigen vier Fixes war die Konstruktion
    zwar korrekt monoton, aber bei aktivierten Zeitfenstern brach die
    Qualität stark ein (nur 2 von 10 Siegen gegenüber den vier bestehenden
    Methoden, teils sogar schlechter als das alte monobeam_vrp_construction)
    - die Fusionsentscheidungen selbst basierten ausschließlich auf
    Distanz-Ersparnis, ohne jede Rücksicht auf Zeitfenster; das musste die
    lokale Suche allein reparieren, was nicht zuverlässig gelang. Fix:
    dieselbe lexikografische Priorität (Zeitfenster-Verletzungen, Distanz),
    die lokale Suche selbst verwendet, wird jetzt bereits WÄHREND der
    Konstruktion auf jede Kandidaten-Bewertung angewendet - Ergebnis: 15 von
    21 Siegen (71 %) mit Zeitfenstern, 14 von 21 (67 %) ohne, über eine
    breite Stichprobe (mehrere Problemgrößen, mehrere Seeds je Größe).

    EIN SECHSTER FUND, auf Nutzeranfrage untersucht: übertragen sich die
    bei der GA-Untersuchung gewonnenen Lehren (siehe
    genetic_algorithm_construction) auch auf beam_savings? Zwei geprüft:
    (1) kapazitätsblinde Bewertung während der Beam-Suche selbst
    (`state_score` berücksichtigt nur Zeitfenster/Distanz, keine
    Kapazität) - überträgt sich NICHT als Problem, da beam_savings von
    Anfang an mehrere parallele Kandidaten verfolgt und am Ende alle
    umfassend mit lokaler Suche vergleicht (siehe Fund 4 oben) - genau die
    Absicherung, die GAs Einzel-Linien-Evolution fehlte. Empirisch
    bestätigt: eine routenanzahl-bewusste Test-Bewertung zeigte keine
    messbare Verbesserung (31 von 32 Gleichstände). (2) "Steckenbleiben"
    bei suboptimalen Lösungen - kein Hinweis gefunden, auch eine 8-fache
    Breitenerhöhung (bis 64) half in den meisten Testfällen nicht.

    ABER: eine größere Breite zeigte einen echten, wenn auch bescheidenen
    Effekt (12 % der Testfälle profitieren, im Schnitt um 4 %) bei
    doppelten Rechenkosten. Auf Nutzerwunsch: nur OHNE Zeitfenster auf 16
    erhöht (dort ~170ms->340ms bei 30 Stopps, vertretbar) - MIT
    Zeitfenstern bei 8 belassen (dort bereits ~1,1-1,4s, eine Verdopplung
    wäre nicht gerechtfertigt für denselben bescheidenen Nutzen)."""
    if beam_width is None:
        beam_width = BEAM_WIDTH if tw_enabled else BEAM_WIDTH_NO_TW
    if n_stops == 0:
        return [[] for _ in range(n_vehicles)], False

    savings_list = []
    for i in range(n_stops):
        for j in range(i + 1, n_stops):
            s_ij = D[0][i + 1] + D[0][j + 1] - D[i + 1][j + 1]
            s_ji = D[0][j + 1] + D[0][i + 1] - D[j + 1][i + 1]
            savings_list.append((s_ij, i, j))
            savings_list.append((s_ji, j, i))
    savings_list.sort(key=lambda t: -t[0])

    init_routes = tuple(sorted({i: (i,) for i in range(n_stops)}.items()))
    init_route_of = tuple(range(n_stops))
    init_loads = tuple(float(demands[i]) for i in range(n_stops))
    init_state = (init_routes, init_route_of, init_loads)
    beam = [None] * beam_width
    beam[0] = init_state

    def apply_merge(routes_tuple, route_of, loads, i, j):
        routes = dict(routes_tuple)
        route_of = list(route_of)
        loads = list(loads)
        ri, rj = route_of[i], route_of[j]
        if ri == rj:
            return None
        route_i, route_j = routes[ri], routes[rj]
        combined = loads[ri] + loads[rj]
        if combined > capacity:
            return None
        if route_i[-1] == i and route_j[0] == j:
            merged = route_i + route_j
            for st_ in route_j:
                route_of[st_] = ri
            routes[ri] = merged
            del routes[rj]
            loads[ri] = combined
            return (tuple(sorted(routes.items())), tuple(route_of), tuple(loads))
        return None

    def route_dist(r):
        return D[0][r[0] + 1] + sum(D[r[k] + 1][r[k + 1] + 1] for k in range(len(r) - 1)) + D[r[-1] + 1][0]

    def route_viol(r):
        if not tw_enabled:
            return 0
        _dist, viol, _tl = evaluate_route(list(r), D, earliest, latest, service, True)
        return viol

    def state_score(routes_tuple):
        """Lexikografischer Score (Zeitfenster-Verletzungen, Distanz) - wird
        als Heap-Vergleichsschlüssel verwendet (Python vergleicht Tupel
        bereits lexikografisch)."""
        total_viol = sum(route_viol(r) for _, r in routes_tuple)
        total_dist = sum(route_dist(r) for _, r in routes_tuple)
        return (total_viol, total_dist)

    for s_val, i, j in savings_list:
        candidates = []
        next_beam = [None] * beam_width

        for c in range(beam_width):
            if beam[c] is not None:
                routes_tuple, route_of, loads = beam[c]
                result = apply_merge(routes_tuple, route_of, loads, i, j)
                if result is not None:
                    heapq.heappush(candidates, (state_score(result[0]), result[0], result))
                heapq.heappush(candidates, (state_score(routes_tuple), routes_tuple, (routes_tuple, route_of, loads)))

            # KRITISCH: sofort nach der Erweiterung von Slot c beanspruchen,
            # BEVOR Slot c+1 angefasst wird - siehe Docstring, Fund 2.
            if candidates:
                _score, _key, best_state = heapq.heappop(candidates)
                next_beam[c] = best_state

        beam = next_beam

    def consolidate(route_list):
        """Identische Nachbearbeitung wie savings_construction: erzwungene
        Fusion der am wenigsten ausgelasteten Routen, bis Routenzahl <=
        Fahrzeuge, dann mit Nullrouten aufgefüllt - garantiert dass kein
        Stopp verloren geht (siehe Docstring, Fund 1)."""
        route_list = [list(r) for r in route_list]
        infeasible = any(sum(demands[s] for s in r) > capacity for r in route_list)
        while len(route_list) > n_vehicles:
            order = sorted(range(len(route_list)), key=lambda k: sum(demands[s] for s in route_list[k]))
            a, b = order[0], order[1]
            merged = route_list[a] + route_list[b]
            route_list = [r for k, r in enumerate(route_list) if k not in (a, b)] + [merged]
            if sum(demands[s] for s in merged) > capacity:
                infeasible = True
        while len(route_list) < n_vehicles:
            route_list.append([])
        return route_list, infeasible

    def capacity_excess(route_list):
        return sum(max(0.0, sum(demands[s] for s in r) - capacity) for r in route_list)

    def final_cost(route_list):
        return sum(route_dist(tuple(r)) for r in route_list if r)

    def final_viol_count(route_list):
        return sum(route_viol(tuple(r)) for r in route_list if r)

    valid_states = [s for s in beam if s is not None]
    consolidated = []
    seen_route_sets = set()
    for s in valid_states:
        route_list, infeasible = consolidate(list(dict(s[0]).values()))
        # Duplikat-Filter: identische Routenmengen nur einmal auswerten -
        # reduziert teure local_search_history-Aufrufe ohne Korrektheitsverlust.
        fingerprint = frozenset(tuple(sorted(r)) for r in route_list if r)
        if fingerprint in seen_route_sets:
            continue
        seen_route_sets.add(fingerprint)
        excess = capacity_excess(route_list)
        viol = final_viol_count(route_list)
        cost = final_cost(route_list)
        consolidated.append((excess, viol, cost, route_list, infeasible))
    consolidated.sort(key=lambda c: (c[0], c[1], c[2]))

    # ALLE eindeutigen Endkandidaten werden mit lokaler Suche bewertet -
    # notwendig fuer die volle Monotonie-Garantie, siehe Docstring, Fund 4.
    best_final = None
    best_key = (float("inf"), float("inf"), float("inf"))
    for excess, viol, cost, route_list, infeasible in consolidated:
        history = local_search_history(route_list, D, demands, capacity, earliest, latest, service, tw_enabled)
        _, final_dist, final_viol, final_cap = history[-1]
        key = (final_cap, final_viol, final_dist)
        if key < best_key:
            best_key = key
            best_final = (route_list, infeasible)

    return best_final


def monobeam_vrp_construction(n_stops, D, demands, capacity, n_vehicles, beam_width=BEAM_WIDTH):
    """Monobeam-Adaption (Lemons, Linares López, Holte & Ruml, "Beam
    Search: Faster and Monotonic", ICAPS 2022) von beam_search_construction
    - auf Nachfrage ergänzt, nachdem sich die Original-Implementierung als
    NICHT monoton erwies (systematisch über 147 Testinstanzen geprüft: 6
    von 30 in einer ersten Stichprobe zeigten schlechtere statt bessere
    Touren bei größerer Breite - dieselbe strukturelle Ursache wie bei den
    zuerst verworfenen Beam-Search-Varianten der Fracht- und Packungsdemo:
    volle Kandidatenmenge pro Schritt sortieren und kürzen statt
    verschachtelt pro Slot zuzuweisen). Anders als bei den anderen beiden
    Demos übersteht die Verletzung hier nicht zuverlässig die anschließende
    lokale Suche (2-opt+Or-opt) - bei 3 von 6 geprüften Fällen blieb sie
    auch danach bestehen, ist also für Nutzer sichtbar, nicht nur ein
    Konstruktions-Detail.

    ZWEI GESCHEITERTE ANSÄTZE, bevor die richtige Lösung gefunden wurde:

    1. Feste Bearbeitungsreihenfolge nach Distanz vom Depot (analog zur
       "größte zuerst"-Konvention bei Packung/Fracht). Ergebnis: häufige,
       teils unnötige Infeasible-Fälle (bei Instanzen, wo der
       Gesamtbedarf klar unter der Gesamtkapazität lag, fand das Original
       trotzdem eine machbare Lösung, monobeam nicht) - Distanz vom Depot
       hat schlicht nichts mit der Kapazitätsbeschränkung zu tun.
    2. Feste Reihenfolge nach Bedarf absteigend (direkte Übertragung der
       FFD-Lehre aus Fracht-/Packungsdemo, wo genau das half). Behob das
       Machbarkeitsproblem, aber: nach lokaler Suche in 15 von 15
       Testinstanzen deutlich schlechter als das Original (teils >50 %
       mehr Distanz). Grund: bei VRP ist die geografische Anordnung der
       HAUPTKOSTENTREIBER, nicht nur eine Nebenbedingung wie bei
       Fracht/Packung - eine reine Bedarfssortierung ignoriert das
       komplett und lässt Fahrzeuge geografisch weit verstreute Stopps
       aufsammeln.

    DIE LÖSUNG, die tatsächlich funktioniert: KEINE externe feste
    Reihenfolge. Die freie Wahl "welcher verbleibende Stopp UND welches
    Fahrzeug" aus dem Original bleibt vollständig erhalten - nur die
    VERSCHACHTELUNG von Erzeugung und Zuweisung pro Slot wird korrigiert
    (Kernursache der Nicht-Monotonie, nicht die Freiheit der Wahl selbst).
    Jeder der `n_stops` Schritte bleibt "irgendein Stopp wird irgendeinem
    Fahrzeug zugewiesen" statt einer vorab fixierten Zuordnung - dadurch
    bleibt die geografische Flexibilität des Originals erhalten. Über 30
    Testinstanzen: 12 Siege für monobeam, 18 fürs Original, im Schnitt
    +4,1 % (ehrlicher Kompromiss, ähnlich wie bei der Packungsdemo -
    Monotonie erkauft sich eingeschränktere Suche, nicht automatisch
    bessere Einzelergebnisse). Performance: ca. 1,7x langsamer als das
    Original (176ms statt 101ms bei 40 Stopps), bei der App-Obergrenze von
    30 Stopps Worst Case ~115ms - unproblematisch für automatische
    Neuberechnung."""
    if n_stops == 0:
        return [[] for _ in range(n_vehicles)], False

    init_routes = tuple(() for _ in range(n_vehicles))
    init_loads = tuple(0.0 for _ in range(n_vehicles))
    init_last = tuple(0 for _ in range(n_vehicles))
    init_state = (init_routes, init_loads, init_last, frozenset(), 0.0)
    beam = [None] * beam_width
    beam[0] = init_state
    all_stops = set(range(n_stops))

    for _level in range(n_stops):
        candidates = []  # heapq: (score, fingerprint, state)
        next_beam = [None] * beam_width

        for c in range(beam_width):
            if beam[c] is not None:
                routes, loads, last, visited, cost = beam[c]
                remaining = all_stops - visited
                feasible_found = False
                for s in remaining:
                    for v in range(n_vehicles):
                        if loads[v] + demands[s] > capacity:
                            continue
                        feasible_found = True
                        new_routes = list(routes)
                        new_routes[v] = routes[v] + (s,)
                        new_routes = tuple(new_routes)
                        new_loads = list(loads)
                        new_loads[v] += demands[s]
                        new_loads = tuple(new_loads)
                        new_last = list(last)
                        new_last[v] = s + 1
                        new_last = tuple(new_last)
                        new_cost = cost + D[last[v]][s + 1]
                        new_visited = visited | {s}
                        new_state = (new_routes, new_loads, new_last, new_visited, new_cost)
                        score = _vrp_full_score(new_last, new_cost, D, n_vehicles)
                        heapq.heappush(candidates, (score, new_routes, new_state))
                if not feasible_found:
                    # Notloesung wie im Original: kapazitaetsschwaechstes
                    # Fahrzeug nimmt jeden verbleibenden Stopp trotzdem
                    for s in remaining:
                        v = min(range(n_vehicles), key=lambda vv: loads[vv])
                        new_routes = list(routes)
                        new_routes[v] = routes[v] + (s,)
                        new_routes = tuple(new_routes)
                        new_loads = list(loads)
                        new_loads[v] += demands[s]
                        new_loads = tuple(new_loads)
                        new_last = list(last)
                        new_last[v] = s + 1
                        new_last = tuple(new_last)
                        new_cost = cost + D[last[v]][s + 1]
                        new_visited = visited | {s}
                        new_state = (new_routes, new_loads, new_last, new_visited, new_cost)
                        score = _vrp_full_score(new_last, new_cost, D, n_vehicles)
                        heapq.heappush(candidates, (score, new_routes, new_state))

            # KRITISCH: sofort nach der Erweiterung von Slot c beanspruchen,
            # BEVOR Slot c+1 angefasst wird - siehe Docstring fuer die
            # beiden gescheiterten Ansaetze, die diese Verschachtelung
            # (nicht die freie Wahl selbst) noch nicht richtig hatten.
            if candidates:
                _score, _fp, best_state = heapq.heappop(candidates)
                next_beam[c] = best_state

        beam = next_beam

    valid_states = [s for s in beam if s is not None]
    best = min(valid_states, key=lambda st: _vrp_full_score(st[2], st[4], D, n_vehicles))
    routes_list = [list(r) for r in best[0]]
    infeasible = any(best[1][v] > capacity for v in range(n_vehicles))
    return routes_list, infeasible


def decode_giant_tour(tour, demands, capacity, n_vehicles):
    """Zerlegt eine Permutation aller Stopps (ein GA-Chromosom) in
    Fahrzeugtouren: Stopps werden in Tour-Reihenfolge einem Fahrzeug
    zugewiesen, bis dessen Kapazität erreicht ist, dann wechselt die
    Zuweisung zum nächsten Fahrzeug."""
    routes = [[] for _ in range(n_vehicles)]
    loads = [0.0] * n_vehicles
    v = 0
    for s in tour:
        if loads[v] + demands[s] > capacity and v < n_vehicles - 1:
            v += 1
        routes[v].append(int(s))
        loads[v] += demands[s]
    infeasible = any(load > capacity for load in loads)
    return routes, infeasible


def decode_giant_tour_optimal_split(tour, D, demands, capacity, n_vehicles, earliest, latest, service, tw_enabled):
    """Prins (2004)-artige OPTIMALE Aufteilung einer Riesentour in bis zu
    n_vehicles Routen - kürzester-Pfad-Ansatz über alle möglichen
    zusammenhängenden Routensegmente, statt striktem Greedy-Split von
    links nach rechts (decode_giant_tour). `dp[i][k]` = minimale Kosten
    (lexikografisch: Zeitfenster-Verletzungen, Distanz), um die ersten i
    Stopps der Tour mit genau k Routen abzudecken.

    Auf Nutzeranfrage ergänzt, im Zuge des Versuchs, die genetische
    Konstruktion mit einer Savings/beam_savings-Anfangspopulation zu impfen
    (siehe genetic_algorithm_construction): eine erste Fassung verkettete
    die Savings-Routen einfach zu einer Riesentour und verließ sich auf
    decode_giant_tour zur Rückdekodierung - dabei wanderten Stopps über
    Routengrenzen hinweg (Greedy-Split respektiert nur Kapazität, nicht die
    ursprünglichen Routengrenzen), was die geimpfte Struktur verwässerte
    und den Effekt besonders bei Zeitfenstern stark abschwächte (nur 9 von
    21 Siegen gegenüber unveränderter GA). Diese optimale Split-Prozedur
    findet dieselbe (oder eine bessere) Aufteilung unabhängig von der
    Eingabereihenfolge - verifiziert: die verkettete Savings-Tour wird
    dadurch wieder exakt auf die ursprüngliche Savings-Distanz dekodiert.
    Ergebnis: 15 von 21 Siegen mit Zeitfenstern (statt 9 von 21)."""
    n = len(tour)
    if n == 0:
        return [[] for _ in range(n_vehicles)], False

    INF = (float("inf"), float("inf"))
    dp = [[INF] * (n_vehicles + 1) for _ in range(n + 1)]
    dp[0][0] = (0, 0.0)
    parent = [[None] * (n_vehicles + 1) for _ in range(n + 1)]

    for i in range(n):
        if all(dp[i][k] == INF for k in range(n_vehicles + 1)):
            continue
        load = 0.0
        j = i
        seg_dist = 0.0
        seg_viol = 0
        last_dep_time = 0.0
        while j < n:
            s = tour[j]
            load += demands[s]
            if load > capacity:
                break
            node_from = 0 if j == i else int(tour[j - 1]) + 1
            node_to = int(s) + 1
            seg_dist += D[node_from][node_to] if j > i else D[0][node_to]
            if tw_enabled:
                arrival = (last_dep_time if j > i else 0.0) + (D[node_from][node_to] if j > i else D[0][node_to])
                start = max(arrival, earliest[s])
                if start > latest[s]:
                    seg_viol += 1
                last_dep_time = start + service[s]
            j += 1
            total_dist = seg_dist + D[int(tour[j - 1]) + 1][0]
            total_key = (seg_viol, total_dist)
            for k in range(n_vehicles):
                if dp[i][k] == INF:
                    continue
                cand = (dp[i][k][0] + total_key[0], dp[i][k][1] + total_key[1])
                if cand < dp[j][k + 1]:
                    dp[j][k + 1] = cand
                    parent[j][k + 1] = (i, k)

    best_k, best_val = None, INF
    for k in range(n_vehicles + 1):
        if dp[n][k] < best_val:
            best_val = dp[n][k]
            best_k = k
    if best_k is None:
        # Kein gueltiger Split gefunden (z.B. ein einzelner Stopp ueberschreitet
        # bereits die Kapazitaet) - Fallback auf Greedy-Split.
        return decode_giant_tour(tour, demands, capacity, n_vehicles)

    segments = []
    cur_i, cur_k = n, best_k
    while cur_k > 0:
        pi, pk = parent[cur_i][cur_k]
        segments.append(tour[pi:cur_i])
        cur_i, cur_k = pi, pk
    segments.reverse()

    routes = [list(map(int, seg)) for seg in segments]
    while len(routes) < n_vehicles:
        routes.append([])
    infeasible = any(sum(demands[s] for s in r) > capacity for r in routes)
    return routes, infeasible


def genetic_algorithm_construction_seeded(
    n_stops, D, demands, capacity, n_vehicles, earliest, latest, service, tw_enabled,
    pop_size=GA_POP_SIZE, generations=GA_GENERATIONS, seed=0, seed_routes=None,
):
    """ÜBERHOLT, aber vollständig im Code belassen (getestet, nicht mehr an
    die Oberfläche angebunden) - dieselbe Konvention wie bei
    monobeam_vrp_construction. Ersetzt durch die neue
    genetic_algorithm_construction weiter unten, die GA direkt auf
    Savings-Fusionsentscheidungen operieren lässt statt auf Stopp-
    Permutationen - siehe README für die vollständige Herleitung, warum
    dieser Ansatz hier verworfen wurde (praktisch identische Qualität bei
    mehr als doppelt so langer Rechenzeit).

    Genetischer Algorithmus mit 'Giant-Tour'-Kodierung: ein Chromosom ist
    eine Permutation aller Stopps. Order Crossover (OX), Segment-Umkehr-
    Mutation ODER eine Or-opt-inspirierte Verschiebungs-Mutation,
    Elitismus, Turnierselektion.

    Die Or-opt-Mutation wurde nachträglich ergänzt und im Benchmark bestätigt
    (+3,9 % statt +5,3 % Abstand zu OR-Tools) - im Gegensatz zu einem
    ähnlichen Versuch bei Beam Search (siehe dort), der wieder verworfen
    wurde.

    AUF NUTZERANFRAGE ERGÄNZT (`seed_routes`, optional): nachdem sich
    zeigte, dass Beam Search als Metaheuristik gut mit Savings' Fusions-
    prinzip harmoniert (siehe beam_savings), die naheliegende Anschluss-
    frage: hilft dasselbe Prinzip auch GA, der anderen Metaheuristik hier?
    Getestet: die Anfangspopulation mit der bereits andernorts berechneten
    beam_savings-Lösung (statt komplett zufällig) zu impfen, hilft
    tatsächlich deutlich - 23 von 28 Siegen gegenüber unveränderter GA ohne
    Zeitfenster.

    Ein Struktur-Problem musste dafür erst gelöst werden: die Impf-Route
    wird als Riesentour übergeben (Routen einfach aneinandergehängt), aber
    `decode_giant_tour`s striktes Greedy-Split (nur Kapazität zählt, nicht
    die ursprünglichen Routengrenzen) verwässerte diese Struktur - Stopps
    wanderten über Routengrenzen hinweg. Das schwächte den Effekt bei
    Zeitfenstern besonders stark ab (nur 9 von 21 Siegen). Fix:
    `decode_giant_tour_optimal_split` (Prins 2004, kürzester-Pfad über alle
    möglichen Routensegmente) statt Greedy-Split - findet die beste
    Aufteilung unabhängig von der Eingabereihenfolge. Ergebnis mit
    Zeitfenstern: 15 von 21 Siegen (statt 9 von 21).

    Die optimale Dekodierung kostet spürbar mehr Rechenzeit (0,5-0,6ms statt
    Bruchteile einer Millisekunde je Aufruf) - bei den ~2000 Bewertungen
    einer vollen GA-Runde (Standardbreite pop_size=30, generations=40)
    summierte sich das auf ~1,9s statt ~264ms GA-Anteil bei Zeitfenstern.
    Ein Kompromiss (teure Dekodierung nur an wenigen Stellen: Seed-Start,
    einmal je Generation) war zwar schneller (~283ms), aber schwächer in
    der Qualität (12 statt 15 von 21 Siegen) - die Selektionsdruck-Schleife
    (Turnierauswahl, Crossover, Mutation) "wusste" ohne durchgängig
    korrekte Bewertung nicht zuverlässig genug, welche Kandidaten wirklich
    gut waren. Stattdessen: volle optimale Dekodierung überall, aber
    deutlich reduzierte Populationsgröße/Generationenzahl
    (GA_SEEDED_POP_SIZE=20, GA_SEEDED_GENERATIONS=15 statt 30/40) - der
    Seed gibt bereits einen starken Ausgangspunkt, weniger Generationen
    genügen zum Verfeinern. Ergebnis: sowohl schneller (~377-458ms
    GA-Anteil) ALS AUCH qualitativ besser (23/28 ohne, 15/21 mit
    Zeitfenstern) als der Kompromiss-Ansatz.

    `seed_routes=None` (Standard) bewahrt das bisherige Verhalten
    vollständig (komplett zufällige Anfangspopulation, Greedy-Split-
    Dekodierung, volle pop_size/generations) - Rückwärtskompatibilität für
    bestehenden Code, der ohne Seed aufruft."""
    if n_stops == 0:
        return [[] for _ in range(n_vehicles)], False
    if n_stops == 1:
        routes = [[0]] + [[] for _ in range(n_vehicles - 1)]
        return routes, demands[0] > capacity

    rng = np.random.default_rng(int(seed) + 5000)
    use_optimal_split = seed_routes is not None

    def decode(tour):
        if use_optimal_split:
            return decode_giant_tour_optimal_split(tour, D, demands, capacity, n_vehicles, earliest, latest, service, tw_enabled)
        return decode_giant_tour(tour, demands, capacity, n_vehicles)

    def fitness_key(tour):
        routes, _ = decode(tour)
        dist, viol = solution_totals(routes, D, earliest, latest, service, tw_enabled)
        return (viol, dist)

    if seed_routes is not None:
        seed_tour = [s for r in seed_routes for s in r]
        n_seeded = int(pop_size * 0.3)
        population = [seed_tour[:]]
        for _ in range(n_seeded - 1):
            t = seed_tour[:]
            for _ in range(rng.integers(1, 4)):
                i, j = rng.choice(n_stops, size=2, replace=False)
                t[i], t[j] = t[j], t[i]
            population.append(t)
        while len(population) < pop_size:
            population.append(rng.permutation(n_stops).tolist())
    else:
        population = [rng.permutation(n_stops).tolist() for _ in range(pop_size)]

    scores = [fitness_key(t) for t in population]

    def tournament():
        idxs = rng.choice(len(population), size=3, replace=False)
        best_i = min(idxs, key=lambda i: scores[i])
        return population[best_i]

    def ox_crossover(p1, p2):
        n = len(p1)
        a, b = sorted(rng.choice(n, size=2, replace=False))
        child = [-1] * n
        child[a:b] = p1[a:b]
        taken = set(p1[a:b])
        fill = [g for g in p2 if g not in taken]
        idx = 0
        for i in range(n):
            if child[i] == -1:
                child[i] = fill[idx]
                idx += 1
        return child

    def or_opt_mutate(tour, n_candidates=4):
        """Or-opt-inspirierte Mutation: nimmt einen zufälligen Stopp aus der
        Permutation und testet ihn an ein paar zufälligen anderen Positionen
        (auch weit entfernte, was nach dem Decode einem Fahrzeugwechsel
        entsprechen kann) - behält die beste gefundene."""
        n = len(tour)
        if n < 3:
            return tour
        i = int(rng.integers(0, n))
        stop = tour[i]
        remainder = tour[:i] + tour[i + 1 :]
        n_try = min(n_candidates, len(remainder) + 1)
        positions = rng.choice(len(remainder) + 1, size=n_try, replace=False)
        best_tour, best_key = tour, fitness_key(tour)
        for pos in positions:
            candidate = remainder[:pos] + [stop] + remainder[pos:]
            key = fitness_key(candidate)
            if key < best_key:
                best_key = key
                best_tour = candidate
        return best_tour

    def mutate(tour, rate=0.3):
        if len(tour) >= 2 and rng.random() < rate:
            if len(tour) >= 3 and rng.random() < 0.5:
                tour = or_opt_mutate(tour)
            else:
                tour = tour[:]
                i, j = sorted(rng.choice(len(tour), size=2, replace=False))
                tour[i : j + 1] = tour[i : j + 1][::-1]
        return tour

    best_idx = min(range(len(population)), key=lambda i: scores[i])
    best_tour, best_score = population[best_idx], scores[best_idx]

    for _ in range(generations):
        new_pop = [best_tour]
        while len(new_pop) < pop_size:
            child = mutate(ox_crossover(tournament(), tournament()))
            new_pop.append(child)
        population = new_pop
        scores = [fitness_key(t) for t in population]
        gen_best_idx = min(range(len(population)), key=lambda i: scores[i])
        if scores[gen_best_idx] < best_score:
            best_score = scores[gen_best_idx]
            best_tour = population[gen_best_idx]

    routes, infeasible = decode(best_tour)
    return routes, infeasible


def _route_time_window_violations(route, D, earliest, latest, service, tw_enabled):
    """Anzahl Zeitfenster-Verletzungen einer einzelnen Tour, ohne Distanz -
    Hilfsfunktion für genetic_algorithm_construction (Fusionsentscheidung)."""
    if not tw_enabled or not route:
        return 0
    _dist, viol, _timeline = evaluate_route(list(route), D, earliest, latest, service, True)
    return viol


def _decode_merge_priority(priority_perm, savings_list, D, demands, capacity, n_vehicles,
                            earliest, latest, service, tw_enabled):
    """Führt Savings-Fusionen in der durch priority_perm gegebenen
    Reihenfolge (eine Permutation der Indizes von savings_list) statt der
    festen, nach Ersparnis sortierten Reihenfolge durch - siehe
    genetic_algorithm_construction, deren Chromosom GENAU diese
    Prioritäts-Permutation ist. Eine Fusion wird nur akzeptiert, wenn sie
    weder Kapazität überschreitet NOCH die Zeitfenster-Verträglichkeit
    gegenüber den getrennten Routen verschlechtert (auf Nutzeranfrage
    ergänzt - siehe Docstring von genetic_algorithm_construction für die
    Historie, warum das nötig war)."""
    routes = {i: (i,) for i in range(len(demands))}
    route_of = list(range(len(demands)))
    loads = [float(d) for d in demands]

    for idx in priority_perm:
        _s_val, i, j = savings_list[idx]
        ri, rj = route_of[i], route_of[j]
        if ri == rj:
            continue
        route_i, route_j = routes[ri], routes[rj]
        if route_i[-1] != i or route_j[0] != j:
            continue
        if loads[ri] + loads[rj] > capacity:
            continue

        merged = route_i + route_j
        if tw_enabled:
            viol_before = (
                _route_time_window_violations(route_i, D, earliest, latest, service, True)
                + _route_time_window_violations(route_j, D, earliest, latest, service, True)
            )
            viol_after = _route_time_window_violations(merged, D, earliest, latest, service, True)
            if viol_after > viol_before:
                continue  # Fusion würde Zeitfenster-Verträglichkeit verschlechtern

        for st_ in route_j:
            route_of[st_] = ri
        routes[ri] = merged
        del routes[rj]
        loads[ri] += loads[rj]

    route_list = [list(r) for r in routes.values()]
    infeasible = any(sum(demands[s] for s in r) > capacity for r in route_list)
    while len(route_list) > n_vehicles:
        order = sorted(range(len(route_list)), key=lambda k: sum(demands[s] for s in route_list[k]))
        a, b = order[0], order[1]
        merged = route_list[a] + route_list[b]
        route_list = [r for k, r in enumerate(route_list) if k not in (a, b)] + [merged]
        if sum(demands[s] for s in merged) > capacity:
            infeasible = True
    while len(route_list) < n_vehicles:
        route_list.append([])
    return route_list, infeasible


def genetic_algorithm_construction(
    n_stops, D, demands, capacity, n_vehicles, earliest, latest, service, tw_enabled,
    pop_size=None, generations=None, seed=0,
):
    """Genetischer Algorithmus, der DIREKT auf Savings-Fusions-Priori-
    täten operiert statt auf Stopp-Permutationen (ersetzt die frühere,
    jetzt als genetic_algorithm_construction_seeded erhaltene Fassung -
    siehe dort und README für die vollständige Herleitung).

    AUF NUTZERANFRAGE UNTERSUCHT: nachdem sich zeigte, dass Beam Search als
    Metaheuristik gut mit Savings' Fusionsprinzip harmoniert (beam_savings),
    die naheliegende Frage: könnte dieselbe Kombination auch "auf einer
    generelleren Ebene" laufen? Vier verschiedene Verallgemeinerungen
    getestet:

    1. Vielfältige Beam-Search-Kandidaten als GA-Startpopulation nutzen -
       verworfen: beam_savings' interner Beam konvergiert typischerweise
       auf nur 1-3 tatsächlich unterschiedliche Endkandidaten, zu wenig
       Vielfalt für eine ganze Population.
    2. Routenbewusster Crossover (Route Exchange, ganze Touren zwischen
       Eltern austauschen) statt reinem Permutations-Order-Crossover (OX)
       - kein klarer Vorteil (9 von 15 Siegen für reines OX, meist
       identische Endwerte - die lokale Suche danach glättet die
       Unterschiede offenbar).
    3. Mehrere Konstruktionsquellen (Sweep, Savings, beam_savings) statt
       nur einer als Startpopulation impfen - praktisch kein Unterschied
       (26 von 28 Gleichständen) - beam_savings' Ergebnis dominiert die
       Population ohnehin schnell, die zusätzlichen Quellen tragen kaum
       etwas bei.
    4. GA DIREKT auf Savings-Fusions-Prioritäten operieren lassen (dieses
       Chromosom hier) statt auf Stopp-Permutationen - GA erkundet damit
       DENSELBEN Entscheidungsraum, den auch beam_savings durchsucht, aber
       evolutionär statt mit fester Beam-Breite. Vielversprechend: ohne
       Zeitfenster leicht im Vorteil UND deutlich schneller (98ms, keine
       teure beam_savings-Vorberechnung nötig, komplett eigenständig) -
       aber mit Zeitfenstern zunächst deutlich schlechter (6 von 20
       Siegen), weil der Fusionsprozess selbst noch keine Zeitfenster-
       Verträglichkeit prüfte (dieselbe Lücke, die beam_savings vor seiner
       eigenen Zeitfenster-Korrektur hatte).

    Fix, analog zum beam_savings-Zeitfenster-Fix: die Fusionsentscheidung
    selbst (_decode_merge_priority) prüft jetzt, ob eine Fusion die
    Zeitfenster-Verträglichkeit gegenüber den getrennten Routen
    verschlechtern würde, und lehnt sie in diesem Fall ab - die GA-
    evolvierte Prioritätsreihenfolge findet dadurch selbstständig
    zeitfenster-verträgliche Fusionen. Ergebnis nach dem Fix: 20 von 20
    Siegen gegen die Zählung der alten seed_routes-Fassung (9+11 aus zwei
    Stichproben, 9 Gleichstände) - praktisch IDENTISCHE Qualität, aber
    mehr als doppelt so schnell (897ms statt 2067ms bei 30 Stopps mit
    Zeitfenstern), da weder beam_savings als Vorberechnung noch die
    aufwändige optimale Split-Dekodierung (decode_giant_tour_optimal_split)
    benötigt werden - das Chromosom IST bereits eine Permutation über
    Fusionsentscheidungen, keine Stopp-Reihenfolge, die erst noch in
    Routen zerlegt werden müsste.

    EIN FÜNFTER FUND beim Neu-Vermessen der Benchmark-Tabelle: ein
    deutlicher Ausreißer (+26,2 % statt der erwarteten ~0,4 % Abstand zu
    OR-Tools) bei einer bestimmten Szenario/Seed-Kombination. Untersucht:
    GAs internes Rohergebnis (VOR lokaler Suche) war tatsächlich BESSER
    als beam_savings (438,7 vs. 441,0) - aber NACH lokaler Suche deutlich
    schlechter (553,0 vs. 441,0), obwohl lokale Suche eigentlich nie
    verschlechtern sollte. Ursache gefunden: das Rohergebnis war
    kapazitätsverletzt (eine Route hatte 39 statt maximal 35 Einheiten
    Last) - lokale Suche priorisiert korrekt die Kapazitätsreparatur vor
    Distanz (siehe find_or_opt_move), was hier zusätzliche Distanz
    kostete. Der eigentliche Fehler lag in `fitness_key`: sie bewertete
    nur `(Zeitfenster-Verletzungen, Distanz)` - Kapazität floss überhaupt
    nicht in die Bewertung ein, GA hatte dadurch keinerlei evolutionären
    Druck, kapazitätsverletzte Prioritätsreihenfolgen zu vermeiden. Fix:
    `solution_capacity_excess` als ranghöchstes Kriterium ergänzt,
    `fitness_key` liefert jetzt `(Kapazitätsüberschreitung, Zeitfenster-
    Verletzungen, Distanz)` - dieselbe lexikografische Priorität wie
    überall sonst in dieser Demo. Ergebnis: der Ausreißer verschwand
    vollständig (alle 5 internen Test-Seeds landen jetzt konsistent bei
    443,5 statt zuvor meist 553,0), Gesamt-Benchmark verbesserte sich von
    +2,3 % auf +0,7 % Abstand zu OR-Tools.

    Eine kleine Zahl (~9 % der getesteten Instanzen mit knapper
    Fahrzeuganzahl) liefert weiterhin ein kapazitätsverletztes
    Rohergebnis - verifiziert, dass dies KEINE GA-spezifische Schwäche
    ist: Savings und beam_savings zeigen dasselbe Verhalten bei denselben
    Instanzen (die Zwangs-Konsolidierung bei zu wenigen Fahrzeugen kann
    strukturell nicht immer Kapazität einhalten) - lokale Suche repariert
    das wie bei den anderen Methoden auch.

    Robustheit über eine breite Parameterspanne verifiziert (n_stops 5-30,
    n_vehicles 1-5, inklusive Randfällen) - keine Ausnahmen, stets
    vollständige Stopp-Abdeckung.

    EIN SIEBTER FUND, auf Nutzeranfrage untersucht: analog zu
    BEAM_WIDTH_NO_TW bei beam_savings geprüft, ob eine bedingte
    Parameterwahl (größere Population/mehr Generationen, wenn günstiger)
    auch hier hilft. Kostenvergleich: GA kostet ohne Zeitfenster nur
    ~113ms, mit Zeitfenstern ~1586ms (14x teurer, ein noch größerer
    Unterschied als bei beam_savings) - viel Spielraum für aufwändigere
    Suche im günstigeren Fall. Ergebnis: DEUTLICH stärkerer Effekt als bei
    beam_savings' Breitenerhöhung (dort 12 % der Fälle, +4 %) - 40 % der
    Testfälle (20 von 50) profitieren von größerer Population/mehr
    Generationen, im Schnitt um 2,9 %, bei 455ms statt 113ms (Gesamtzeit
    aller vier Methoden zusammen: ~814ms, vertretbar). Umgesetzt:
    GA_NO_TW_POP_SIZE=40/GA_NO_TW_GENERATIONS=30 ohne Zeitfenster,
    GA_SEEDED_POP_SIZE=20/GA_SEEDED_GENERATIONS=15 bleiben mit
    Zeitfenstern (siehe README).

    ZUR MONOTONIE-FRAGE (auf Nutzeranfrage geprüft, siehe README): anders
    als beam_savings hat GA KEINE echte strukturelle Monotonie-Garantie.
    Verifiziert: die rohe fitness_key-Bewertung IST monoton in
    `generations` (durch Elitismus + deterministische Zufallssequenz -
    mehr Generationen können den intern verfolgten Bestwert nie
    verschlechtern), aber NICHT in `pop_size` (eine größere Population
    verbraucht die Zufallszahlen-Sequenz grundlegend anders, kein
    "enthält die kleinere Population vollständig"-Verhältnis wie bei
    beam_savings' Breite). Und selbst die generations-Monotonie auf
    Rohebene überträgt sich NICHT verlässlich auf das Ergebnis NACH
    lokaler Suche (12 % Verletzungen gemessen) - ein Korrekturversuch
    (periodische Nachprüfung mit echter lokaler Suche) wurde nach
    Rücksprache verworfen: er hätte die Verletzungen nur in der
    getesteten Stichprobe beseitigt, ohne eine tatsächlich bewiesene
    Garantie herzustellen (die Prüfpunkte hingen von der genauen
    Generationenzahl ab, kein instanzunabhängiger struktureller Beweis
    wie bei beam_savings' Verschachtelungsarchitektur). Fazit: GAs
    "mehr Aufwand hilft tendenziell" ist ein empirischer Trend, keine
    mathematische Garantie - im Gegensatz zu beam_savings."""
    if pop_size is None:
        pop_size = GA_SEEDED_POP_SIZE if tw_enabled else GA_NO_TW_POP_SIZE
    if generations is None:
        generations = GA_SEEDED_GENERATIONS if tw_enabled else GA_NO_TW_GENERATIONS
    if n_stops == 0:
        return [[] for _ in range(n_vehicles)], False
    if n_stops == 1:
        routes = [[0]] + [[] for _ in range(n_vehicles - 1)]
        return routes, demands[0] > capacity

    rng = np.random.default_rng(int(seed) + 5000)

    savings_list = []
    for i in range(n_stops):
        for j in range(i + 1, n_stops):
            s_ij = D[0][i + 1] + D[0][j + 1] - D[i + 1][j + 1]
            s_ji = D[0][j + 1] + D[0][i + 1] - D[j + 1][i + 1]
            savings_list.append((s_ij, i, j))
            savings_list.append((s_ji, j, i))
    m = len(savings_list)
    natural_order = sorted(range(m), key=lambda k: -savings_list[k][0])

    def fitness_key(perm):
        routes, _ = _decode_merge_priority(
            perm, savings_list, D, demands, capacity, n_vehicles, earliest, latest, service, tw_enabled,
        )
        dist, viol = solution_totals(routes, D, earliest, latest, service, tw_enabled)
        cap_excess = solution_capacity_excess(routes, demands, capacity)
        return (cap_excess, viol, dist)

    # Population: die NATÜRLICHE Savings-Reihenfolge (entspricht Breite-1-
    # Beam Search) plus Mutationen davon fürs "Impfen", plus zufällige
    # Permutationen für Diversität.
    population = [natural_order[:]]
    for _ in range(int(pop_size * 0.3) - 1):
        t = natural_order[:]
        for _ in range(rng.integers(1, 6)):
            i, j = rng.choice(m, size=2, replace=False)
            t[i], t[j] = t[j], t[i]
        population.append(t)
    while len(population) < pop_size:
        population.append(rng.permutation(m).tolist())

    scores = [fitness_key(p) for p in population]

    def tournament():
        idxs = rng.choice(len(population), size=3, replace=False)
        best_i = min(idxs, key=lambda i: scores[i])
        return population[best_i]

    def ox_crossover(p1, p2):
        n = len(p1)
        a, b = sorted(rng.choice(n, size=2, replace=False))
        child = [-1] * n
        child[a:b] = p1[a:b]
        taken = set(p1[a:b])
        fill = [g for g in p2 if g not in taken]
        idx = 0
        for i in range(n):
            if child[i] == -1:
                child[i] = fill[idx]
                idx += 1
        return child

    def insertion_mutate(perm, n_candidates=4):
        """Analog zu or_opt_mutate der überholten Stopp-Permutations-GA:
        nimmt einen zufälligen Eintrag aus der Prioritäts-Permutation und
        testet ihn an ein paar zufälligen anderen Positionen, behält die
        beste gefundene. Auf Nutzeranfrage ergänzt, nachdem sich zeigte,
        dass reine Segment-Umkehr-Mutation bei manchen Instanzen in einem
        klar suboptimalen lokalen Optimum steckenblieb (Benchmark-Fund:
        Seed 14 bei n=15/v=3/cap=35 lieferte mit reiner Segment-Umkehr
        553,0 statt der mit anderem internen Seed erreichbaren 443,5, nahe
        an beam_savings' 441,0 - ein deutliches Robustheitsproblem ohne
        diese zweite Mutationsart)."""
        n = len(perm)
        if n < 3:
            return perm
        i = int(rng.integers(0, n))
        val = perm[i]
        remainder = perm[:i] + perm[i + 1 :]
        n_try = min(n_candidates, len(remainder) + 1)
        positions = rng.choice(len(remainder) + 1, size=n_try, replace=False)
        best_perm, best_key = perm, fitness_key(perm)
        for pos in positions:
            candidate = remainder[:pos] + [val] + remainder[pos:]
            key = fitness_key(candidate)
            if key < best_key:
                best_key = key
                best_perm = candidate
        return best_perm

    def mutate(perm, rate=0.3):
        if rng.random() < rate:
            if len(perm) >= 3 and rng.random() < 0.5:
                perm = insertion_mutate(perm)
            else:
                perm = perm[:]
                i, j = sorted(rng.choice(len(perm), size=2, replace=False))
                perm[i : j + 1] = perm[i : j + 1][::-1]
        return perm

    best_idx = min(range(len(population)), key=lambda i: scores[i])
    best_perm, best_score = population[best_idx], scores[best_idx]

    for _ in range(generations):
        new_pop = [best_perm]
        while len(new_pop) < pop_size:
            child = mutate(ox_crossover(tournament(), tournament()))
            new_pop.append(child)
        population = new_pop
        scores = [fitness_key(t) for t in population]
        gen_best_idx = min(range(len(population)), key=lambda i: scores[i])
        if scores[gen_best_idx] < best_score:
            best_score = scores[gen_best_idx]
            best_perm = population[gen_best_idx]

    routes, infeasible = _decode_merge_priority(
        best_perm, savings_list, D, demands, capacity, n_vehicles, earliest, latest, service, tw_enabled,
    )
    return routes, infeasible
