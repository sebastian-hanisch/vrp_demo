"""
Kombinierte lokale Suche (2-opt + Or-opt), lexikografisch zuerst nach
Kapazitätsüberschreitung, dann nach Zeitfenster-Verletzungen, dann nach
Distanz optimiert. Auf Nutzeranfrage ergänzt: Kapazität war vorher keine
eigene Optimierungsgröße, nur ein Freigabefilter für Or-opt-Zielrouten -
dadurch konnte eine kapazitätsverletzte Konstruktion auch nach der lokalen
Suche verletzt bleiben, selbst wenn der Gesamtbedarf klar unter der
Gesamtkapazität lag (siehe find_or_opt_move und README). Wird von allen
vier eigenen Konstruktionsheuristiken (Sweep, Savings, Beam Search, GA) im
Anschluss an die Konstruktion verwendet, um eine gemeinsame, faire
Vergleichsgrundlage zu schaffen.
"""

from vrp_constants import EPS, LOCAL_SEARCH_MAX_MOVES, OR_OPT_SEG_LENGTHS
from vrp_evaluation import evaluate_route, route_capacity_excess, solution_capacity_excess, solution_totals


def find_two_opt_move(routes, D, earliest, latest, service, tw_enabled):
    """Sucht EINE verbessernde 2-opt-Vertauschung innerhalb einer beliebigen
    Fahrzeugtour (erste gefundene Verbesserung)."""
    for v, route in enumerate(routes):
        if len(route) < 2:
            continue
        base_dist, base_viol, _ = evaluate_route(route, D, earliest, latest, service, tw_enabled)
        for i in range(len(route) - 1):
            for j in range(i + 1, len(route)):
                cand = route[:i] + route[i : j + 1][::-1] + route[j + 1 :]
                cand_dist, cand_viol, _ = evaluate_route(cand, D, earliest, latest, service, tw_enabled)
                if cand_viol < base_viol or (cand_viol == base_viol and cand_dist < base_dist - EPS):
                    new_routes = [r[:] for r in routes]
                    new_routes[v] = cand
                    return new_routes, True
    return routes, False


def find_or_opt_move(routes, D, demands, capacity, earliest, latest, service, tw_enabled, seg_lengths=OR_OPT_SEG_LENGTHS, theoretical_min_excess=0.0):
    """Sucht EINEN verbessernden Or-opt-Zug: ein kurzes Segment (1-2 Stopps)
    wird aus einer Tour entfernt und an der besten Position wieder
    eingefügt - auch in einer anderen Fahrzeugtour. Das behebt die zentrale
    Schwäche von reinem 2-opt, das Stopps nie zwischen Fahrzeugen verschieben
    kann.

    `theoretical_min_excess` (Gesamtbedarf minus Gesamtkapazität, falls
    positiv) ist die kleinstmögliche Kapazitätsüberschreitung, die JEDE
    Anordnung mindestens hat - bei genuin unlösbaren Instanzen (Gesamtbedarf
    übersteigt Gesamtkapazität) kann keine Umverteilung sie unterschreiten.
    Ist die aktuelle Überschreitung bereits bei dieser Untergrenze
    angekommen, lohnt sich die teure Vollauswertung nicht mehr (siehe
    README für den gefundenen, sonst nutzlos wiederholten Rechenaufwand bei
    hoffnungslosen Instanzen).

    WICHTIG, auf Nutzeranfrage korrigiert: eine frühere Fassung blockierte
    jeden Zug, der die ZIEL-Tour über die Kapazität gebracht hätte
    (`if target_load + seg_demand > capacity: continue`), unabhängig davon,
    ob die QUELL-Tour dadurch entlastet worden wäre. War die Quelle bereits
    überladen und die einzige entlastende Verschiebung hätte das Ziel (noch
    stärker oder überhaupt) über die Kapazität gebracht, verhinderte dieser
    harte Filter genau die Züge, die die Verletzung insgesamt verringert
    hätten - die lokale Suche konnte dadurch bei manchen Instanzen dauerhaft
    in einem kapazitätsverletzten Zustand steckenbleiben, obwohl der
    Gesamtbedarf klar unter der Gesamtkapazität lag (empirisch: ~21% der
    getesteten Instanzen zeigten das).

    Fix: kein harter Filter mehr, stattdessen lexikografischer Vergleich wie
    bei Zeitfenster-Verletzungen, nur mit Kapazität als ranghöchster Stufe:
    (Kapazitätsüberschreitung, Zeitfenster-Verletzungen, Distanz). Ein Zug
    wird akzeptiert, wenn er die Kapazitätsüberschreitung verringert - auch
    wenn er Distanz oder Zeitfenster verschlechtert -, sonst bei gleicher
    Kapazitätsüberschreitung nach denselben Regeln wie zuvor."""
    n_vehicles = len(routes)
    system_total_excess = solution_capacity_excess(routes, demands, capacity)
    capacity_floor_reached = system_total_excess <= theoretical_min_excess + EPS
    for v_from in range(n_vehicles):
        route_from = routes[v_from]
        for seg_len in seg_lengths:
            if seg_len > len(route_from):
                continue
            for start in range(len(route_from) - seg_len + 1):
                segment = route_from[start : start + seg_len]
                remainder = route_from[:start] + route_from[start + seg_len :]
                base_from_dist, base_from_viol, _ = evaluate_route(route_from, D, earliest, latest, service, tw_enabled)
                base_from_cap = route_capacity_excess(route_from, demands, capacity)

                for v_to in range(n_vehicles):
                    if v_to == v_from:
                        target = remainder
                        base_dist, base_viol = base_from_dist, base_from_viol
                        base_cap = base_from_cap
                    else:
                        target = routes[v_to]
                        if base_from_cap <= 0 or capacity_floor_reached:
                            # Schnellausstieg fuer den Regelfall: entweder ist
                            # die Quelle bereits zulaessig, ODER die
                            # Gesamtueberschreitung im System hat bereits die
                            # theoretische Untergrenze erreicht (keine
                            # Anordnung kann sie weiter senken, siehe
                            # Docstring) - in beiden Faellen kann ein Zug
                            # ueber die Ziel-Kapazitaet hinaus nie eine
                            # Verbesserung der Gesamt-Kapazitaet sein.
                            target_load = sum(demands[s] for s in target)
                            seg_demand = sum(demands[s] for s in segment)
                            if target_load + seg_demand > capacity:
                                continue
                        base_to_dist, base_to_viol, _ = evaluate_route(target, D, earliest, latest, service, tw_enabled)
                        base_to_cap = route_capacity_excess(target, demands, capacity)
                        base_dist, base_viol = base_from_dist + base_to_dist, base_from_viol + base_to_viol
                        base_cap = base_from_cap + base_to_cap

                    for pos in range(len(target) + 1):
                        if v_to == v_from and pos == start:
                            continue  # entspricht exakt der Ursprungsposition -> kein echter Zug
                        new_target = target[:pos] + segment + target[pos:]

                        if v_to == v_from:
                            new_cap = route_capacity_excess(new_target, demands, capacity)
                        else:
                            new_cap = route_capacity_excess(remainder, demands, capacity) + route_capacity_excess(new_target, demands, capacity)

                        # Kapazitaetsueberschreitung haengt nur von der
                        # Bedarfssumme ab, nicht von der Position - bei
                        # eindeutig schlechterer Kapazitaet kann KEINE
                        # Position eine Verbesserung sein (lexikografisch
                        # sofort abgelehnt), das teure evaluate_route lohnt
                        # sich dann nicht (deutliche Zeitersparnis im
                        # Kapazitaets-Reparatur-Fall, siehe README).
                        if new_cap > base_cap + EPS:
                            continue

                        if v_to == v_from:
                            new_dist, new_viol, _ = evaluate_route(new_target, D, earliest, latest, service, tw_enabled)
                        else:
                            rem_dist, rem_viol, _ = evaluate_route(remainder, D, earliest, latest, service, tw_enabled)
                            tgt_dist, tgt_viol, _ = evaluate_route(new_target, D, earliest, latest, service, tw_enabled)
                            new_dist, new_viol = rem_dist + tgt_dist, rem_viol + tgt_viol

                        better = (
                            new_cap < base_cap - EPS
                            or (abs(new_cap - base_cap) <= EPS and new_viol < base_viol)
                            or (abs(new_cap - base_cap) <= EPS and new_viol == base_viol and new_dist < base_dist - EPS)
                        )
                        if better:
                            new_routes = [r[:] for r in routes]
                            if v_to == v_from:
                                new_routes[v_from] = new_target
                            else:
                                new_routes[v_from] = remainder
                                new_routes[v_to] = new_target
                            return new_routes, True
    return routes, False


def find_swap_move(routes, D, demands, capacity, earliest, latest, service, tw_enabled):
    """Sucht EINEN verbessernden Tausch-Zug: ein einzelner Stopp aus einer
    Tour wird gegen einen einzelnen Stopp einer ANDEREN Tour getauscht.

    Auf Nutzeranfrage ergänzt, nachdem sich zeigte, dass selbst die um
    Kapazitäts-Priorität erweiterte Or-opt-Suche (siehe find_or_opt_move)
    manche kapazitätsverletzten Instanzen nicht lösen konnte: Or-opt kann
    nur EINFÜGEN, nie gleichzeitig etwas aus der Zielroute ENTFERNEN. Ist
    eine Route überladen und die freie Kapazität JEDER anderen Route kleiner
    als der kleinste verschiebbare Stopp, findet Or-opt keinen entlastenden
    Zug - ein echter Tausch (ein Stopp raus, ein anderer rein) kann trotzdem
    funktionieren, wenn der eingetauschte Stopp einen kleineren Bedarf hat.
    Konkretes Beispiel, das dadurch gelöst wird: Route A=26 (Kapazität 25,
    kleinster Stopp dort hat Bedarf 8), Route B=18 mit nur 7 freier
    Kapazität - kein Or-opt-Zug möglich, aber ein Tausch von As Stopp
    (Bedarf 8) gegen Bs kleinsten Stopp (Bedarf 2) bringt beide Routen unter
    die Kapazität.

    Dieselbe lexikografische Priorität wie find_or_opt_move: Kapazität
    zuerst, dann Zeitfenster-Verletzungen, dann Distanz."""
    n_vehicles = len(routes)
    route_excess = [route_capacity_excess(r, demands, capacity) for r in routes]
    for v1 in range(n_vehicles):
        route1 = routes[v1]
        for v2 in range(v1 + 1, n_vehicles):
            if route_excess[v1] <= 0 and route_excess[v2] <= 0:
                # Eine Verringerung der Gesamt-Kapazitaetsueberschreitung
                # erfordert, dass mindestens eine der beiden Routen bereits
                # ueberladen ist - zwei bereits zulaessige Routen ueberspringen
                # (deutliche Suchraum-Reduktion, siehe README fuer die
                # gemessene Zeitersparnis).
                continue
            route2 = routes[v2]
            base1_dist, base1_viol, _ = evaluate_route(route1, D, earliest, latest, service, tw_enabled)
            base2_dist, base2_viol, _ = evaluate_route(route2, D, earliest, latest, service, tw_enabled)
            base_dist, base_viol = base1_dist + base2_dist, base1_viol + base2_viol
            base_cap = route_capacity_excess(route1, demands, capacity) + route_capacity_excess(route2, demands, capacity)

            for i1, stop1 in enumerate(route1):
                for i2, stop2 in enumerate(route2):
                    new_route1 = route1[:i1] + [stop2] + route1[i1 + 1 :]
                    new_route2 = route2[:i2] + [stop1] + route2[i2 + 1 :]

                    new1_dist, new1_viol, _ = evaluate_route(new_route1, D, earliest, latest, service, tw_enabled)
                    new2_dist, new2_viol, _ = evaluate_route(new_route2, D, earliest, latest, service, tw_enabled)
                    new_dist, new_viol = new1_dist + new2_dist, new1_viol + new2_viol
                    new_cap = route_capacity_excess(new_route1, demands, capacity) + route_capacity_excess(new_route2, demands, capacity)

                    better = (
                        new_cap < base_cap - EPS
                        or (abs(new_cap - base_cap) <= EPS and new_viol < base_viol)
                        or (abs(new_cap - base_cap) <= EPS and new_viol == base_viol and new_dist < base_dist - EPS)
                    )
                    if better:
                        new_routes = [r[:] for r in routes]
                        new_routes[v1] = new_route1
                        new_routes[v2] = new_route2
                        return new_routes, True
    return routes, False


def local_search_history(routes, D, demands, capacity, earliest, latest, service, tw_enabled, max_moves=LOCAL_SEARCH_MAX_MOVES):
    """Kombinierte lokale Suche: versucht in jedem Schritt zuerst einen
    günstigeren 2-opt-Zug (billiger), dann einen Or-opt-Zug (kann Stopps
    zwischen Fahrzeugen verschieben), erst wenn keiner von beiden mehr
    etwas findet, einen Tausch-Zug (find_swap_move - kann kapazitätsverletzte
    Routen entlasten, wo Or-opts reines Einfügen an fehlender freier
    Kapazität in jeder anderen Route scheitert). Stoppt, wenn keine der drei
    Nachbarschaften mehr eine Verbesserung liefert. 2-opt selbst kann die
    Kapazität nie verändern (nur Reihenfolge innerhalb EINER Tour), Or-opt
    und Tausch schon - siehe find_or_opt_move und find_swap_move für die auf
    Nutzeranfrage ergänzte Kapazitäts-Priorisierung.

    Jeder Eintrag der zurückgegebenen History ist jetzt
    (Routen-Snapshot, Distanz, Zeitfenster-Verletzungen,
    Kapazitätsüberschreitung) - der vierte Wert wurde auf Nutzeranfrage
    ergänzt, damit aufrufender Code den TATSÄCHLICH angezeigten
    (Nach-lokaler-Suche-)Kapazitätsstatus prüfen kann, statt sich auf den
    separat mitgeführten, nur die KONSTRUKTION betreffenden infeasible-Wert
    zu verlassen (der nach lokaler Suche veraltet sein konnte - siehe
    README)."""
    current = [r[:] for r in routes]
    total_dist, total_viol = solution_totals(current, D, earliest, latest, service, tw_enabled)
    total_cap = solution_capacity_excess(current, demands, capacity)
    history = [([r[:] for r in current], total_dist, total_viol, total_cap)]
    moves = 0

    # Kleinstmoegliche Kapazitaetsueberschreitung, die JEDE Anordnung
    # mindestens hat, wenn der Gesamtbedarf die Gesamtkapazitaet uebersteigt
    # - bei genuin unloesbaren Instanzen (z.B. zu wenige Fahrzeuge fuer die
    # Nachfrage) kann keine Umverteilung sie unterschreiten. Einmal
    # berechnet, spart bei solchen Instanzen wiederholten nutzlosen
    # Rechenaufwand (siehe find_or_opt_move-Docstring und README).
    theoretical_min_excess = max(0.0, sum(demands) - capacity * len(routes))

    while moves < max_moves:
        new_routes, found = find_two_opt_move(current, D, earliest, latest, service, tw_enabled)
        if not found:
            new_routes, found = find_or_opt_move(
                current, D, demands, capacity, earliest, latest, service, tw_enabled,
                theoretical_min_excess=theoretical_min_excess,
            )
        current_cap = solution_capacity_excess(current, demands, capacity)
        if not found and current_cap > theoretical_min_excess + EPS:
            # Tausch-Zug ist deutlich teurer als 2-opt/Or-opt (O(Fahrzeuge^2 x
            # Stopps^2)) und dient ausschließlich der Kapazitätsentlastung -
            # nur versuchen, wenn tatsächlich noch eine Verbesserung der
            # Gesamtueberschreitung MÖGLICH ist (nicht nur "> 0", sondern über
            # der theoretischen Untergrenze), sonst unnötiger Rechenaufwand
            # ohne jede Erfolgsaussicht (siehe README für die gemessene
            # Zeitersparnis bei genuin unlösbaren Instanzen).
            new_routes, found = find_swap_move(current, D, demands, capacity, earliest, latest, service, tw_enabled)
        if not found:
            break
        current = new_routes
        moves += 1
        total_dist, total_viol = solution_totals(current, D, earliest, latest, service, tw_enabled)
        total_cap = solution_capacity_excess(current, demands, capacity)
        history.append(([r[:] for r in current], total_dist, total_viol, total_cap))

    return history
