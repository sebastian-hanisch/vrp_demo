"""
Feedback-Logging für die Frage "War diese Demo hilfreich?" - testet die im
Businessplan vorgesehene Resonanz-Frage für die Weiterentwicklung von Demo
zu Produkt.

Hinweis für den produktiven Einsatz: Auf Streamlit Community Cloud ist das
Dateisystem nicht dauerhaft persistent (Reset bei Neustart/Redeploy). Für
zuverlässige Langzeit-Auswertung eignet sich z. B. eine Anbindung an ein
Google Sheet oder eine kleine Datenbank besser als diese CSV-Lösung.
"""

import csv
import os
import time

from vrp_constants import FEEDBACK_FILE


def log_feedback(vote, feedback_file=FEEDBACK_FILE):
    """Loggt eine Feedback-Stimme in eine lokale CSV. Best-effort: schlägt der
    Schreibzugriff fehl (z. B. schreibgeschütztes Dateisystem beim Hosting),
    wird das still ignoriert - das Feedback-UI funktioniert trotzdem, nur ohne
    Persistenz."""
    try:
        file_exists = os.path.exists(feedback_file)
        with open(feedback_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["timestamp", "vote"])
            writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), vote])
        return True
    except Exception:
        return False


def get_feedback_counts(feedback_file=FEEDBACK_FILE):
    """Zählt positive/negative Stimmen aus der Feedback-CSV. Gibt (0, 0)
    zurück, wenn die Datei (noch) nicht existiert oder nicht lesbar ist."""
    try:
        if not os.path.exists(feedback_file):
            return 0, 0
        up, down = 0, 0
        with open(feedback_file, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("vote") == "up":
                    up += 1
                elif row.get("vote") == "down":
                    down += 1
        return up, down
    except Exception:
        return 0, 0
