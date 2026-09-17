# ProJote — plugin Jeedom pour Pronote
# Copyright (C) 2024-2026 Aldarande
# Licensed under the GNU Affero General Public License v3 or later.
# See <https://www.gnu.org/licenses/agpl-3.0.html> for full license text.

"""format_pronote.py — Mise en forme des objets pronotepy pour Jeedom.

Ces fonctions ne parlent à personne : elles reçoivent un objet pronotepy (ou un
dictionnaire déjà extrait) et rendent la structure que la charge transmise à
Jeedom attend. Aucune requête réseau, aucun état partagé, aucune dépendance au
démon — c'est ce qui permet de les éprouver sans compte Pronote.

Deux précautions reviennent partout et méritent d'être dites une fois :

* **Tout est échappé avant de devenir du HTML.** Les libellés viennent de
  l'établissement — nom de plat, intitulé de cours, titre de notification — et
  finissent dans le widget. `html.escape` est appliqué à chaque insertion.
* **Aucun attribut pronotepy n'est supposé présent.** La bibliothèque renomme
  et déplace ses champs d'une version à l'autre ; `_safe_attr` essaie plusieurs
  noms et retombe sur une valeur neutre plutôt que de lever.

Extrait de ProJoted.py en v1.6.0, sans modification du code.
"""

import logging


def cours_affiche_from_lesson(lesson_data):
    if lesson_data.detention == True:
        return "RETENUE"
    try:
        return lesson_data.subject.name if lesson_data.subject else "Repas"
    except Exception:
        return "Repas"


def build_menu_data(menu):
    """
    Construit un dictionnaire contenant toutes les informations d'un menu Pronote.
    Args:
        menu (pronotepy.Menu): Un objet Menu pronotepy.
    Returns:
        dict: Un dictionnaire structuré avec tous les champs utiles.
    """

    def serialize_food_list(food_list):
        if not food_list:
            return []
        result = []
        for food in food_list:
            result.append(
                {
                    "id": getattr(food, "id", ""),
                    "name": getattr(food, "name", ""),
                    "labels": [
                        {
                            "id": getattr(label, "id", ""),
                            "name": getattr(label, "name", ""),
                            "color": getattr(label, "color", ""),
                        }
                        for label in getattr(food, "labels", [])
                    ],
                }
            )
        return result

    return {
        "id": getattr(menu, "id", ""),
        "name": getattr(menu, "name", ""),
        "date": menu.date.strftime("%Y-%m-%d") if getattr(menu, "date", None) else "",
        "is_lunch": getattr(menu, "is_lunch", False),
        "is_dinner": getattr(menu, "is_dinner", False),
        "first_meal": serialize_food_list(getattr(menu, "first_meal", [])),
        "main_meal": serialize_food_list(getattr(menu, "main_meal", [])),
        "side_meal": serialize_food_list(getattr(menu, "side_meal", [])),
        "other_meal": serialize_food_list(getattr(menu, "other_meal", [])),
        "cheese": serialize_food_list(getattr(menu, "cheese", [])),
        "dessert": serialize_food_list(getattr(menu, "dessert", [])),
    }


def build_cours_data(lesson_data):
    """
    Construit un dictionnaire contenant les informations formatées d'un cours.
    Args:
        lesson_data (object): Un objet représentant les données d'un cours.
    Returns:
        dict: Un dictionnaire contenant les informations formatées du cours.
    """
    return {
        "id": lesson_data.id,
        "date_heure": lesson_data.start.strftime("%d/%m/%Y, %H:%M"),
        "date": lesson_data.start.strftime("%d/%m/%Y"),
        "heure": lesson_data.start.strftime("%H%M"),
        "heure_fin": lesson_data.end.strftime("%H%M"),
        "cours": cours_affiche_from_lesson(lesson_data),
        "Professeur": lesson_data.teacher_name,
        "salle": lesson_data.classroom,
        "annulation": lesson_data.canceled,
        "status": lesson_data.status,
        "background_color": lesson_data.background_color,
        # Ces sept champs étaient lus sous leur nom dans le JSON brut PRONOTE
        # (estServiceGroupe, cahierDeTextes…). Or `Lesson` dérive d'un objet à
        # slots, sans __getattr__ : aucun de ces noms n'existe, et les sept
        # valeurs étaient donc invariablement None dans les commandes d'emploi
        # du temps. On lit désormais les attributs que pronotepy expose vraiment.
        "est_service_groupe": bool(getattr(lesson_data.subject, "groups", False))
        if lesson_data.subject
        else None,
        "cahier_de_texte": getattr(lesson_data, "test", None),
        "est_retenue": getattr(lesson_data, "detention", None),
        "liste_visios": getattr(lesson_data, "virtual_classrooms", None),
        "dispense_eleve": getattr(lesson_data, "exempted", None),
        "est_sortie_pedagogique": getattr(lesson_data, "outing", None),
        # Doublon assumé d'« annulation » : la clé est déjà consommée ailleurs.
        "est_Annule": getattr(lesson_data, "canceled", None),
    }


def _menu_to_text(menu_data):
    """Convertit un menu sérialisé (build_menu_data) en chaîne lisible.

    Format : "Entrée · Plat · Accompagnement · Fromage · Dessert"
    Les sections vides sont omises. Renvoie "" si aucun aliment.
    """
    sections = []
    for key in ("first_meal", "main_meal", "side_meal", "cheese", "dessert", "other_meal"):
        items = menu_data.get(key) or []
        names = [str(item.get("name", "")).strip() for item in items if item.get("name")]
        names = [n for n in names if n]
        if names:
            sections.append(", ".join(names))
    return " · ".join(sections)


def _menu_labels(menu_data):
    """Liste dédupliquée des labels/allergènes d'un menu (dans l'ordre d'apparition).

    Les labels Pronote (Bio, Local, Porc, Allergènes…) sont déjà sérialisés par
    build_menu_data sous chaque aliment. On les agrège au niveau du menu pour
    un affichage compact dans le widget.
    """
    seen = []
    for key in ("first_meal", "main_meal", "side_meal", "cheese", "dessert", "other_meal"):
        for item in menu_data.get(key) or []:
            for label in item.get("labels") or []:
                name = str(label.get("name", "")).strip()
                if name and name not in seen:
                    seen.append(name)
    return seen


def _menu_to_html_row(menu_data):
    """Une ligne HTML compacte représentant un menu pour le widget."""
    import html as _html_mod

    date_iso = menu_data.get("date", "")
    is_lunch = menu_data.get("is_lunch", False)
    is_dinner = menu_data.get("is_dinner", False)
    repas_label = "🍽️ Midi" if is_lunch else ("🌙 Soir" if is_dinner else "🍴 Repas")
    text = _menu_to_text(menu_data) or "—"

    # Labels / allergènes (Bio, Local, Porc…) en puces discrètes.
    labels = _menu_labels(menu_data)
    labels_html = ""
    if labels:
        chips = "".join(
            f'<span class="pj-menu-label">{_html_mod.escape(name)}</span>' for name in labels
        )
        labels_html = f'<span class="pj-menu-labels">{chips}</span>'

    return (
        f'<div class="pj-menu-row">'
        f'<span class="pj-menu-date">{_html_mod.escape(date_iso)}</span>'
        f'<span class="pj-menu-type">{_html_mod.escape(repas_label)}</span>'
        f'<span class="pj-menu-text">{_html_mod.escape(text)}</span>'
        f"{labels_html}"
        f"</div>"
    )


def _truncate(text, max_len=200):
    """Tronque proprement un texte avec ellipse."""
    if not text:
        return ""
    text = str(text).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _safe_attr(obj, *names, default=""):
    """Renvoie le premier attribut existant et non-vide parmi `names`.

    Utile pour pronotepy qui peut renommer/déplacer des attributs entre versions.
    """
    for name in names:
        try:
            val = getattr(obj, name, None)
            if val not in (None, ""):
                return val
        except Exception:
            continue
    return default


def _information_content(notif):
    """Contenu texte d'une information Pronote, quelle que soit la version de pronotepy.

    pronotepy <= 2.14 exposait `Information.content` comme une propriété (le texte
    était déjà chargé). Depuis 2.15, c'est une méthode : le contenu est récupéré à
    la demande par une requête supplémentaire vers Pronote. Sans ce garde-fou, le
    widget recevait l'objet méthode lui-même (non sérialisable en JSON).
    """
    try:
        content = getattr(notif, "content", "")
        return content() if callable(content) else content
    except Exception as e:
        logging.warning(
            "Contenu de l'information « %s » non récupéré : %s",
            _safe_attr(notif, "title", default="?"),
            e,
        )
        return ""
