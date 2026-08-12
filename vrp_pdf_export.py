"""
Erzeugt einen einsatzfähigen Tourenplan als downloadbares PDF (in-memory,
kein Zwischenspeichern auf Disk nötig).
"""

import time

from vrp_constants import DEFAULT_CO2_PER_KM, DEFAULT_COST_PER_KM, DEFAULT_SPEED_KMH
from vrp_evaluation import distance_to_business, route_timeline, solution_totals


def generate_tour_plan_pdf(label, routes, ids, demands, D, earliest, latest, service, tw_enabled, capacity, speed_kmh=DEFAULT_SPEED_KMH, cost_per_km=DEFAULT_COST_PER_KM, co2_per_km=DEFAULT_CO2_PER_KM):
    """Erzeugt einen einsatzfähigen Tourenplan als PDF (in-memory, kein
    Zwischenspeichern auf Disk nötig) - eine Seite Zusammenfassung + eine
    Stopp-Tabelle je Fahrzeug."""
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    total_dist, total_viol = solution_totals(routes, D, earliest, latest, service, tw_enabled)
    total_hours, total_cost, total_co2 = distance_to_business(total_dist, speed_kmh, cost_per_km, co2_per_km)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, f"Tourenplan - {label}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6, f"Erstellt: {time.strftime('%d.%m.%Y %H:%M')} Uhr", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Zusammenfassung", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Gesamtdistanz: {total_dist:.1f} km", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"Geschaetzte Fahrzeit: {total_hours:.1f} h (bei {speed_kmh} km/h)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"Geschaetzte Kraftstoffkosten: {total_cost:.0f} EUR (bei {cost_per_km:.2f} EUR/km)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"Geschaetzter CO2-Ausstoss: {total_co2:.0f} kg (bei {co2_per_km:.2f} kg/km)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"Fahrzeuge im Einsatz: {sum(1 for r in routes if r)} von {len(routes)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if tw_enabled:
        pdf.cell(0, 6, f"Zeitfenster-Verletzungen: {total_viol}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    for v, route in enumerate(routes):
        if not route:
            continue
        load = sum(demands[s] for s in route)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, f"Fahrzeug {v + 1}  ({load:.0f}/{capacity:.0f}, {len(route)} Stopps)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        if tw_enabled:
            headers = ["#", "Stopp-ID", "Ankunft", "Fenster", "Status"]
            widths = [10, 30, 25, 40, 30]
        else:
            headers = ["#", "Stopp-ID", "Bedarf"]
            widths = [12, 40, 40]

        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(235, 235, 235)
        for h, w in zip(headers, widths):
            pdf.cell(w, 7, h, border=1, fill=True, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.ln(7)

        pdf.set_font("Helvetica", "", 9)
        if tw_enabled:
            for i, entry in enumerate(route_timeline(route, D, earliest, latest, service)):
                s = entry["stop"]
                row = [
                    str(i + 1), str(ids[s]), f"{entry['start']:.1f}",
                    f"{earliest[s]:.0f}-{latest[s]:.0f}", "Verletzt" if entry["violation"] else "OK",
                ]
                for val, w in zip(row, widths):
                    pdf.cell(w, 6, val, border=1, new_x=XPos.RIGHT, new_y=YPos.TOP)
                pdf.ln(6)
        else:
            for i, s in enumerate(route):
                row = [str(i + 1), str(ids[s]), f"{demands[s]:.0f}"]
                for val, w in zip(row, widths):
                    pdf.cell(w, 6, val, border=1, new_x=XPos.RIGHT, new_y=YPos.TOP)
                pdf.ln(6)
        pdf.ln(5)

    return bytes(pdf.output())
