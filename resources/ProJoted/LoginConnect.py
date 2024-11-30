try:
    # TO DO :: add log to plugin for troubleshoote
    import pronotepy
    from pronotepy.ent import *
    import sys
    import json

    # type de commande python3 ../../resources/ProJoted/LoginConnect.py 'JETON_RETIRE_4' 'JETON_RETIRE_2' 'https://0000000a.index-education.net/pronote/parent.html?identifiant=EXEMPLE5#/mobile.parent.html' '1234'
    # get Arguments in right order : Jeton, Login, Url, Pin
    Pronote_url = str(sys.argv[1])
    Username = str(sys.argv[2])
    Password = str(sys.argv[3])
    Ent = str(sys.argv[4])


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
