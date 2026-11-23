"""
Suppression ponctuelle de toutes les publications appartenant au compte Bluesky de Lexo.
Ce script n'est jamais lance automatiquement par bot.py.
Pour l'executer volontairement, definir CONFIRM_DELETE_ALL_OWN_POSTS=YES.
"""
import os
from dotenv import load_dotenv
from atproto import Client

load_dotenv()

if os.getenv("CONFIRM_DELETE_ALL_OWN_POSTS") != "YES":
    raise SystemExit(
        "Suppression annulee. Definissez CONFIRM_DELETE_ALL_OWN_POSTS=YES "
        "uniquement si vous confirmez la suppression de toutes les publications de Lexo."
    )

handle = os.getenv("BSKY_HANDLE")
password = os.getenv("BSKY_PASSWORD")
if not handle or not password:
    raise SystemExit("BSKY_HANDLE et BSKY_PASSWORD sont requis.")

client = Client()
client.login(handle, password)
own_did = client.me.did
cursor = None
deleted = 0
seen = set()

while True:
    params = {"actor": own_did, "limit": 100}
    if cursor:
        params["cursor"] = cursor
    page = client.app.bsky.feed.get_author_feed(params)

    for item in page.feed:
        post = item.post
        # Ne jamais supprimer un post d'un autre compte qui apparait dans le fil.
        if post.author.did != own_did or post.uri in seen:
            continue
        seen.add(post.uri)
        rkey = post.uri.rsplit("/", 1)[-1]
        client.com.atproto.repo.delete_record({
            "repo": own_did,
            "collection": "app.bsky.feed.post",
            "rkey": rkey
        })
        deleted += 1
        print(f"Publication Lexo supprimee ({deleted}).")

    cursor = getattr(page, "cursor", None)
    if not cursor:
        break

print(f"Termine : {deleted} publication(s) appartenant a Lexo supprimee(s).")
