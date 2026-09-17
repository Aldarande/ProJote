# ProJote — plugin Jeedom pour Pronote
# Copyright (C) 2024-2026 Aldarande
# Licensed under the GNU Affero General Public License v3 or later.
# See <https://www.gnu.org/licenses/agpl-3.0.html> for full license text.

"""periodes_scolaires.py — Périodes Pronote et calendrier de l'établissement.

Trimestre ou semestre en cours et ses bornes, bornes de l'année scolaire,
prochaines vacances ou prochain jour férié.

Deux choses s'y jouent qui ne vont pas de soi :

* **Ce que Pronote appelle « période » n'est pas ce que l'établissement
  appelle « trimestre ».** La liste mélange les découpages (trimestres,
  semestres, année entière) et plusieurs périodes couvrent la même date.
  `_periodes_couvrantes` retient celles qui portent réellement les données du
  moment — les absences et les notes d'un élève seraient sinon comptées deux
  fois, ou cherchées dans la mauvaise.
* **Les vacances arrivent mêlées aux jours fériés**, dans une même liste de
  paramètres généraux, sans champ qui les distingue.

Extrait de ProJoted.py en v1.6.0, sans modification du code.
"""

import datetime
import logging

import pronotepy


def _parametres_generaux(client):
    """Bloc « General » des paramètres publiés par Pronote à la connexion.

    Il est récupéré une fois pour toutes au login (``FonctionParametres``) :
    le lire ne coûte aucune requête supplémentaire.
    """
    try:
        options = getattr(client, "func_options", None) or {}
        bloc = options.get("dataSec") or options.get("donneesSec") or {}
        return (bloc.get("data") or {}).get("General") or {}
    except Exception as e:
        logging.debug("Paramètres généraux illisibles : %s", e)
        return {}


def _vacances(client):
    """Vacances scolaires et jours fériés publiés par Pronote.

    Ils figurent dans ``listeJoursFeries`` des paramètres généraux, récupérés à
    la connexion : aucune requête supplémentaire. Malgré son nom, cette liste
    mélange les jours fériés (« Armistice 1918 ») et les périodes de vacances
    (« Vacances de la Toussaint »). Une entrée porte ``L`` (libellé), ``N``
    (identifiant), ``dateDebut`` et ``dateFin`` — relevé sur PRONOTE 2026.2.5 ;
    ``date`` est accepté en second recours, les versions antérieures ayant pu
    nommer ce champ autrement.

    Retourne la liste triée par date, chaque élément valant
    ``{"nom", "debut", "fin"}`` au format jj/mm/aaaa.
    """
    general = _parametres_generaux(client)
    brut = general.get("listeJoursFeries")
    if isinstance(brut, dict):
        brut = brut.get("V")
    if not isinstance(brut, list) or not brut:
        return []

    if isinstance(brut[0], dict):
        logging.debug("Vacances : clés d'une entrée = %s", sorted(brut[0].keys()))

    def _date(entree, *cles):
        for cle in cles:
            valeur = entree.get(cle)
            if isinstance(valeur, dict):
                valeur = valeur.get("V")
            if valeur:
                try:
                    return pronotepy.dataClasses.Util.datetime_parse(valeur)
                except Exception:
                    continue
        return None

    vacances = []
    for entree in brut:
        if not isinstance(entree, dict):
            continue
        fin = _date(entree, "dateFin", "date")
        debut = _date(entree, "dateDebut", "date") or fin
        if not fin:
            continue
        vacances.append(
            {
                "nom": entree.get("L", "") or "",
                "debut": debut.strftime("%d/%m/%Y") if debut else "",
                "fin": fin.strftime("%d/%m/%Y"),
                "_fin": fin,
            }
        )
    vacances.sort(key=lambda v: v["_fin"])
    for v in vacances:
        del v["_fin"]
    return vacances


def _bornes_annee_scolaire(client):
    """Premier et dernier jour de l'année scolaire, tels que Pronote les publie.

    Journalise au passage ce que le serveur expose sur les jours fériés et les
    vacances : pronotepy n'en donne aucune représentation, et leur présence
    varie d'un établissement à l'autre.
    """
    general = _parametres_generaux(client)
    if not general:
        return None, None

    def _lire(cle):
        valeur = general.get(cle)
        if isinstance(valeur, dict):
            valeur = valeur.get("V")
        if not valeur:
            return None
        try:
            return pronotepy.dataClasses.Util.datetime_parse(valeur)
        except Exception:
            return None

    interessants = sorted(
        cle
        for cle in general
        if any(m in cle.lower() for m in ("ferie", "vacance", "conge", "fermeture"))
    )
    if interessants:
        for cle in interessants:
            valeur = general.get(cle)
            if isinstance(valeur, dict):
                valeur = valeur.get("V", valeur)
            taille = len(valeur) if isinstance(valeur, (list, dict)) else valeur
            logging.debug("Calendrier publié par Pronote : %s = %s entrée(s)", cle, taille)
    else:
        logging.debug(
            "Pronote ne publie ni jours fériés ni vacances dans ses paramètres généraux."
        )

    return _lire("PremiereDate"), _lire("DerniereDate")


def _periodes_couvrantes(periods):
    """Sous-ensemble minimal de périodes couvrant la même plage de dates.

    Pronote publie une douzaine de découpages qui se recouvrent — « Année
    continue », « année », semestres, mi-semestres, trimestres, « DNB blanc »,
    « Hors période »… Or les absences, retards et punitions s'interrogent par
    plage de dates (requête ``PagePresence``) : les demander période par période
    renvoie douze fois les mêmes enregistrements.

    Le coût est loin d'être théorique. Sur les serveurs 2026, chaque
    ``PagePresence`` échoue d'abord sur « La page a expiré », ce qui pousse
    pronotepy à se ré-authentifier entièrement avant de rejouer la requête.
    Mesuré sur un cycle réel : 12 périodes × 3 collectes = 36 requêtes, 72 appels
    et 40 authentifications — chacune faisant tourner le jeton, jusqu'à la
    suspension de l'adresse IP par Pronote.

    On retient donc la période la plus large, puis uniquement celles qui
    dépassent de la couverture déjà acquise. La plage interrogée reste
    rigoureusement identique, mais une seule requête suffit dans le cas normal.
    """
    valides = []
    for period in periods or []:
        debut = getattr(period, "start", None)
        fin = getattr(period, "end", None)
        if debut and fin and fin >= debut:
            valides.append((debut, fin, period))
    if not valides:
        # Aucune date exploitable : on ne sait pas raisonner, on rend tout.
        return list(periods or [])

    # Les périodes Pronote se suivent sans se chevaucher : un trimestre finit le
    # 23 novembre et le suivant commence le 24. Sans tolérance, la fusion verrait
    # un trou d'une journée entre deux périodes pourtant contiguës, et garderait
    # inutilement toute période à cheval sur la jointure.
    tolerance = datetime.timedelta(days=1)

    def _couvert(debut, fin, intervalles):
        return any(d <= debut and fin <= f for d, f in intervalles)

    retenues = []
    couverture = []
    for debut, fin, period in sorted(valides, key=lambda v: v[1] - v[0], reverse=True):
        if _couvert(debut, fin, couverture):
            continue
        retenues.append(period)
        couverture = sorted(couverture + [(debut, fin)])
        fusionnes = [couverture[0]]
        for d, f in couverture[1:]:
            dernier_d, dernier_f = fusionnes[-1]
            if d <= dernier_f + tolerance:
                fusionnes[-1] = (dernier_d, max(dernier_f, f))
            else:
                fusionnes.append((d, f))
        couverture = fusionnes

    if len(retenues) < len(valides):
        logging.debug(
            "Périodes : %d découpages retournés par Pronote, %d suffisent à couvrir "
            "la même plage de dates.",
            len(valides),
            len(retenues),
        )
    return retenues


def periodes(client):
    """
    Récupère la période Pronote en cours et ses dates de début / fin.

    Pronote publie plusieurs découpages simultanés (trimestres, semestres,
    « Année continue »…). `client.current_period` renvoie celui que Pronote
    désigne lui-même par défaut pour l'onglet Notes : c'est la source la plus
    fiable, et elle évite d'avoir à deviner. En cas d'échec (structure absente
    sur certaines instances), on retombe sur la période qui contient la date du
    jour, en retenant la plus courte — sans quoi un découpage englobant toute
    l'année scolaire l'emporterait sur le trimestre réellement en cours.

    Retourne les trois valeurs câblées aux commandes Jeedom
    (periode_courante / periode_debut / periode_fin), plus la liste complète
    des périodes de l'année à toutes fins utiles.
    """
    data = {
        "periode_courante": "",
        "periode_debut": "",
        "periode_fin": "",
        "annee_debut": "",
        "annee_fin": "",
        "periodes": [],
    }

    try:
        all_periods = list(client.periods or [])
    except Exception as e:
        logging.error("Erreur lors de l'accès aux périodes : %s", e)
        data["error"] = str(e)
        return data

    def _format_date(valeur):
        """Formate une date Pronote comme le reste du plugin (jj/mm/aaaa)."""
        if not valeur:
            return ""
        try:
            return valeur.strftime("%d/%m/%Y")
        except Exception:
            return ""

    courante = None
    try:
        courante = client.current_period
    except Exception as e:
        logging.debug(
            "current_period indisponible (%s) : repli sur la date du jour.", e
        )

    if courante is None:
        today = datetime.date.today()
        candidates = []
        for period in all_periods:
            debut = getattr(period, "start", None)
            fin = getattr(period, "end", None)
            if not debut or not fin:
                continue
            try:
                if debut.date() <= today <= fin.date():
                    candidates.append((fin - debut, period))
            except Exception:
                continue
        if candidates:
            # La plus courte : « Trimestre 1 » plutôt que « Année continue ».
            courante = min(candidates, key=lambda c: c[0])[1]

    id_courante = getattr(courante, "id", None) if courante is not None else None
    for period in all_periods:
        data["periodes"].append(
            {
                "nom": getattr(period, "name", "") or "",
                "debut": _format_date(getattr(period, "start", None)),
                "fin": _format_date(getattr(period, "end", None)),
                "en_cours": id_courante is not None
                and getattr(period, "id", None) == id_courante,
            }
        )

    # Bornes de l'année scolaire. Pronote les publie dans les paramètres
    # généraux récupérés à la connexion (aucune requête supplémentaire) ; à
    # défaut, la période la plus large fait référence — « Année continue »
    # couvre par construction toute l'année.
    debut_annee, fin_annee = _bornes_annee_scolaire(client)
    if debut_annee is None or fin_annee is None:
        plus_large = None
        for period in all_periods:
            debut = getattr(period, "start", None)
            fin = getattr(period, "end", None)
            if not debut or not fin or fin < debut:
                continue
            if plus_large is None or (fin - debut) > (plus_large[1] - plus_large[0]):
                plus_large = (debut, fin)
        if plus_large:
            debut_annee, fin_annee = plus_large
    data["annee_debut"] = _format_date(debut_annee)
    data["annee_fin"] = _format_date(fin_annee)

    # Vacances et jours fériés : la liste complète, plus la prochaine échéance
    # à venir (celle dont la fin n'est pas encore passée).
    data["vacances"] = _vacances(client)
    aujourdhui = datetime.date.today().strftime("%Y%m%d")

    def _tri(valeur):
        jour, mois, annee = valeur.split("/")
        return annee + mois + jour

    for v in data["vacances"]:
        if v["fin"] and _tri(v["fin"]) >= aujourdhui:
            data["vacances_nom"] = v["nom"]
            data["vacances_debut"] = v["debut"]
            data["vacances_fin"] = v["fin"]
            break
    else:
        data["vacances_nom"] = ""
        data["vacances_debut"] = ""
        data["vacances_fin"] = ""

    if courante is not None:
        data["periode_courante"] = getattr(courante, "name", "") or ""
        data["periode_debut"] = _format_date(getattr(courante, "start", None))
        data["periode_fin"] = _format_date(getattr(courante, "end", None))
        logging.debug(
            "Période en cours : %s (%s → %s)",
            data["periode_courante"],
            data["periode_debut"],
            data["periode_fin"],
        )
    else:
        logging.warning(
            "Aucune période en cours identifiée parmi les %d périodes retournées "
            "par Pronote.",
            len(all_periods),
        )

    return data
