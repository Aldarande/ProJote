# ProJote — plugin Jeedom pour Pronote
# Copyright (C) 2024-2026 Aldarande
# Licensed under the GNU Affero General Public License v3 or later.
# See <https://www.gnu.org/licenses/agpl-3.0.html> for full license text.

"""
pronote_compat.py — Correctifs de compatibilité appliqués à pronotepy.

Deux correctifs sans rapport entre eux, tous deux posés sur les classes de
pronotepy au chargement du plugin : le traitement du challenge
d'authentification (protocole PRONOTE 2026), et la suppression d'une
ré-authentification inutile sur les onglets non accessibles.

# Challenge d'authentification non chiffré (PRONOTE >= 2026.2.5)

Depuis le 2 septembre 2026, certaines instances PRONOTE ne chiffrent plus le
« challenge » renvoyé à l'Identification. pronotepy 2.15.6, lui, applique
toujours le cycle historique :

    déchiffrer le challenge → retirer l'alea (un caractère sur deux) → rechiffrer

Sur ces serveurs, la première étape échoue et pronotepy lève
``CryptoError("Decryption failed while trying to un pad")``, quel que soit le
mode de connexion (QR Code, identifiants ou jeton). Signature du symptôme,
identique à celle relevée sur notre instance :

    - réponse Identification sans champ « alea » ;
    - challenge d'un seul bloc AES (16 octets) ;
    - déchiffrement du contenu du QR Code réussi juste avant.

Le serveur attend en réalité le chiffrement direct de la chaîne brute. Voir
https://github.com/bain3/pronotepy/issues/346 (cause et correctif) et
https://github.com/bain3/pronotepy/issues/348 (même instance que la nôtre,
PRONOTE 2026.2.5.7).

Le JS officiel du client PRONOTE 2026 confirme le nouveau comportement : sa
méthode ``getNouveauChallenge()`` chiffre directement la chaîne reçue, sans
aucune étape de déchiffrement ni de retrait d'aléa. Ce n'est donc pas un
contournement mais bien le protocole en vigueur.

Plutôt que de dupliquer les 110 lignes de ``ClientBase._login``, on intercepte
``_Encryption.aes_decrypt`` **pendant la seule durée du login**. Pour le
challenge, on renvoie sa chaîne hexadécimale avec chaque caractère doublé :
``_enleverAlea()`` — qui ne garde qu'un caractère sur deux — restitue alors
exactement le challenge, que pronotepy rechiffre et renvoie. Le résultat est
celui du correctif de l'issue #346, sans réécrire la méthode.

Le patch est délibérément limité :

    - actif uniquement pendant ``_login`` (restauré dans un ``finally``), pour
      ne pas masquer un code PIN erroné : le champ « login » d'un QR Code fait
      lui aussi un seul bloc, et un PIN faux doit continuer à lever
      QRCodeDecryptError ;
    - réservé à l'instance ``_Encryption`` locale à ``_login`` — celle qui
      traite le challenge — et non à celle de la communication, qui déchiffre
      les réponses du serveur et la clé de session dans ``after_auth`` ;
    - déclenché sur un challenge d'un seul bloc AES, signature du protocole
      2026 : les serveurs antérieurs renvoient une chaîne entrelacée d'aléa,
      toujours plus longue. Trancher sur la taille plutôt que sur l'échec du
      déchiffrement évite un piège : avec une mauvaise clé, le dépadding
      réussit par hasard environ une fois sur 256, et l'ancien chemin
      produirait alors une réponse fausse — soit, au rythme du démon, un échec
      inexpliqué tous les deux jours environ.

À retirer quand pronotepy publiera son propre correctif (le plancher de version
de requirements.txt devra alors être relevé).
"""

import logging

_applied = False


# Listes que pronotepy lit sans précaution dans la réponse de ListeMessagerie.
# Une liste vide dit exactement ce que leur absence signifie : aucune étiquette,
# aucune discussion.
_LISTES_MESSAGERIE = ("listeEtiquettes", "listeMessagerie")


def _reparer_reponse_messagerie(function_name, reponse):
    """Complète les listes que le serveur omet dans la réponse de messagerie.

    pronotepy lit ``listeEtiquettes["V"]`` puis ``listeMessagerie["V"]`` sans
    vérifier leur présence. Tous les serveurs ne les renvoient pas : sur un
    lycée éprouvé le 18 septembre 2026, les deux manquaient, et la messagerie
    échouait à chaque cycle — d'abord sur l'une, puis sur l'autre une fois la
    première réparée.

    Ne touche qu'à la réponse de ``ListeMessagerie``, et seulement aux clés
    absentes : un serveur qui les renvoie garde les siennes intactes.

    Args:
        function_name: nom de la fonction PRONOTE appelée.
        reponse: la réponse déchiffrée, telle que rendue par pronotepy.

    Returns:
        La réponse, complétée le cas échéant.
    """
    if function_name != "ListeMessagerie" or not isinstance(reponse, dict):
        return reponse
    donnees = reponse.get("dataSec", {}).get("data")
    if not isinstance(donnees, dict):
        return reponse
    manquantes = [cle for cle in _LISTES_MESSAGERIE if cle not in donnees]
    if manquantes:
        # Relevées AVANT l'insertion : journaliser les clés après aurait montré
        # celles qu'on vient d'ajouter, ce qui ne renseigne sur rien. Ce sont
        # les clés réellement envoyées par le serveur qui permettent de
        # distinguer « messagerie vide » d'une réponse de forme inattendue,
        # sans avoir à rejouer une session sur le compte concerné.
        recues = sorted(donnees.keys())
        for cle in manquantes:
            donnees[cle] = {"V": []}
        logging.debug(
            "pronote_compat :: ListeMessagerie sans %s — liste(s) vide(s) "
            "ajoutée(s). Clés réellement reçues : %s",
            ", ".join("« %s »" % c for c in manquantes),
            recues or "aucune",
        )
    return reponse


def apply() -> None:
    """Installe les correctifs. Idempotent : les appels suivants sont ignorés.

    Ne lève jamais : ce correctif s'appuie sur des détails internes de
    pronotepy (``ClientBase._login``, ``_Encryption.aes_decrypt``). Si une
    version future les déplace, on veut une connexion qui échoue avec le
    message d'origine — pas un démon qui refuse de démarrer.
    """
    global _applied
    if _applied:
        return

    try:
        _install()
    except Exception as e:
        logging.warning(
            "pronote_compat :: correctif « challenge non chiffré » non installé "
            "(%s: %s). La connexion échouera sur les serveurs PRONOTE >= 2026.2.5.",
            type(e).__name__,
            e,
        )
        return

    _applied = True
    logging.debug(
        "pronote_compat :: correctif « challenge non chiffré » installé "
        "(pronotepy issues #346 / #348)."
    )


def _install() -> None:
    """Pose effectivement le correctif sur les classes de pronotepy."""
    from pronotepy import clients
    from pronotepy.exceptions import CryptoError, PronoteAPIError
    from pronotepy.pronoteAPI import _Encryption

    _original_decrypt = _Encryption.aes_decrypt
    _original_login = clients.ClientBase._login

    def _challenge_brut(data: bytes) -> bytes:
        """Rend le challenge tel quel, sous une forme que pronotepy restituera.

        pronotepy applique `_enleverAlea()` (un caractère sur deux) au résultat
        du déchiffrement ; on double donc chaque caractère pour qu'il retrouve
        la chaîne d'origine, qu'il rechiffrera et renverra au serveur.
        """
        return "".join(c * 2 for c in data.hex().upper()).encode()

    def _login_avec_repli(self) -> bool:
        # Le challenge est déchiffré dans _login par une instance _Encryption
        # locale, distincte de celle de la communication (qui sert, elle, aux
        # réponses du serveur et à la clé de session dans after_auth). Cette
        # distinction permet de ne détourner QUE le challenge.
        communication = getattr(self, "communication", None)
        chiffrement_session = getattr(communication, "encryption", None)

        def _decrypt(enc_self, data: bytes) -> bytes:
            challenge = (
                chiffrement_session is not None
                and enc_self is not chiffrement_session
                and len(data) == 16
            )
            if challenge:
                # Un challenge d'un seul bloc AES est la signature du protocole
                # PRONOTE >= 2026.2.5 : le client officiel ne le déchiffre plus
                # du tout (getNouveauChallenge() chiffre la chaîne brute). On
                # tranche donc sur la taille plutôt que sur l'échec du
                # déchiffrement : avec une mauvaise clé, le dépadding réussit
                # par hasard une fois sur 256 environ, et pronotepy repartirait
                # alors sur l'ancien chemin pour produire une réponse fausse.
                # Sur les serveurs antérieurs, le challenge contient une chaîne
                # entrelacée d'aléa : il fait toujours plus d'un bloc.
                logging.info(
                    "pronote_compat :: challenge d'un seul bloc : mode PRONOTE "
                    ">= 2026.2.5 (chiffrement direct de la chaîne brute)."
                )
                return _challenge_brut(data)
            try:
                return _original_decrypt(enc_self, data)
            except CryptoError:
                if len(data) != 16:
                    raise
                # Filet de sécurité si la structure interne de pronotepy change
                # et que le challenge n'est plus reconnaissable ci-dessus.
                logging.info(
                    "pronote_compat :: repli sur le mode PRONOTE >= 2026.2.5 "
                    "après échec du déchiffrement d'un bloc unique."
                )
                return _challenge_brut(data)

        _Encryption.aes_decrypt = _decrypt
        try:
            return _original_login(self)
        finally:
            _Encryption.aes_decrypt = _original_decrypt

    clients.ClientBase._login = _login_avec_repli

    # ── Onglets non accessibles ───────────────────────────────────────────
    # pronotepy rejette lui-même, avant tout appel réseau, une requête visant un
    # onglet absent de « authorized_onglets ». Mais ClientBase.post traite cette
    # PronoteAPIError comme n'importe quelle autre : il se ré-authentifie
    # entièrement puis rejoue la requête — qui échoue de nouveau, forcément,
    # puisqu'une nouvelle session ne donne aucun droit supplémentaire.
    #
    # Le coût n'est pas nul : chaque authentification fait tourner le jeton de
    # connexion, et leur accumulation a valu une suspension d'adresse IP par
    # Pronote. On lève donc l'erreur avant d'entrer dans ce mécanisme.
    _original_post = clients.ClientBase.post

    def _post_sans_reauth_inutile(self, function_name, onglet=None, data=None):
        autorises = getattr(
            getattr(self, "communication", None), "authorized_onglets", None
        )
        if onglet is not None and autorises and onglet not in autorises:
            raise PronoteAPIError(
                "Onglet %s non accessible pour ce compte (%s)"
                % (onglet, function_name)
            )
        reponse = _original_post(self, function_name, onglet, data)
        return _reparer_reponse_messagerie(function_name, reponse)

    clients.ClientBase.post = _post_sans_reauth_inutile

    # ── Messagerie : étiquettes absentes de la réponse ────────────────────
    # pronotepy lit les étiquettes de discussion sans précaution :
    #
    #     labels = {l["N"]: l["G"]
    #               for l in discussions["dataSec"]["data"]["listeEtiquettes"]["V"]}
    #
    # Tous les serveurs ne renvoient pas cette clé. Relevé le 17 septembre 2026
    # sur un lycée : la messagerie y échouait à chaque cycle sur un
    # « KeyError: 'listeEtiquettes' », et l'onglet restait vide pour toujours.
    # Aucune version publiée de pronotepy ne le corrige — vérifié jusqu'à la
    # 2.15.7 du 3 septembre 2026.
    #
    # La réparation est faite sur la réponse plutôt que sur discussions() :
    # c'est la forme renvoyée par le serveur qui est en cause, et une liste
    # d'étiquettes vide donne exactement ce que pronotepy attend — des
    # discussions sans étiquette, ce qui est le cas.
    # Réparer la méthode aurait supposé d'en recopier le corps, et de le
    # maintenir à chaque version.

    # ── Compte parent : enfant perdu après réinitialisation de session ────
    # Client.refresh() rejoue toute la connexion quand PRONOTE renvoie « La page
    # a expiré ». ParentClient ne la surcharge pas, alors que la reconnexion
    # défait tout ce que ParentClient avait mis en place :
    #
    #   - parametres_utilisateur["…"]["ressource"] redevient la ressource du
    #     PARENT, alors que set_child l'avait remplacée par celle de l'enfant ;
    #   - self.children n'est pas reconstruit et self._selected_child continue
    #     de désigner l'objet de la session morte.
    #
    # Or les identifiants de ressource PRONOTE (« 46#… ») sont propres à une
    # session : relevés sur deux connexions successives du même compte, ils
    # diffèrent. ParentClient.post signant chaque requête avec
    # « membre: {N: _selected_child.id} », toutes les requêtes qui suivent une
    # réinitialisation portent un identifiant périmé et PRONOTE répond « La page
    # a expiré », en boucle. Symptômes relevés sur un compte parent 2026 :
    # devoirs vides (« Unknown error from pronote: 20 »), et évaluations en
    # KeyError 'listeOngletsPourPeriodes' — cette clé n'existant que sur la
    # ressource d'un enfant, jamais sur celle du parent.
    #
    # On reconstruit donc la liste des enfants depuis la session fraîche, puis
    # on re-sélectionne le même enfant PAR SON NOM, seul identifiant stable
    # d'une session à l'autre.
    #
    # Correctif posé à part : il vise d'autres classes que les deux précédents,
    # et son absence ne doit pas priver la connexion du correctif « challenge ».
    if not hasattr(clients, "Client") or not hasattr(clients, "ParentClient"):
        logging.warning(
            "pronote_compat :: correctif « enfant après réinitialisation » non "
            "installé : pronotepy n'expose pas Client/ParentClient."
        )
        return

    _original_refresh = clients.Client.refresh

    def _refresh_avec_enfant(self):
        precedent = getattr(self, "_selected_child", None)
        nom = getattr(precedent, "name", None)

        _original_refresh(self)

        if not isinstance(self, clients.ParentClient):
            return
        try:
            from pronotepy import dataClasses

            self.children = [
                dataClasses.ClientInfo(self, c)
                for c in self.parametres_utilisateur["dataSec"]["data"]["ressource"][
                    "listeRessources"
                ]
            ]
            if self.children:
                self.set_child(nom if nom else self.children[0])
                logging.debug(
                    "pronote_compat :: enfant « %s » re-sélectionné après "
                    "réinitialisation de session.",
                    getattr(self._selected_child, "name", "?"),
                )
        except Exception as e:
            # Ne jamais faire échouer la reconnexion elle-même : sans cette
            # reprise, on retombe simplement sur le comportement d'origine.
            logging.warning(
                "pronote_compat :: enfant non re-sélectionné après "
                "réinitialisation (%s: %s).",
                type(e).__name__,
                e,
            )

    clients.Client.refresh = _refresh_avec_enfant

    # ── Compte parent : ParentClient.post contourne les deux garde-fous ───
    # ParentClient.post ne délègue pas à ClientBase.post : il redescend
    # directement vers _Communication.post. Le garde-fou « onglet non
    # accessible » posé plus haut ne le protège donc pas, et sur un compte
    # parent chaque appel visant un onglet non accordé (la messagerie, ici :
    # l'onglet 131 est absent des onglets autorisés) part sur le réseau, échoue,
    # et déclenche un refresh() — soit une authentification complète, donc une
    # rotation du jeton, à chaque cycle. C'est précisément la dépense que les
    # correctifs de performance précédents cherchaient à supprimer.
    #
    # Second défaut, dans la reprise elle-même : « post_data » est construit
    # AVANT le refresh, avec l'identifiant de l'enfant de la session courante.
    # Après réinitialisation cet identifiant est périmé (ils changent à chaque
    # session), et la requête rejouée ne peut donc que se faire refuser. On la
    # reconstruit après le refresh.
    def _post_parent_protege(self, function_name, onglet=None, data=None):
        autorises = getattr(
            getattr(self, "communication", None), "authorized_onglets", None
        )
        if onglet is not None and autorises and onglet not in autorises:
            raise PronoteAPIError(
                "Onglet %s non accessible pour ce compte (%s)"
                % (onglet, function_name)
            )

        def _payload():
            post_data = {}
            if onglet:
                post_data["Signature"] = {
                    "onglet": onglet,
                    "membre": {"N": self._selected_child.id, "G": 4},
                }
            if data:
                post_data["data"] = data
            return post_data

        try:
            return _reparer_reponse_messagerie(
                function_name, self.communication.post(function_name, _payload())
            )
        except PronoteAPIError as e:
            if type(e).__name__ == "ExpiredObject":
                raise

            # Garde anti-récursion, repris de ClientBase.post (« prevent refresh
            # recursion ») que cette redéfinition avait laissé tomber.
            #
            # Sans lui, la réparation se mord la queue : refresh() appelle
            # _login(), qui poste « Identification » — donc cette méthode. Si le
            # serveur refuse cette Identification à son tour, on relance un
            # refresh, qui repose Identification, indéfiniment. Un seul cycle a
            # produit 415 ré-authentifications en quelques secondes le
            # 13 septembre 2026, jusqu'à ce que PRONOTE suspende l'adresse IP —
            # suspension dont la durée double à chaque récidive.
            if getattr(self, "_refreshing", False):
                raise

            # Le libellé PRONOTE est journalisé avec le code : sans lui, on ne
            # peut pas savoir si une réinitialisation de session était la bonne
            # réponse, et l'on paie une authentification complète à l'aveugle.
            logging.debug(
                "pronote_compat :: %s refusé (G=%s « %s ») — réinitialisation "
                "puis rejeu avec l'identifiant d'enfant à jour.",
                function_name,
                getattr(e, "pronote_error_code", None),
                getattr(e, "pronote_error_msg", None) or e,
            )
            self._refreshing = True
            try:
                self.refresh()
            finally:
                # `finally` et non simple affectation : si refresh() lève, le
                # drapeau resterait armé et bloquerait toute réparation future
                # sur ce client.
                self._refreshing = False
            # _payload() est ré-évalué ici : il lit le _selected_child
            # reconstruit par le refresh corrigé ci-dessus.
            return _reparer_reponse_messagerie(
                function_name, self.communication.post(function_name, _payload())
            )

    clients.ParentClient.post = _post_parent_protege
