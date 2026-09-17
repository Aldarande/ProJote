# ProJote — plugin Jeedom pour Pronote
# Copyright (C) 2024-2026 Aldarande
# Licensed under the GNU Affero General Public License v3 or later.
# See <https://www.gnu.org/licenses/agpl-3.0.html> for full license text.

"""collecteurs.py — Les douze onglets Pronote relevés par le démon.

Chacune de ces fonctions reçoit un client pronotepy connecté et rend la portion
de charge que Jeedom consomme pour cet onglet. Elles partagent trois règles, qui
expliquent la forme du code :

* **Aucune ne lève.** Un onglet en panne ne doit coûter que lui-même : chacune
  rattrape ses propres erreurs et rend une structure vide, complétée d'une clé
  ``error`` quand la cause mérite d'être remontée. Seule ``SuspensionIP``
  traverse — elle hérite de ``BaseException`` justement pour cela, chaque
  requête supplémentaire prolongeant le blocage côté Pronote.
* **Les clés de sortie sont un contrat.** ``jeeProJote.php`` et le widget les
  lisent nommément ; en renommer une vide une commande ou une section à
  l'écran. ``tests/test_collecteurs.py`` les garde.
* **Rien n'est supposé présent côté pronotepy.** La bibliothèque déplace ses
  champs d'une version à l'autre, et les serveurs Pronote ne répondent pas tous
  la même chose : les accès passent par ``getattr`` ou par ``_safe_attr``.

Absences, retards et punitions partagent l'onglet « Présence » de Pronote, d'où
leur passage par ``presence_pronote`` : un refus est retenu le temps du cycle
pour ne pas provoquer trois ré-authentifications inutiles.

Extrait de ProJoted.py en v1.6.0, sans modification du code.
"""

import datetime
import logging
import traceback

from analyse_scolaire import (
    compute_moyenne_generale,
    detect_next_evaluations,
    detect_subject_trends,
)
from format_pronote import (
    _information_content,
    _menu_to_html_row,
    _menu_to_text,
    _safe_attr,
    _truncate,
    build_cours_data,
    build_menu_data,
    cours_affiche_from_lesson,
)
from periodes_scolaires import _periodes_couvrantes
from presence_pronote import (
    _noter_refus_presence,
    _presence_deja_refusee,
    _refus_de_presence,
)


def _sans_equipement():
    """Valeur de repli tant que le démon n'a pas injecté sa propre fonction."""
    return None


# Identifiant de l'équipement en cours de traitement. Le démon traite les
# équipements l'un après l'autre et le sait seul ; les collecteurs en ont besoin
# pour mémoriser un refus de l'onglet Présence au bon endroit. Il est injecté
# par installer() plutôt qu'importé, pour que ce module reste indépendant du
# démon — et donc testable sans lui. Même procédé que token_secours.installer().
_equipement_en_cours = _sans_equipement


def installer(equipement_en_cours):
    """Renseigne la fonction qui nomme l'équipement en cours de traitement."""
    global _equipement_en_cours
    _equipement_en_cours = equipement_en_cours


def Emploidutemps(client):
    try:
        # Emploi du temps : aujourd'hui + 4 prochains jours scolaires (v0.9b : 1 appel batch sur 14j)
        # Récupération  emploi du temps du jour
        lessons_today = client.lessons(datetime.date.today())
        data = {
            "edt_aujourdhui": [],
            "edt_aujourdhui_debut": "",
            "edt_aujourdhui_fin": "",
            "edt_aujourdhui_cancel": 0,
        }
        lessons_today = sorted(lessons_today, key=lambda lesson: lesson.start)
        if lessons_today:
            for lesson in lessons_today:
                index = lessons_today.index(lesson)
                if (
                    lesson.start != lessons_today[index - 1].start
                    or lesson.canceled != True
                ):
                    data["edt_aujourdhui"].append(build_cours_data(lesson))
                if lesson.canceled == False and data["edt_aujourdhui_debut"] == "":
                    data["edt_aujourdhui_debut"] = lesson.start.strftime("%H%M")
                if lesson.canceled == True:
                    data["edt_aujourdhui_cancel"] = data["edt_aujourdhui_cancel"] + 1
            data["edt_aujourdhui_fin"] = lesson.end.strftime("%H%M")

        # Récupération des 4 prochains jours scolaires (1 seul appel API sur 28 jours
        # pour couvrir les vacances scolaires de 2 semaines)
        try:
            lessons_range = client.lessons(
                datetime.date.today() + datetime.timedelta(days=1),
                datetime.date.today() + datetime.timedelta(days=28),
            )
        except Exception as e:
            logging.warning(f"Impossible de récupérer les jours suivants : {e}")
            lessons_range = []

        # Grouper les cours par date
        days_by_date = {}
        for lesson in lessons_range or []:
            d = lesson.start.date() if hasattr(lesson.start, "date") else lesson.start
            if d not in days_by_date:
                days_by_date[d] = []
            days_by_date[d].append(lesson)

        # Prendre les 4 premières dates avec cours
        next_school_dates = sorted(days_by_date.keys())[:4]

        # Initialiser les 4 slots à vide
        for i in range(1, 5):
            key = f"edt_J{i}"
            data[key] = []
            data[f"{key}_date"] = ""
            data[f"{key}_debut"] = ""
            data[f"{key}_fin"] = ""
            data[f"{key}_cancel"] = 0

        # Remplir les slots disponibles
        for i, school_date in enumerate(next_school_dates, 1):
            key = f"edt_J{i}"
            lessons = sorted(days_by_date[school_date], key=lambda l: l.start)
            data[f"{key}_date"] = school_date.strftime("%d/%m/%Y")
            for lesson in lessons:
                index = lessons.index(lesson)
                if lesson.start != lessons[index - 1].start or lesson.canceled != True:
                    lesson_to_append = build_cours_data(lesson)
                    lesson_to_append["index"] = index
                    data[key].append(lesson_to_append)
                if lesson.canceled == True:
                    data[f"{key}_cancel"] += 1
                if lesson.canceled == False and data[f"{key}_debut"] == "":
                    data[f"{key}_debut"] = lesson.start.strftime("%H%M")
            if lessons:
                data[f"{key}_fin"] = lessons[-1].end.strftime("%H%M")

        # Rétro-compatibilité : edt_prochainjour = J1
        data["edt_prochainjour"] = data["edt_J1"]
        data["edt_prochainjour_date"] = data["edt_J1_date"]
        data["edt_prochainjour_debut"] = data["edt_J1_debut"]
        data["edt_prochainjour_fin"] = data["edt_J1_fin"]
        data["edt_prochainjour_cancel"] = data["edt_J1_cancel"]

        # Tableau compact pour le widget (évite de répliquer les données)
        data["edt_next_days"] = []
        for i in range(1, 5):
            key = f"edt_J{i}"
            if data[f"{key}_date"]:
                data["edt_next_days"].append(
                    {
                        "cours": data[key],
                        "date": data[f"{key}_date"],
                        "debut": data[f"{key}_debut"],
                        "fin": data[f"{key}_fin"],
                        "cancel": data[f"{key}_cancel"],
                    }
                )

        # Récupération emploi du jour courant (date spécifique)
        lessons_specific = client.lessons(datetime.date.today())
        lessons_specific = sorted(lessons_specific, key=lambda lesson: lesson.start)

        data["edt_date_specific"] = []
        if lessons_specific:
            for lesson in lessons_specific:
                index = lessons_specific.index(lesson)
                if lesson.start == lessons_specific[index - 1].start:
                    lesson.num
                else:
                    lesson_to_append = build_cours_data(lesson)
                    lesson_to_append["index"] = index
                    lesson_to_append["num"] = lesson.num
                    data["edt_date_specific"].append(lesson_to_append)

        # Récupération  emploi du temps global de la période en cours
        try:
            lessons_full = client.lessons(
                client.current_period.start, datetime.date.today()
            )
        except Exception as e:
            logging.error(f"Erreur lors de l'accès à l'emploi du temps global : {e}")
            lessons_full = []
        lessons_full = sorted(lessons_full, key=lambda lesson: lesson.start)

        # data["edt_period_full"] = []
        # data["edt_absent_full"] = []
        data["edt_Cours_canceled"] = 0
        if lessons_full:
            for lesson in lessons_full:
                # lesson_to_append = build_cours_data(lesson)
                # lesson_to_append["index"] = index
                # lesson_to_append["num"] = lesson.num
                # data["edt_period_full"].append(lesson_to_append)
                if lesson.canceled == True:
                    # data["edt_absent_full"].append(lesson_to_append)
                    data["edt_Cours_canceled"] += 1
        return data
    except Exception as e:
        line_number = e.__traceback__.tb_lineno if e.__traceback__ else "unknown"
        error_msg = f"Erreur lors de la récupération de l'emploi du temps : ligne {line_number} - {str(e)}"
        logging.error(error_msg)
        return {"error": error_msg}


def menus(client):
    """Collecte les menus cantine sur 7 jours et construit les agrégats widget.

    Retourne un dict avec :
      - menu_midi_aujourdhui : texte lisible du menu de midi du jour (ou "")
      - menu_midi_demain     : idem pour le lendemain
      - menu_semaine         : HTML compact des 7 prochains jours
      - Nb_menus_semaine     : nombre de menus dans la fenêtre
      - menus_brut           : liste complète des menus sérialisés (build_menu_data)

    pronotepy v2.14+ : client.menus(date_from, date_to=None) → List[Menu]
    En cas d'erreur, retourne un dict avec clé 'error' et valeurs neutres
    (pattern d'isolation des erreurs par feature, cf. notes, devoirs…).
    """
    today = datetime.date.today()
    week_end = today + datetime.timedelta(days=7)
    empty = {
        "menu_midi_aujourdhui": "",
        "menu_midi_demain": "",
        "menu_semaine": "",
        "Nb_menus_semaine": 0,
        "menus_brut": [],
    }
    try:
        menu_list = client.menus(today, week_end)
    except TypeError:
        # Compat ancienne signature : un seul argument
        try:
            menu_list = client.menus(today)
        except Exception as e:
            logging.error("Erreur lors de l'appel client.menus : %s", e)
            empty["error"] = f"Erreur d'accès aux menus : {e}"
            return empty
    except Exception as e:
        logging.error("Erreur lors de l'appel client.menus : %s", e)
        empty["error"] = f"Erreur d'accès aux menus : {e}"
        return empty

    if not menu_list:
        logging.info("Aucun menu cantine trouvé pour la fenêtre %s → %s.", today, week_end)
        return empty

    try:
        menu_list = sorted(menu_list, key=lambda m: m.date)
    except Exception:
        pass

    menus_brut = []
    for menu in menu_list:
        try:
            menus_brut.append(build_menu_data(menu))
        except Exception as e:
            logging.error("Erreur sérialisation menu : %s", e)

    tomorrow = today + datetime.timedelta(days=1)
    today_iso = today.strftime("%Y-%m-%d")
    tomorrow_iso = tomorrow.strftime("%Y-%m-%d")

    menu_midi_today = ""
    menu_midi_tomorrow = ""
    for m in menus_brut:
        if not m.get("is_lunch"):
            continue
        if m.get("date") == today_iso and not menu_midi_today:
            menu_midi_today = _menu_to_text(m)
        elif m.get("date") == tomorrow_iso and not menu_midi_tomorrow:
            menu_midi_tomorrow = _menu_to_text(m)

    menu_semaine_html = "".join(_menu_to_html_row(m) for m in menus_brut)

    return {
        "menu_midi_aujourdhui": menu_midi_today,
        "menu_midi_demain": menu_midi_tomorrow,
        "menu_semaine": menu_semaine_html,
        "Nb_menus_semaine": len(menus_brut),
        "menus_brut": menus_brut,
    }


def messages(client):
    """Collecte les discussions Pronote (messagerie) et construit les agrégats widget.

    Retourne un dict avec :
      - Nb_messages_non_lus       : compteur entier
      - dernier_message_expediteur: nom du créateur du dernier message
      - dernier_message_sujet     : objet (sujet) du dernier message
      - dernier_message_date      : date formatée dd/mm/yyyy HH:MM
      - dernier_message_extrait   : contenu tronqué (200 caractères)
      - messages_html             : liste HTML compacte des discussions pour widget
      - Nb_messages               : compteur total des discussions visibles
      - messages_brut             : liste structurée des discussions

    pronotepy : Client.discussions() → List[Discussion]
    Pattern d'isolation des erreurs (cf. menus, notes…).
    """
    import html as _html_mod

    empty = {
        "Nb_messages": 0,
        "Nb_messages_non_lus": 0,
        "dernier_message_expediteur": "",
        "dernier_message_sujet": "",
        "dernier_message_date": "",
        "dernier_message_extrait": "",
        "messages_html": "",
        "messages_brut": [],
    }

    try:
        # ParentClient peut nécessiter de cibler l'enfant sélectionné. Le client.discussions()
        # fonctionne sur le client courant (élève direct ou child sélectionné via _selected_child).
        discussions = client.discussions()
    except AttributeError:
        logging.info("pronotepy : client.discussions() indisponible — messagerie ignorée.")
        return empty
    except Exception as e:
        logging.error("Erreur lors de l'accès aux discussions Pronote : %s", e)
        empty["error"] = f"Erreur d'accès à la messagerie : {e}"
        return empty

    if not discussions:
        logging.info("Aucune discussion Pronote retournée.")
        return empty

    messages_brut = []
    for disc in discussions:
        try:
            subject = _safe_attr(disc, "subject", default="(sans objet)")
            creator = _safe_attr(disc, "creator", "sender", default="")
            # Date du dernier message — selon pronotepy, attribut date ou date_last_message
            raw_date = _safe_attr(disc, "date", "date_last_message", default=None)
            date_str = ""
            date_sort = ""  # Clé de tri chronologique (ISO ou epoch string)
            if raw_date:
                try:
                    date_str = raw_date.strftime("%d/%m/%Y %H:%M")
                except Exception:
                    date_str = str(raw_date)
                try:
                    # ISO 8601 trie lexicographiquement = chronologiquement
                    date_sort = raw_date.strftime("%Y-%m-%dT%H:%M:%S")
                except Exception:
                    date_sort = str(raw_date)

            unread = bool(_safe_attr(disc, "unread", default=0))
            participants_count = 0
            try:
                participants = _safe_attr(disc, "participants", default=[]) or []
                participants_count = len(participants)
            except Exception:
                participants_count = 0

            # Contenu : Discussion.messages est généralement une List[Message]
            last_content = ""
            try:
                msg_list = _safe_attr(disc, "messages", default=[]) or []
                if msg_list:
                    last_msg = msg_list[-1]
                    last_content = _safe_attr(last_msg, "content", "body", default="")
            except Exception:
                last_content = ""

            messages_brut.append(
                {
                    "subject": str(subject),
                    "creator": str(creator),
                    "date": date_str,
                    "_date_sort": date_sort,  # interne, retiré avant retour
                    "unread": unread,
                    "participants_count": participants_count,
                    "extrait": _truncate(last_content, 200),
                }
            )
        except Exception as e:
            logging.error("Erreur sérialisation discussion : %s", e)

    # « dernier message » = le plus récent chronologiquement, indépendamment du statut lu.
    # Calcul avant tri d'affichage pour ne pas dépendre de l'ordre final.
    dernier = {}
    if messages_brut:
        try:
            dernier = max(messages_brut, key=lambda m: m.get("_date_sort") or "")
        except Exception:
            dernier = messages_brut[0]

    # Tri d'affichage : non-lus d'abord, puis du plus récent au plus ancien.
    # On utilise _date_sort (ISO 8601) qui se trie correctement lexicographiquement.
    try:
        messages_brut.sort(
            key=lambda m: (0 if m["unread"] else 1, m.get("_date_sort") or ""),
            reverse=False,
        )
        # Si deux messages ont le même statut lu/non-lu, on veut le plus récent en premier ;
        # le tri ci-dessus met le plus ancien en premier dans un groupe. On inverse par groupe.
        messages_brut = sorted(
            messages_brut,
            key=lambda m: (0 if m["unread"] else 1, -1),
        )
        # Re-trier finalement avec un comparateur composite : groupes par unread, puis date desc.
        from functools import cmp_to_key

        def _msg_cmp(a, b):
            # Non-lus avant lus
            ua, ub = (0 if a["unread"] else 1), (0 if b["unread"] else 1)
            if ua != ub:
                return ua - ub
            # Date décroissante (plus récent en premier)
            da, db = a.get("_date_sort") or "", b.get("_date_sort") or ""
            if da > db:
                return -1
            if da < db:
                return 1
            return 0

        messages_brut.sort(key=cmp_to_key(_msg_cmp))
    except Exception as e:
        logging.debug("Tri messages : %s", e)

    # Nettoyage : retirer la clé interne _date_sort avant exposition
    for m in messages_brut:
        m.pop("_date_sort", None)
    dernier.pop("_date_sort", None) if isinstance(dernier, dict) else None

    nb_total = len(messages_brut)
    nb_non_lus = sum(1 for m in messages_brut if m["unread"])

    # HTML compact pour le widget — pattern aligné sur les autres listes
    html_parts = []
    for m in messages_brut:
        unread_cls = " pj-msg-unread" if m["unread"] else ""
        html_parts.append(
            f'<div class="pj-msg-row{unread_cls}">'
            f'<div class="pj-msg-head">'
            f'<span class="pj-msg-sender">{_html_mod.escape(m["creator"]) or "—"}</span>'
            f'<span class="pj-msg-date">{_html_mod.escape(m["date"])}</span>'
            f"</div>"
            f'<div class="pj-msg-subject">{_html_mod.escape(m["subject"])}</div>'
            f'<div class="pj-msg-extract">{_html_mod.escape(m["extrait"])}</div>'
            f"</div>"
        )

    return {
        "Nb_messages": nb_total,
        "Nb_messages_non_lus": nb_non_lus,
        "dernier_message_expediteur": dernier.get("creator", ""),
        "dernier_message_sujet": dernier.get("subject", ""),
        "dernier_message_date": dernier.get("date", ""),
        "dernier_message_extrait": dernier.get("extrait", ""),
        "messages_html": "".join(html_parts),
        "messages_brut": messages_brut,
    }


def evaluations(client):
    try:
        # Récupération des évaluations
        try:
            evaluations = client.current_period.evaluations
        except Exception as e:
            logging.error(f"Erreur lors de l'accès aux évaluations : {e}")
            return {
                "evaluations": [],
                "error": f"Erreur d'accès aux évaluations : {str(e)}",
            }
        data = {
            "evaluations": [],
        }
        if evaluations == []:
            return data
        for evaluation in evaluations:

            def acquisition_to_dict(acq):
                # Si c'est déjà un dict, on le retourne
                if isinstance(acq, dict):
                    return acq
                # Sinon, on extrait les attributs principaux
                return {
                    "ordre": getattr(acq, "order", ""),
                    "name": getattr(acq, "name", ""),
                    "name_id": getattr(acq, "name_id", ""),
                    "abbreviation": getattr(acq, "abbreviation", ""),
                    "level": getattr(acq, "level", ""),
                    "coefficient": getattr(acq, "coefficient", ""),
                    "domain": getattr(acq, "domain", ""),
                    "domain_id": getattr(acq, "domain_id", ""),
                    "pillar": getattr(acq, "pillar", ""),
                    "pillar_id": getattr(acq, "pillar_id", ""),
                }

            # Si c'est un dict, on convertit ses valeurs
            if isinstance(evaluation.acquisitions, dict):
                acquisitions = {
                    k: acquisition_to_dict(v)
                    for k, v in evaluation.acquisitions.items()
                }
            # Si c'est une liste
            elif isinstance(evaluation.acquisitions, list):
                acquisitions = [acquisition_to_dict(a) for a in evaluation.acquisitions]
            else:
                acquisitions = evaluation.acquisitions

            try:
                sujet_name = getattr(evaluation.subject, "name", "Inconnu")
            except Exception:
                sujet_name = "Inconnu"
            data["evaluations"].append(
                {
                    "id": evaluation.id,
                    "nom": evaluation.name,
                    "domaine": evaluation.domain,
                    "professeur": evaluation.teacher,
                    "Sujet": sujet_name,
                    "date": evaluation.date.strftime("%d/%m/%Y"),
                    "acquisitions": acquisitions,
                    "description": evaluation.description,
                    "Paliers": evaluation.paliers,
                    "coeff": evaluation.coefficient,
                }
            )
        return data["evaluations"]
    except Exception as e:
        line_number = e.__traceback__.tb_lineno
        logging.error(
            "Une erreur est retournée sur le traitement des évaluations-lig: %s; %s",
            line_number,
            e,
        )


def notes(client):
    """
    Récupère toutes les notes de l'année scolaire (toutes périodes) et les formate en JSON.
    """
    try:
        data = {"note": [], "derniere_note": [], "moyennes_periodes": []}

        try:
            all_periods = client.periods
        except Exception as e:
            logging.error(f"Erreur lors de l'accès aux périodes : {e}")
            return {"note": [], "derniere_note": [], "error": str(e)}

        all_grades = []
        for period in all_periods:
            try:
                period_grades = period.grades
                period_name = getattr(period, "name", "")
                for grade in period_grades or []:
                    all_grades.append((grade, period_name))
            except Exception as e:
                logging.warning(
                    f"Impossible de lire les notes de la période {getattr(period, 'name', '?')} : {e}"
                )

            # Moyennes générales par période (élève + classe)
            try:
                period_name = getattr(period, "name", "?")
                moy_eleve_raw = getattr(period, "overall_average", "") or ""
                moy_classe_raw = getattr(period, "class_overall_average", "") or ""
                logging.debug(
                    "Moyenne brute Pronote — période=%s  élève=%r  classe=%r",
                    period_name, moy_eleve_raw, moy_classe_raw,
                )
                moy_eleve = moy_eleve_raw
                moy_classe = moy_classe_raw
                # Pronote retourne "-1" comme sentinelle quand la moyenne n'est pas disponible
                if str(moy_eleve).strip() == "-1":
                    logging.debug("Moyenne élève ignorée (sentinelle -1) — période=%s", period_name)
                    moy_eleve = ""
                if str(moy_classe).strip() == "-1":
                    logging.debug("Moyenne classe ignorée (sentinelle -1) — période=%s", period_name)
                    moy_classe = ""
                if moy_eleve or moy_classe:
                    logging.debug(
                        "Moyenne retenue — période=%s  élève=%s  classe=%s",
                        period_name,
                        str(moy_eleve).replace(",", "."),
                        str(moy_classe).replace(",", "."),
                    )
                    data["moyennes_periodes"].append(
                        {
                            "periode": period_name,
                            "moyenne_eleve": str(moy_eleve).replace(",", "."),
                            "moyenne_classe": str(moy_classe).replace(",", "."),
                        }
                    )
                else:
                    logging.debug("Aucune moyenne disponible pour la période=%s", period_name)
            except Exception:
                pass

        if all_grades:
            # Tri toutes périodes confondues, du plus récent au plus ancien
            all_grades = sorted(
                all_grades,
                key=lambda x: getattr(x[0], "date", datetime.date.min),
                reverse=True,
            )

            for grade, period_name in all_grades:
                cours_name = "Inconnu"
                if hasattr(grade, "subject") and grade.subject:
                    cours_name = getattr(grade.subject, "name", "Inconnu")

                note_value = getattr(grade, "grade", "")
                out_of_value = getattr(grade, "out_of", "")
                note_sur = (
                    f"{note_value}\u00a0/\u00a0{out_of_value}"
                    if note_value and out_of_value
                    else ""
                )
                grade_date = getattr(grade, "date", None) or datetime.date.today()

                # Pronote renvoie parfois des objets {"V": valeur} au lieu de scalaires
                coeff_raw = getattr(grade, "coefficient", "1")
                if isinstance(coeff_raw, dict):
                    coeff_raw = coeff_raw.get("V", "1")
                comment_raw = getattr(grade, "comment", "")
                if isinstance(comment_raw, dict):
                    comment_raw = comment_raw.get("V", "")

                data["note"].append(
                    {
                        "id": getattr(grade, "id", ""),
                        "periode": period_name,
                        "date": grade_date.strftime("%d/%m/%Y"),
                        "date_courte": grade_date.strftime("%d/%m"),
                        "cours": cours_name,
                        "note": str(note_value).replace(",", "."),
                        "sur": str(out_of_value).replace(",", "."),
                        "note_sur": note_sur,
                        "coeff": str(coeff_raw).replace(",", "."),
                        "moyenne_classe": str(getattr(grade, "average", "")).replace(
                            ",", "."
                        ),
                        "max": str(getattr(grade, "max", "")).replace(",", "."),
                        "min": str(getattr(grade, "min", "")).replace(",", "."),
                        "commentaire": str(comment_raw),
                        "optionnel": getattr(grade, "is_optionnal", False),
                        "bonus": getattr(grade, "is_bonus", False),
                    }
                )

            if data["note"]:
                data["derniere_note"].append(data["note"][0])

            # ── Moyenne générale + détection des matières en baisse (F3, v1.1.0) ─
            moy_gen = compute_moyenne_generale(data["note"])
            data["moyenne_generale"] = "" if moy_gen is None else str(moy_gen)
            data.update(detect_subject_trends(data["note"]))

            # ── Calcul debug de la moyenne (même logique que le widget JS) ──────
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                tot = 0.0
                coefs = 0.0
                skipped = 0
                logging.debug("── Détail calcul moyenne générale (%d notes) ──", len(data["note"]))
                for n in data["note"]:
                    note_str = str(n.get("note", "")).replace(",", ".")
                    sur_str  = str(n.get("sur",  "20")).replace(",", ".") or "20"
                    coeff_str = str(n.get("coeff", "1")).replace(",", ".")
                    try:
                        note_f  = float(note_str)
                        sur_f   = float(sur_str) if sur_str else 20.0
                        coeff_f = float(coeff_str) if coeff_str else 1.0
                    except ValueError:
                        logging.debug(
                            "  IGNORÉE  %-30s  %s — valeur non numérique (note=%r sur=%r coeff=%r)",
                            n.get("cours", "?"), n.get("date", "?"),
                            n.get("note"), n.get("sur"), n.get("coeff"),
                        )
                        skipped += 1
                        continue
                    if sur_f <= 0:
                        logging.debug(
                            "  IGNORÉE  %-30s  %s — dénominateur nul ou négatif (sur=%s)",
                            n.get("cours", "?"), n.get("date", "?"), sur_str,
                        )
                        skipped += 1
                        continue
                    contribution = (note_f / sur_f) * 20.0 * coeff_f
                    tot   += contribution
                    coefs += coeff_f
                    logging.debug(
                        "  INCLUSE  %-30s  %s  note=%s/%s  coeff=%s  contrib=%.4f  (tot=%.4f coefs=%.2f)",
                        n.get("cours", "?"), n.get("date", "?"),
                        note_str, sur_str, coeff_str,
                        contribution, tot, coefs,
                    )
                if coefs > 0:
                    moy_calc = tot / coefs
                    logging.debug(
                        "── Résultat calcul : %.2f/20  (%d notes incluses, %d ignorées) ──",
                        moy_calc, len(data["note"]) - skipped, skipped,
                    )
                else:
                    logging.debug("── Résultat calcul : aucune note valide ──")
        else:
            logging.info("Aucune note trouvée pour l'année scolaire.")

        return data
    except Exception as e:
        line_number = e.__traceback__.tb_lineno if e.__traceback__ else "unknown"
        error_msg = (
            f"Erreur lors de la récupération des notes : ligne {line_number} - {str(e)}"
        )
        logging.error(error_msg)
        logging.debug(traceback.format_exc())
        return {"note": [], "derniere_note": [], "error": error_msg}


def process_homework(homework_list, data, key):
    if not homework_list:
        logging.info(f"Aucun devoir trouvé pour {key}.")
        data[f"Nb_{key}"] = 0
        data[f"Nb_{key}_F"] = 0
        data[f"Nb_{key}_NF"] = 0
        return 0, 0, 0

    Devoir = 0
    Devoirfait = 0
    Devoirnonfait = 0

    for homework in homework_list:
        try:
            title = (
                getattr(homework.subject, "name", "Inconnu")
                if homework.subject
                else "Inconnu"
            )
        except Exception:
            title = "Inconnu"

        # Description : Util.html_parse est patché pour préserver les espaces inter-mots
        description = homework.description or ""

        # Pièces jointes et liens
        fichiers = []
        try:
            for f in homework.files:
                fichiers.append(
                    {
                        "nom": f.name,
                        "url": f.url,
                        "type": f.type,  # 0 = lien externe, 1 = fichier Pronote
                    }
                )
        except Exception:
            pass

        data[key].append(
            {
                "index": homework_list.index(homework),
                "date": homework.date.strftime("%d/%m"),
                # Date complète pour le widget : il compose l'échéance en toutes
                # lettres (« Aujourd'hui », « Demain », « Mardi ») au moment du
                # rendu, et non de la collecte — sans quoi un widget affiché le
                # lendemain annoncerait encore « Aujourd'hui ».
                "date_iso": homework.date.strftime("%Y-%m-%d"),
                "title": title,
                "description": description,
                "color": homework.background_color,
                "done": homework.done,
                "fichiers": fichiers,
            }
        )
        Devoir += 1
        if homework.done == 1:
            Devoirfait += 1
        else:
            Devoirnonfait += 1

    data[f"Nb_{key}"] = Devoir
    data[f"Nb_{key}_F"] = Devoirfait
    data[f"Nb_{key}_NF"] = Devoirnonfait

    return Devoir, Devoirfait, Devoirnonfait


DEVOIRS_FENETRE_DEFAUT = 7


DEVOIRS_FENETRE_MAX = 120


def _fenetre_devoirs(message):
    """Nombre de jours couverts par la liste des devoirs, jour même compris.

    Réglable par équipement (configuration « devoirs_jours ») ; toute valeur
    absente, non numérique ou hors bornes retombe sur la valeur par défaut.
    """
    try:
        valeur = int(message.get("DevoirsJours") or DEVOIRS_FENETRE_DEFAUT)
    except (TypeError, ValueError, AttributeError):
        return DEVOIRS_FENETRE_DEFAUT
    if 1 <= valeur <= DEVOIRS_FENETRE_MAX:
        return valeur
    return DEVOIRS_FENETRE_DEFAUT


def devoirs(client, fenetre_jours=DEVOIRS_FENETRE_DEFAUT):
    try:
        data = {"devoir": [], "devoir_Demain": []}

        # Fenêtre glissante de 120 jours. Pronote raisonne en semaines : pronotepy
        # convertit ces dates en numéros de semaine scolaire (get_week) et demande
        # la plage correspondante à PageCahierDeTexte (onglet 88).
        date_debut = datetime.date.today()
        date_fin = date_debut + datetime.timedelta(days=120)
        try:
            semaines = "%s..%s" % (client.get_week(date_debut), client.get_week(date_fin))
        except Exception:  # get_week dépend des paramètres publiés à la connexion
            semaines = "?"
        logging.debug(
            "Devoirs : demande du %s au %s (semaines %s).",
            date_debut.strftime("%d/%m/%Y"),
            date_fin.strftime("%d/%m/%Y"),
            semaines,
        )

        all_homework = client.homework(date_from=date_debut, date_to=date_fin)

        if not all_homework:
            # Pronote a répondu, mais sans aucun devoir sur 120 jours. Soit le
            # cahier de textes est vide, soit l'onglet n'est pas accessible à ce
            # compte — auquel cas l'onglet 88 manque dans la liste journalisée à
            # la connexion (« Onglets autorisés par Pronote pour ce compte »).
            logging.warning(
                "Aucun devoir trouvé sur la période du %s au %s (semaines %s). "
                "Si le cahier de textes n'est pas vide côté Pronote, vérifiez que "
                "l'onglet 88 figure dans les onglets autorisés journalisés à la connexion.",
                date_debut.strftime("%d/%m/%Y"),
                date_fin.strftime("%d/%m/%Y"),
                semaines,
            )
            for key in ["devoir", "devoir_Demain"]:
                data[f"Nb_{key}"] = 0
                data[f"Nb_{key}_F"] = 0
                data[f"Nb_{key}_NF"] = 0
                data[key] = []
            # Fusionne agrégats DS vides pour cohérence des cmd Jeedom
            data.update(detect_next_evaluations([]))
            return data

        today = datetime.date.today()

        # « devoir » couvre les jours à venir, pas la seule échéance du jour.
        # L'ancienne définition — hw.date == today — vidait la liste tous les
        # week-ends et tous les soirs sans devoir à rendre le lendemain, alors
        # que Pronote en fournit 120 jours d'avance : le compteur affichait 0
        # devoir pendant que « devoirs demain » en annonçait un.
        # fenetre_jours compte les jours couverts en partant d'aujourd'hui :
        # 1 = le jour même seulement, 7 = la semaine à venir jour compris.
        fin_fenetre = today + datetime.timedelta(days=max(0, fenetre_jours - 1))
        homework_today = sorted(
            (hw for hw in all_homework if today <= hw.date <= fin_fenetre),
            key=lambda hw: hw.date,
        )

        # Les dates reçues : c'est ce qui distingue « Pronote n'a rien renvoyé »
        # de « les devoirs existent mais pas aux dates attendues ».
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            recu = sorted({hw.date for hw in all_homework if hw.date})
            logging.debug(
                "Devoirs : %d reçu(s), échéances %s.",
                len(all_homework),
                ", ".join(d.strftime("%d/%m") for d in recu) or "aucune",
            )

        # Filtrer les devoirs pour le prochain jour d'école
        delta = 1
        next_school_day = None
        while delta < 120:
            next_day = today + datetime.timedelta(days=delta)
            homework_nextday = [hw for hw in all_homework if hw.date == next_day]
            if homework_nextday:
                next_school_day = homework_nextday
                break
            delta += 1
        # Traiter les devoirs pour aujourd'hui
        process_homework(homework_today, data, "devoir")
        # Traiter les devoirs pour le prochain jour d'école
        if next_school_day:
            logging.debug(
                "Devoirs : prochain jour avec devoirs = %s (J+%d), %d devoir(s).",
                (today + datetime.timedelta(days=delta)).strftime("%d/%m/%Y"),
                delta,
                len(next_school_day),
            )
            process_homework(next_school_day, data, "devoir_Demain")
        else:
            logging.info(
                "Aucun devoir trouvé pour le prochain jour d'école (sur %d devoir(s) reçu(s)).",
                len(all_homework),
            )

        # ── Détection des évaluations / DS à venir ─────────────────────────
        # Pattern heuristique sur l'ensemble des devoirs collectés.
        try:
            data.update(detect_next_evaluations(all_homework))
        except Exception as e:
            logging.error("Erreur detect_next_evaluations : %s", e)
            data.update(detect_next_evaluations([]))

        return data
    except Exception as e:
        line_number = e.__traceback__.tb_lineno if e.__traceback__ else "?"
        logging.error(
            "Récupération des devoirs échouée (ligne %s) — %s: %s",
            line_number,
            type(e).__name__,
            e,
        )
        logging.debug("Devoirs — trace complète : %s", traceback.format_exc())
        return data


def notifications(client):
    try:
        data = {"Notification": [], "dernier_Notification": []}
        # Récupération des notifications
        notification_eleve = client.information_and_surveys()
        if not notification_eleve == []:
            notification_eleve = sorted(
                notification_eleve,
                key=lambda information_and_survey: information_and_survey.start_date,
                reverse=True,
            )
            # Récupération des notifications
            for notif in notification_eleve:
                data["Notification"].append(
                    {
                        "sujet": (notif.title),
                        "auteur": (notif.author),
                        "creation": (notif.creation_date).strftime("%d/%m"),
                        "message": _information_content(notif),
                        "categorie": (notif.category),
                        "lu": (notif.read),
                    }
                )
                # récupération du dernier message
            if data["Notification"]:
                data["dernier_Notification"] = (
                    [data["Notification"][0]] if data["Notification"] else []
                )
        return data
    except Exception as e:
        logging.error(
            "Un erreur est retourné sur le traitement des notifications: %s", e
        )


def retards(client):
    try:
        data = {"retard": [], "dernier_retard": [], "nb_retard": 0}
        try:
            all_periods = client.periods
        except Exception as e:
            logging.error(f"Erreur lors de l'accès aux périodes (retards) : {e}")
            return {"retard": [], "dernier_retard": [], "nb_retard": 0, "error": str(e)}

        eq_id = _equipement_en_cours()
        if _presence_deja_refusee(eq_id):
            logging.debug(
                "Collecte des retards ignorée : l'onglet Présence a déjà été refusé "
                "sur ce cycle."
            )
            return data

        all_retards_map = {}
        for period in _periodes_couvrantes(all_periods):
            try:
                for d in period.delays or []:
                    all_retards_map[d.id] = d
            except Exception as e:
                if _refus_de_presence(e):
                    _noter_refus_presence(eq_id, "retards", e)
                    break
                logging.warning(
                    f"Impossible de lire les retards de la période {getattr(period, 'name', '?')} : {e}"
                )

        all_retards = list(all_retards_map.values())
        if all_retards:
            all_retards = sorted(
                all_retards, key=lambda delay: delay.date, reverse=True
            )
            for retard in all_retards:
                data["retard"].append(
                    {
                        "id": retard.id,
                        "date": retard.date.strftime("%d/%m/%y %H:%M"),
                        "justifie": retard.justified,
                        "nb_minutes": retard.minutes,
                        "justification": retard.justification or "",
                        "raison": ", ".join(retard.reasons) if retard.reasons else "",
                    }
                )
            data["nb_retard"] = len(data["retard"])
            data["dernier_retard"] = [data["retard"][0]]
        return data
    except Exception as e:
        line_number = e.__traceback__.tb_lineno
        logging.error(
            "Un erreur est retourné sur le traitement des retards: %s; %s",
            line_number,
            e,
        )


def absences(client):
    try:
        data = {"absence": [], "nb_absences": 0, "derniere_absence": []}
        try:
            all_periods = client.periods
        except Exception as e:
            logging.error(f"Erreur lors de l'accès aux périodes (absences) : {e}")
            return {
                "absence": [],
                "nb_absences": 0,
                "derniere_absence": [],
                "error": str(e),
            }

        eq_id = _equipement_en_cours()
        if _presence_deja_refusee(eq_id):
            logging.debug(
                "Collecte des absences ignorée : l'onglet Présence a déjà été refusé "
                "sur ce cycle."
            )
            return data

        all_absences_map = {}
        for period in _periodes_couvrantes(all_periods):
            try:
                for a in period.absences or []:
                    all_absences_map[a.id] = a
            except Exception as e:
                if _refus_de_presence(e):
                    _noter_refus_presence(eq_id, "absences", e)
                    break
                logging.warning(
                    f"Impossible de lire les absences de la période {getattr(period, 'name', '?')} : {e}"
                )

        all_absences = list(all_absences_map.values())
        if all_absences:
            all_absences = sorted(all_absences, key=lambda a: a.from_date, reverse=True)
            for absence in all_absences:
                data["absence"].append(
                    {
                        "id": absence.id,
                        "date_debut": absence.from_date.strftime("%d/%m/%y %H:%M"),
                        "date_fin": absence.to_date.strftime("%d/%m/%y %H:%M"),
                        "justifie": absence.justified,
                        "nb_heures": absence.hours or "",
                        "nb_jours": absence.days or 0,
                        "raison": ", ".join(absence.reasons) if absence.reasons else "",
                    }
                )
            data["nb_absences"] = len(data["absence"])
            data["derniere_absence"] = [data["absence"][0]]
        return data
    except Exception as e:
        line_number = e.__traceback__.tb_lineno
        logging.error(
            "Un erreur est retourné sur le traitement des absences: %s; %s",
            line_number,
            e,
        )
        return data


def punitions(client):
    try:
        data = {"punition": [], "derniere_punition": [], "Nb_Punitions": 0}
        try:
            all_periods = client.periods
        except Exception as e:
            logging.error(f"Erreur lors de l'accès aux périodes (punitions) : {e}")
            return {
                "punition": [],
                "derniere_punition": [],
                "Nb_Punitions": 0,
                "error": str(e),
            }

        eq_id = _equipement_en_cours()
        if _presence_deja_refusee(eq_id):
            logging.debug(
                "Collecte des punitions ignorée : l'onglet Présence a déjà été refusé "
                "sur ce cycle."
            )
            return data

        all_punitions_map = {}
        for period in _periodes_couvrantes(all_periods):
            try:
                for p in period.punishments or []:
                    all_punitions_map[p.id] = p
            except Exception as e:
                if _refus_de_presence(e):
                    _noter_refus_presence(eq_id, "punitions", e)
                    break
                logging.warning(
                    f"Impossible de lire les punitions de la période {getattr(period, 'name', '?')} : {e}"
                )

        import datetime as _dt

        def _punition_sort_key(p):
            g = p.given
            if isinstance(g, _dt.datetime):
                return g.date()
            return g if isinstance(g, _dt.date) else _dt.date.min

        punitions = (
            sorted(all_punitions_map.values(), key=_punition_sort_key, reverse=True)
            if all_punitions_map
            else []
        )
        if punitions:

            def format_punition(p):
                # Créneaux planifiés (ex : retenues programmées)
                schedule = []
                for s in p.schedule or []:
                    try:
                        start_str = (
                            s.start.strftime("%d/%m %H:%M")
                            if hasattr(s.start, "strftime")
                            else str(s.start)
                        )
                        duree_min = (
                            int(s.duration.total_seconds() // 60)
                            if s.duration
                            else None
                        )
                        schedule.append({"start": start_str, "duree": duree_min})
                    except Exception:
                        pass
                return {
                    "id": p.id,
                    "type": p.nature,
                    "raison": ", ".join(p.reasons) if p.reasons else "",
                    "donneur": p.giver,
                    "date": (
                        p.given.strftime("%d/%m/%Y")
                        if hasattr(p.given, "strftime")
                        else str(p.given)
                    ),
                    "date_court": (
                        p.given.strftime("%d/%m")
                        if hasattr(p.given, "strftime")
                        else str(p.given)
                    ),
                    "circonstances": p.circumstances or "",
                    "exclusion": p.exclusion,
                    "pendant_cours": p.during_lesson,
                    "travail": p.homework or "",
                    "duree": int(p.duration.total_seconds() // 60) if p.duration else 0,
                    "schedule": schedule,
                }

            nbpunition = 0
            for punition in punitions:
                data["punition"].append(format_punition(punition))
                nbpunition += 1
            data["Nb_Punitions"] = nbpunition
            # Dernière punition (liste déjà triée par date desc)
            data["derniere_punition"] = (
                [data["punition"][0]] if data["punition"] else []
            )
        return data
    except Exception as e:
        logging.error("Un erreur est retourné sur le traitement des Punitions: %s", e)
        return data


def ical(client):
    """
    Récupère l'URL du calendrier iCal de l'utilisateur.

    Args:
        client: L'objet client pronotepy connecté.

    L'URL est composée par pronotepy à partir de l'onglet « Informations
    personnelles » (PageInfosPerso, onglet 16), qui n'est pas toujours ouvert :
    un compte sans ce droit fait lever pronotepy, sans que ce soit une panne.

    Returns:
        str: L'URL du calendrier iCal, ou une chaîne vide si non trouvée ou en cas d'erreur.
    """
    try:
        # `export_ical()` est une MÉTHODE. Le code lisait auparavant un attribut
        # `client.ical_url` qui n'a jamais existé dans pronotepy — ni en 2.14 ni
        # en 2.15 — si bien que cette fonction rendait toujours la chaîne vide
        # et que le lien ICAL du panel n'a jamais fonctionné.
        if not hasattr(client, "export_ical"):
            logging.warning(
                "La version de pronotepy installée n'expose pas export_ical()."
            )
            return ""
        ical_url = client.export_ical()
        if ical_url:
            logging.info("URL iCal récupérée avec succès.")
            return ical_url
        logging.warning("Aucune URL iCal n'a été trouvée pour ce compte.")
        return ""
    except Exception as e:
        line_number = e.__traceback__.tb_lineno if e.__traceback__ else "unknown"
        logging.error(
            "Une erreur est survenue lors de la récupération de l'URL iCal: ligne %s - %s",
            line_number,
            e,
        )
        return ""
