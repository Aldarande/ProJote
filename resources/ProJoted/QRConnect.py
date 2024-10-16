try:
    # TO DO :: add log to plugin for troubleshoote
    import pronotepy
    import sys
    import json

    # type de commande python3 ../../resources/ProJoted/QRConnect.py 'JETON_RETIRE_4' 'JETON_RETIRE_2' 'https://0000000a.index-education.net/pronote/parent.html?identifiant=EXEMPLE5#/mobile.parent.html' '1234'
    # get Arguments in right order : Jeton, Login, Url, Pin
    # Jeton = sys.argv[1]
    # Login = sys.argv[2]
    Url = str(sys.argv[3])
    parts = Url.split("?identifiant=")
    base_url = parts[0]

    Qrcode_data = {
        "jeton": str(sys.argv[1]),
        "login": str(sys.argv[2]),
        "url": base_url,
    }
    Pin = str(sys.argv[4])

    # Tentative de connexion via le QR code
    Token_data = pronotepy.Client.qrcode_login(
        Qrcode_data,
        Pin,
        uuid="Projote",
    )

    if Token_data.logged_in:
        print("Client connecté")
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
    line_number = e.__traceback__.tb_lineno
    print("An error occurred: line ", line_number, e, Qrcode_data)
