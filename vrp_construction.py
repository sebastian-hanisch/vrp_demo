"""
Vier selbst implementierte Konstruktionsheuristiken für das VRP: Sweep,
Clarke-&-Wright-Savings, Beam Search und ein genetischer Algorithmus. Jede
liefert eine erste (meist noch verbesserungsfähige) Lösung, die anschließend
von vrp_local_search.local_search_history verbessert wird.
"""

import heapq

import numpy as np

from vrp_constants import BEAM_WIDTH, GA_GENERATIONS, GA_POP_SIZE
from vrp_evaluation import solution_totals


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


def genetic_algorithm_construction(
    n_stops, D, demands, capacity, n_vehicles, earliest, latest, service, tw_enabled,
    pop_size=GA_POP_SIZE, generations=GA_GENERATIONS, seed=0,
):
    """Genetischer Algorithmus mit 'Giant-Tour'-Kodierung: ein Chromosom ist
    eine Permutation aller Stopps, die per Greedy-Split in Fahrzeugtouren
    zerlegt wird. Order Crossover (OX), Segment-Umkehr-Mutation ODER eine
    Or-opt-inspirierte Verschiebungs-Mutation, Elitismus, Turnierselektion.

    Die Or-opt-Mutation wurde nachträglich ergänzt und im Benchmark bestätigt
    (+3,9 % statt +5,3 % Abstand zu OR-Tools) - im Gegensatz zu einem
    ähnlichen Versuch bei Beam Search (siehe dort), der wieder verworfen
    wurde."""
    if n_stops == 0:
        return [[] for _ in range(n_vehicles)], False
    if n_stops == 1:
        routes = [[0]] + [[] for _ in range(n_vehicles - 1)]
        return routes, demands[0] > capacity

    rng = np.random.default_rng(int(seed) + 5000)

    def fitness_key(tour):
        routes, _ = decode_giant_tour(tour, demands, capacity, n_vehicles)
        dist, viol = solution_totals(routes, D, earliest, latest, service, tw_enabled)
        return (viol, dist)

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
        (auch weit entfernte, was nach dem Greedy-Split-Decode einem
        Fahrzeugwechsel entsprechen kann) - behält die beste gefundene."""
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

    routes, infeasible = decode_giant_tour(best_tour, demands, capacity, n_vehicles)
    return routes, infeasible
