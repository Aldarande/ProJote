try:
    # TO DO :: add log to plugin for troubleshoote
    import pronotepy
    import sys
    import json

    # type de commande python3 ../../resources/ProJoted/QRConnect.py 'E2A24D72F39BA48F2E400CA838E5CCB5F5F6733C64FA762F8FEF473AA7D5BBAD05F641FFE8C6CFE9486564470BB8FCD0F9E4EAE77338B2B45B9A28DB85EC79AE0729E20FF4D0D60D79A7E0CA0380364CB05DC4C1FC3D71E2575423FECF4A0BDD74ADE24A020B222916617B30B189C724' '4C0B20E070291B38E256452F80138CBE' 'https://0912109y.index-education.net/pronote/parent.html?identifiant=7tTQmnp4Qyu7ZR58#/mobile.parent.html' '1234'
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
