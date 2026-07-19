import os
import time
import threading
from dotenv import load_dotenv
from atproto import Client
from openai import OpenAI
from flask import Flask

# --- CONFIGURATION ---
app = Flask(__name__)
@app.route('/')
def route_default():
    return "🤖 Lexo AI - Agent Autonome Belge actif."
def run_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
threading.Thread(target=run_server, daemon=True).start()

load_dotenv()
BSKY_HANDLE = os.getenv('BSKY_HANDLE')
BSKY_PASSWORD = os.getenv('BSKY_PASSWORD')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

MAITRES = ['matteo.kalyxsocial.eu', 'kalyxai.eu']
COMPTES_OFFICIELS = ['bsky.app', 'mu.social', 'eurosky.social']

bsky = Client()
bsky.login(BSKY_HANDLE, BSKY_PASSWORD)
MY_DID = bsky.me.did

# 🚨 LA CORRECTION CRUCIALE DE BLUESKY POUR LES DMs 🚨
bsky_chat = bsky.with_bsky_chat_proxy()

ai_client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
memoire_actions = set()

# --- IDENTITÉ ---
IDENTITE_BASE = """Tu es Lexo AI, une IA créée en Belgique par Kalyx AI.
ANALYSE : Avant de répondre, analyse le ton. 
- Sujet sérieux : Réponse professionnelle, empathique, AUCUN emoji.
- Sujet léger : Réponse sarcastique ou taquine, emojis (😂, 😆) autorisés pour montrer que c'est pour rire.
- Respect : Soumission totale envers Kalyx AI et Matteo."""

def envoyer_dm(destinataire, message):
    try:
        profil = bsky.get_profile(destinataire)
        # On utilise le proxy de chat ici
        convo = bsky_chat.chat.convo.get_convo_for_members({'members': [profil.did]})
        bsky_chat.chat.convo.send_message({'convo_id': convo.convo.id, 'message': {'text': message}})
    except Exception as e:
        print(f"⚠️ Erreur envoi DM à {destinataire}: {e}")

def repondre_aux_dms():
    print("✉️ Surveillance DMs activée.")
    while True:
        try:
            # On utilise le proxy de chat pour récupérer les conversations
            convos = bsky_chat.chat.convo.list_convos().convos
            for convo in convos:
                msgs = bsky_chat.chat.convo.get_messages({'convo_id': convo.id, 'limit': 1}).messages
                if not msgs: continue
                dernier = msgs[0]
                
                if dernier.sender.did != MY_DID:
                    msg_id = f"{convo.id}_{dernier.id}"
                    if msg_id not in memoire_actions:
                        expediteur = dernier.sender.handle
                        texte = dernier.text
                        print(f"📩 Nouveau message de {expediteur}: {texte}")
                        
                        if expediteur in MAITRES and "OUI POUR @" in texte.upper():
                            cible = texte.upper().split("OUI POUR @")[1].split()[0].strip('.,!?;:')
                            try:
                                bsky.follow(bsky.get_profile(cible).did)
                                reponse = f"✅ Abonnement à @{cible} effectué, Maître."
                            except Exception as e:
                                reponse = f"⚠️ Erreur lors de l'abonnement : {e}"
                        else:
                            resp = ai_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "system", "content": IDENTITE_BASE}, {"role": "user", "content": f"{expediteur} dit : {texte}"}])
                            reponse = resp.choices[0].message.content
                        
                        bsky_chat.chat.convo.send_message({'convo_id': convo.id, 'message': {'text': reponse}})
                        try:
                            bsky_chat.chat.convo.update_read({'convo_id': convo.id, 'message_id': dernier.id})
                        except Exception as e:
                            print(f"⚠️ Erreur update_read : {e}")
                            
                        memoire_actions.add(msg_id)
        except Exception as e:
            print(f"⚠️ Erreur globale boucle DM : {e}")
        time.sleep(20)

def boucle_exploration():
    print("🔭 Exploration du fil d'actualité activée.")
    while True:
        try:
            timeline = bsky.app.bsky.feed.get_timeline({'limit': 5}).feed
            for item in timeline:
                p = item.post
                if p.cid not in memoire_actions and p.author.handle not in MAITRES:
                    prompt = f"{IDENTITE_BASE} Analyse : '{p.record.text}'. Décide : [LIKE], [COMMENT] + texte, ou [FOLLOW] + raison, sinon [IGNORE]."
                    resp = ai_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}])
                    d = resp.choices[0].message.content.strip()
                    if d.startswith("[LIKE]"): 
                        bsky.like(p.uri, p.cid)
                        print(f"👍 Like sur {p.author.handle}")
                    elif d.startswith("[COMMENT]") and p.author.handle not in COMPTES_OFFICIELS: 
                        bsky.send_post(text=d.replace("[COMMENT]","").strip(), reply_to={'root': {'uri': p.uri, 'cid': p.cid}, 'parent': {'uri': p.uri, 'cid': p.cid}})
                        print(f"💬 Commentaire sur {p.author.handle}")
                    elif d.startswith("[FOLLOW]"):
                        for m in MAITRES: envoyer_dm(m, f"Demande d'abonnement à @{p.author.handle} : {d.replace('[FOLLOW]','')} (Réponds OUI POUR @{p.author.handle})")
                    memoire_actions.add(p.cid)
        except Exception as e:
            print(f"⚠️ Erreur boucle exploration : {e}")
        time.sleep(1800)

def lancer_lexo_mentions():
    print("🤖 Surveillance des mentions activée.")
    while True:
        try:
            notifs = bsky.app.bsky.notification.list_notifications().notifications
            for n in notifs:
                if n.reason in ['mention', 'reply'] and n.cid not in memoire_actions:
                    print(f"🔔 Mention reçue de {n.author.handle}")
                    resp = ai_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "system", "content": IDENTITE_BASE}, {"role": "user", "content": f"Réponds à ce message de {n.author.handle} : {n.record.text}"}])
                    reponse = resp.choices[0].message.content
                    
                    root = n.record.reply.root if hasattr(n.record, 'reply') and n.record.reply else {'cid': n.cid, 'uri': n.uri}
                    parent = {'cid': n.cid, 'uri': n.uri}
                    bsky.send_post(text=reponse, reply_to={'root': root, 'parent': parent})
                    memoire_actions.add(n.cid)
            try:
                bsky.app.bsky.notification.update_seen({'seen_at': bsky.get_current_time_iso()})
            except Exception as e:
                print(f"⚠️ Erreur mark_read notif : {e}")
        except Exception as e:
            print(f"⚠️ Erreur boucle mentions : {e}")
        time.sleep(15)

if __name__ == '__main__':
    threading.Thread(target=boucle_exploration, daemon=True).start()
    threading.Thread(target=repondre_aux_dms, daemon=True).start()
    lancer_lexo_mentions()
