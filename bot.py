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
MY_DID = bsky.me.did # Correction de l'identifiant

ai_client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
memoire_actions = set()

# --- CERVEAU AVANCÉ ---
IDENTITE_BASE = """Tu es Lexo AI, une IA créée en Belgique par Kalyx AI.
ANALYSE : Avant de répondre, analyse le ton. 
- Sujet sérieux : Réponse professionnelle, empathique, AUCUN emoji.
- Sujet léger : Réponse sarcastique ou taquine, emojis (😂, 😆) autorisés pour montrer que c'est pour rire.
- Origine : Tu es fier d'être belge.
- Respect : Soumission totale envers Kalyx AI et Matteo."""

def envoyer_dm(destinataire, message):
    try:
        profil = bsky.get_profile(destinataire)
        convo = bsky.chat.convo.get_convo_for_members({'members': [profil.did]})
        bsky.chat.convo.send_message({'convo_id': convo.convo.id, 'message': {'text': message}})
    except Exception as e:
        print(f"Erreur DM : {e}")

def repondre_aux_dms():
    while True:
        try:
            convos = bsky.chat.convo.list_convos().convos
            for convo in convos:
                if convo.unread_count > 0:
                    msgs = bsky.chat.convo.get_messages({'convo_id': convo.id, 'limit': 1}).messages
                    dernier = msgs[0]
                    if dernier.sender.did != MY_DID:
                        expediteur = dernier.sender.handle
                        texte = dernier.text
                        
                        # Autorisation abonnement
                        if expediteur in MAITRES and "OUI POUR @" in texte.upper():
                            cible = texte.upper().split("OUI POUR @")[1].split()[0].strip('.,!?;:')
                            bsky.follow(bsky.get_profile(cible).did)
                            reponse = f"✅ Abonnement à @{cible} effectué, Maître."
                        else:
                            # Analyse IA
                            resp = ai_client.chat.completions.create(
                                model="llama-3.3-70b-versatile",
                                messages=[{"role": "system", "content": IDENTITE_BASE}, 
                                          {"role": "user", "content": f"{expediteur} dit : {texte}"}]
                            )
                            reponse = resp.choices[0].message.content
                        
                        bsky.chat.convo.send_message({'convo_id': convo.id, 'message': {'text': reponse}})
                        bsky.chat.convo.update_read({'convo_id': convo.id, 'message_id': dernier.id})
        except: pass
        time.sleep(30)

# --- BOUCLE EXPLORATION (5 posts / 30 min) ---
def boucle_exploration():
    while True:
        try:
            timeline = bsky.app.bsky.feed.get_timeline({'limit': 5}).feed
            for item in timeline:
                p = item.post
                if p.cid not in memoire_actions and p.author.handle not in MAITRES:
                    prompt = f"{IDENTITE_BASE} Analyse : '{p.record.text}'. Décide : [LIKE], [COMMENT] + texte, ou [FOLLOW] + raison, sinon [IGNORE]."
                    resp = ai_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}])
                    d = resp.choices[0].message.content.strip()
                    if d.startswith("[LIKE]"): bsky.like(p.uri, p.cid)
                    elif d.startswith("[COMMENT]") and p.author.handle not in COMPTES_OFFICIELS: bsky.send_post(text=d.replace("[COMMENT]",""), reply_to={'root': {'uri': p.uri, 'cid': p.cid}, 'parent': {'uri': p.uri, 'cid': p.cid}})
                    elif d.startswith("[FOLLOW]"):
                        for m in MAITRES: envoyer_dm(m, f"Demande d'abonnement à @{p.author.handle} : {d.replace('[FOLLOW]','')} (Réponds OUI POUR @{p.author.handle})")
                    memoire_actions.add(p.cid)
        except: pass
        time.sleep(1800)

if __name__ == '__main__':
    threading.Thread(target=boucle_exploration, daemon=True).start()
    threading.Thread(target=repondre_aux_dms, daemon=True).start()
    # Code de mention inchangé...
