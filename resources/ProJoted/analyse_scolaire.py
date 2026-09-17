# ProJote — plugin Jeedom pour Pronote
# Copyright (C) 2024-2026 Aldarande
# Licensed under the GNU Affero General Public License v3 or later.
# See <https://www.gnu.org/licenses/agpl-3.0.html> for full license text.

"""analyse_scolaire.py — Ce que Pronote ne calcule pas.

Quatre traitements que le plugin fait lui-même, faute que Pronote les expose :

* **La moyenne générale.** Pronote n'en publie pas toujours une ; quand elle
  manque, elle est recalculée à partir des notes et de leurs coefficients.
* **Les matières en baisse**, par comparaison des notes récentes à la moyenne
  de la matière.
* **Les prochains contrôles.** Aucun objet Homework ne porte de marqueur
  « contrôle » : la nature du devoir est devinée à la lecture de son intitulé.
  C'est une heuristique, elle est assumée comme telle.
* **Les nouveautés depuis le cycle précédent**, qui alimentent les commandes
  `nouvelle_note` et `nouveau_devoir` — celles sur lesquelles se branchent les
  scénarios. Elles reposent sur une signature stable par élément : un
  identifiant qui changerait d'un cycle à l'autre déclencherait une notification
  pour chaque note déjà connue.

Extrait de ProJoted.py en v1.6.0, sans modification du code.
"""

import datetime
import logging

from format_pronote import _truncate


# ── Détection des évaluations / DS dans les devoirs ─────────────────────────
# Pronote ne fournit pas de flag « contrôle » sur Homework. On infère via une
# regex sur la description et le titre.
import re as _re_eval


_EVAL_PATTERN = _re_eval.compile(
    r"\b(contr[ôo]le|DS|[ée]valuation|interro(?:gation)?|test|examen|devoir surveill[ée])\b",
    _re_eval.IGNORECASE,
)


DS_HORIZON_JOURS = 7


def detect_next_evaluations(all_homework, max_keep=5, horizon_jours=DS_HORIZON_JOURS):
    """Repère les devoirs qui ressemblent à un contrôle/DS et renvoie les prochains.

    Retourne un dict avec :
      - prochain_DS_matiere      : matière du prochain DS (ou "")
      - prochain_DS_date         : date dd/mm/yyyy
      - prochain_DS_dans_jours   : nb jours entre aujourd'hui et le DS (int)
      - prochains_DS_html        : HTML compact des `max_keep` prochains DS
      - prochains_DS_brut        : liste structurée

    Seuls les contrôles situés dans les `horizon_jours` jours à venir sont
    retenus. Le démon charge 120 jours de devoirs : sans cette borne, le widget
    annonçait un contrôle à trois semaines, information sans valeur d'alerte qui
    masquait de surcroît un éventuel contrôle plus proche annoncé plus tard.

    Robustesse : si all_homework est vide ou si toutes les entrées échouent
    au parsing, on retourne des valeurs neutres.
    """
    import html as _html_mod

    empty = {
        "prochain_DS_matiere": "",
        "prochain_DS_date": "",
        "prochain_DS_dans_jours": -1,
        "prochains_DS_html": "",
        "prochains_DS_brut": [],
    }
    if not all_homework:
        return empty

    today = datetime.date.today()
    candidats = []

    for hw in all_homework:
        try:
            description = (hw.description or "") if hasattr(hw, "description") else ""
            subject_name = ""
            try:
                subject_name = getattr(hw.subject, "name", "") if hw.subject else ""
            except Exception:
                subject_name = ""

            haystack = f"{subject_name} {description}"
            if not _EVAL_PATTERN.search(haystack):
                continue

            hw_date = getattr(hw, "date", None)
            if hw_date is None or hw_date < today:
                continue
            if (hw_date - today).days > horizon_jours:
                continue

            candidats.append(
                {
                    "matiere": subject_name or "—",
                    "date": hw_date.strftime("%d/%m/%Y"),
                    "date_iso": hw_date.isoformat(),
                    "dans_jours": (hw_date - today).days,
                    "extrait": _truncate(description, 120),
                }
            )
        except Exception as e:
            logging.debug("Detection DS : entrée ignorée (%s)", e)

    if not candidats:
        return empty

    candidats.sort(key=lambda c: c["date_iso"])
    prochain = candidats[0]

    top = candidats[:max_keep]
    html_parts = []
    for c in top:
        html_parts.append(
            f'<div class="pj-ds-row">'
            f'<span class="pj-ds-date">{_html_mod.escape(c["date"])}</span>'
            f'<span class="pj-ds-matiere">{_html_mod.escape(c["matiere"])}</span>'
            f'<span class="pj-ds-extrait">{_html_mod.escape(c["extrait"])}</span>'
            f"</div>"
        )

    return {
        "prochain_DS_matiere": prochain["matiere"],
        "prochain_DS_date": prochain["date"],
        "prochain_DS_dans_jours": prochain["dans_jours"],
        "prochains_DS_html": "".join(html_parts),
        "prochains_DS_brut": top,
    }


def compute_moyenne_generale(note_list):
    """Moyenne générale pondérée sur 20, calculée à partir de la liste de notes.

    Reprend la logique du widget : chaque note est ramenée sur 20 puis pondérée
    par son coefficient. Sont exclues les notes non numériques, à dénominateur
    nul ou négatif, et de coefficient nul ou négatif (bonus / optionnel).

    Args:
        note_list (list[dict]): notes sérialisées (clés note, sur, coeff).
    Returns:
        float | None: moyenne arrondie à 2 décimales, ou None si aucune note exploitable.
    """
    tot = 0.0
    coefs = 0.0
    for n in note_list or []:
        try:
            note_f = float(str(n.get("note", "")).replace(",", "."))
        except (ValueError, AttributeError):
            continue
        sur_str = str(n.get("sur", "20")).replace(",", ".") or "20"
        try:
            sur_f = float(sur_str)
        except ValueError:
            sur_f = 20.0
        try:
            coeff_f = float(str(n.get("coeff", "1")).replace(",", "."))
        except ValueError:
            coeff_f = 1.0
        if sur_f <= 0 or coeff_f <= 0:
            continue
        tot += (note_f / sur_f) * 20.0 * coeff_f
        coefs += coeff_f
    if coefs <= 0:
        return None
    return round(tot / coefs, 2)


def detect_subject_trends(note_list, min_notes=4, drop_threshold=2.0):
    """Détecte les matières en baisse à partir des notes (ramenées sur 20).

    Pour chaque matière comptant au moins `min_notes` notes numériques, compare
    la moyenne de la moitié la plus récente à celle de la moitié la plus ancienne.
    Une chute supérieure ou égale à `drop_threshold` points (sur 20) signale une
    matière en baisse.

    `note_list` est attendue triée du plus récent au plus ancien (cf. notes()).

    Returns:
        dict avec :
          - matiere_en_baisse        : noms séparés par " · " (ou "")
          - matiere_en_baisse_detail : liste [{matiere, ancienne_moyenne, recente_moyenne, delta}]
    """
    empty = {"matiere_en_baisse": "", "matiere_en_baisse_detail": []}
    if not note_list:
        return empty

    by_subject = {}
    for n in note_list:
        try:
            note_f = float(str(n.get("note", "")).replace(",", "."))
            sur_f = float(str(n.get("sur", "20")).replace(",", ".") or "20")
        except (ValueError, AttributeError):
            continue
        if sur_f <= 0:
            continue
        subj = n.get("cours", "Inconnu") or "Inconnu"
        by_subject.setdefault(subj, []).append((note_f / sur_f) * 20.0)

    detail = []
    for subj, notes20 in by_subject.items():
        if len(notes20) < min_notes:
            continue
        # notes20 va du plus récent au plus ancien → remettre en ordre chronologique
        chrono = list(reversed(notes20))
        half = len(chrono) // 2
        anciennes = chrono[:half]
        recentes = chrono[len(chrono) - half:]
        if not anciennes or not recentes:
            continue
        moy_anc = sum(anciennes) / len(anciennes)
        moy_rec = sum(recentes) / len(recentes)
        if (moy_anc - moy_rec) >= drop_threshold:
            detail.append(
                {
                    "matiere": subj,
                    "ancienne_moyenne": round(moy_anc, 2),
                    "recente_moyenne": round(moy_rec, 2),
                    "delta": round(moy_rec - moy_anc, 2),
                }
            )

    detail.sort(key=lambda d: d["delta"])  # plus forte baisse en premier
    return {
        "matiere_en_baisse": " · ".join(d["matiere"] for d in detail),
        "matiere_en_baisse_detail": detail,
    }


def _item_signature(item, *fields):
    """Signature stable d'un item à partir de champs sélectionnés."""
    return "|".join(str(item.get(f, "")) for f in fields)


def _sig_of(item, kind):
    """Identifiant stable d'un item selon son type (id Pronote si disponible)."""
    sid = item.get("id")
    has_id = sid not in (None, "")
    if kind == "notes":
        return str(sid) if has_id else "n:" + _item_signature(item, "cours", "date", "note", "sur", "commentaire")
    if kind == "devoirs":
        # Les devoirs n'ont pas d'id Pronote stable exposé → signature de contenu.
        return "d:" + _item_signature(item, "date", "title", "description")
    if kind == "punitions":
        return "p:" + (str(sid) if has_id else _item_signature(item, "date", "raison", "type"))
    if kind == "absences":
        return "a:" + (str(sid) if has_id else _item_signature(item, "date_debut", "date_fin"))
    return _item_signature(item, "id")


def format_new_note_label(note):
    """Libellé lisible d'une nouvelle note. Ex : 'Maths : 16/20 — DS trigonométrie'."""
    cours = str(note.get("cours", "")).strip() or "?"
    note_sur = str(note.get("note_sur", "")).replace(" ", " ").strip()
    if not note_sur:
        n = str(note.get("note", "")).strip()
        s = str(note.get("sur", "")).strip()
        note_sur = f"{n}/{s}" if n and s else n
    comm = str(note.get("commentaire", "")).strip()
    label = f"{cours} : {note_sur}" if note_sur else cours
    if comm:
        label += f" — {comm}"
    return label


def format_new_devoir_label(dv):
    """Libellé lisible d'un nouveau devoir. Ex : 'Maths (12/03) : exercices p.42'."""
    matiere = str(dv.get("title", "")).strip() or "?"
    date = str(dv.get("date", "")).strip()
    desc = str(dv.get("description", "")).strip()
    head = f"{matiere} ({date})" if date else matiere
    return f"{head} : {desc}" if desc else head


def compute_deltas(seen_index, notes_list, devoirs_list, punitions_list, absences_list):
    """Compare les items courants à l'index « déjà vu » précédent.

    Retourne (deltas, new_index). Au PREMIER passage (index vide/absent), aucun
    delta n'est émis : on n'enregistre que la baseline pour éviter une avalanche
    de notifications au branchement initial (même logique que le centre d'alertes).

    deltas contient les compteurs de nouveautés et les libellés de la dernière
    nouvelle note / du dernier nouveau devoir (vides si rien de neuf).
    """
    kinds = (
        ("notes", notes_list, "nouvelles_notes"),
        ("devoirs", devoirs_list, "nouveaux_devoirs"),
        ("punitions", punitions_list, "nouvelles_punitions"),
        ("absences", absences_list, "nouvelles_absences"),
    )
    new_index = {kind: [_sig_of(it, kind) for it in (lst or [])] for kind, lst, _ in kinds}

    deltas = {
        "nouvelles_notes": 0,
        "nouveaux_devoirs": 0,
        "nouvelles_punitions": 0,
        "nouvelles_absences": 0,
        "derniere_nouvelle_note": "",
        "dernier_nouveau_devoir": "",
    }
    if not seen_index:
        return deltas, new_index  # premier passage : baseline seulement

    for kind, lst, count_key in kinds:
        seen = set(seen_index.get(kind, []))
        new_sigs = [s for s in new_index[kind] if s not in seen]
        deltas[count_key] = len(new_sigs)

    new_notes = {s for s in new_index["notes"] if s not in set(seen_index.get("notes", []))}
    if new_notes:
        for n in notes_list or []:
            if _sig_of(n, "notes") in new_notes:
                deltas["derniere_nouvelle_note"] = format_new_note_label(n)
                break

    new_dev = {s for s in new_index["devoirs"] if s not in set(seen_index.get("devoirs", []))}
    if new_dev:
        for d in devoirs_list or []:
            if _sig_of(d, "devoirs") in new_dev:
                deltas["dernier_nouveau_devoir"] = format_new_devoir_label(d)
                break

    return deltas, new_index
