try:
    # TO DO :: add log to plugin for troubleshoote
    import pronotepy
    from pronotepy.ent import *
    import sys
    import json

    # type de commande python3 ../../resources/ProJoted/LoginConnect.py 'E2A24D72F39BA48F2E400CA838E5CCB5F5F6733C64FA762F8FEF473AA7D5BBAD05F641FFE8C6CFE9486564470BB8FCD0F9E4EAE77338B2B45B9A28DB85EC79AE0729E20FF4D0D60D79A7E0CA0380364CB05DC4C1FC3D71E2575423FECF4A0BDD74ADE24A020B222916617B30B189C724' '4C0B20E070291B38E256452F80138CBE' 'https://0912109y.index-education.net/pronote/parent.html?identifiant=7tTQmnp4Qyu7ZR58#/mobile.parent.html' '1234'
    # get Arguments in right order : Jeton, Login, Url, Pin
    Pronote_url = str(sys.argv[1])
    Username = str(sys.argv[2])
    Password = str(sys.argv[3])
    Ent = str(sys.argv[4])

    """
    Pronote_url = "https://0912109y.index-education.net/pronote/parent.html"
    Username = "antoine.thiebault"
    Password = "BEE1220F3D3B6B89A4C47109C91BD741"
    Ent = "ent_essonne"
    """

    if not Pronote_url.endswith("?login=true"):
        Pronote_url = Pronote_url + "?login=true"

    if "parent.html" in Pronote_url:
        Client = pronotepy.ParentClient(
            pronote_url=Pronote_url, username=Username, password=Password
        )

    else:
        Client = pronotepy.Client(
            pronote_url=Pronote_url, username=Username, password=Password
        )
    print("TEST")
    if Client.logged_in:
        qrcode_data = Client.request_qr_code_data("7530")
        # Étape 1 : Extraire la partie de l'URL jusqu'à `/pronote/`
        ## We need to change url because
        base_url = qrcode_data["url"].split("?login=true")[0]
        # base_url = qrcode_data["url"].split("/pronote/")[0] + "/pronote/"

        # Étape 2 : Extraire la dernière partie de l'URL qui commence par `mobile.`

        last_part = base_url.split("parent.html")[0] + "mobile.parent.html"
        print("url last part", last_part)

        qrcode_data["url"] = last_part
        print(qrcode_data)
        Token_data = Client.qrcode_login(
            qrcode_data,
            "7530",
            uuid="Projote",
        )

        # exit(1)  # the client has failed to log in
        # je nettoie l'URL

        # Génération des données de connexion
        CTS = {
            "Token_URL": Token_data.pronote_url,
            "Token_username": Token_data.username,
            "Token_Password": Token_data.password,
            "Token_UUID": Token_data.uuid,
        }

        # Impression des informations sous forme JSON
        print(json.dumps(CTS))


except Exception as e:
    print(f"An error occurred: {e}")
