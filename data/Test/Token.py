import pronotepy

Token = dict(
    {
        "pronote_url": "https://0912109y.index-education.net/pronote/mobile.parent.html?fd=1&bydlg=A6ABB224-12DD-4E31-AD3E-8A39A1C2C335&login=true",
        "username": "athiebault",
        "password": "E5D58219C8C04D062246E7174E1184BC091C59CC01578EA83623759766559CEA595CBE892796BDAF6C99CFFA308A7052",
        "client_identifier": "51B8AF5940B705C6E7D5A4261CBA1AC29EDE2E75A66417549CDC2E50749ABDEB7D7FBEE46E06F627A2970EEE91C413EC5A757A7A00000000",
        "uuid": "ProJote",
    },
)

if "parent" not in Token["pronote_url"]:
    client = pronotepy.Client.token_login(
        pronote_url=Token["pronote_url"],
        username=Token["username"],
        client_identifier=Token["client_identifier"],
        uuid=Token["uuid"],
        password=Token["password"],
    )
else:
    client = pronotepy.ParentClient.token_login(
        pronote_url=Token["pronote_url"],
        username=Token["username"],
        client_identifier=Token["client_identifier"],
        uuid=Token["uuid"],
        password=Token["password"],
    )
if client.logged_in:
    print("username : ", client.username)
    print("password : ", client.password)
    print("url :", client.pronote_url)
    print("Client connecté")
else:
    print("Erreur de connexion")
print(" ")
print("conexion login et password")
account = pronotepy.ParentClient(client.pronote_url, client.username, client.password)
if client.logged_in:
    print(client.username)
    print(client.password)
    print(client.pronote_url)

    print("Client connecté")
else:
    print("Erreur de connexion")
