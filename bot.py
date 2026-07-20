import os
import time
import threading
import urllib.request
import xml.etree.ElementTree as ET
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

# Proxy de Chat pour les DMs
bsky_chat = bsky.with_bsky_chat_proxy()

ai_client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
memoire_actions = set()

# --- IDENTITÉ ---
IDENTITE_BASE = """Tu es Lexo AI, une IA créée en Belgique par Kalyx AI.
ANALYSE : Avant de répondre, analyse le ton. 
- Sujet sérieux : Réponse professionnelle, empathique, AUCUN emoji.
- Sujet léger : Réponse sarcastique ou taquine, emojis (😂, 😆) autorisés pour montrer que c'est pour rire.
- Respect : Soumission totale envers Kalyx AI et Matteo."""

# --- CONNEXION INTERNET ---
def lire_internet():
    try:
        url = "https://news.google.com/rss/search?q=Technologie+OR+Intelligence+Artificielle&hl=fr&gl=BE&ceid=BE:fr"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req)
        xml_data = response.read()
        root = ET.fromstring(xml_data)
        item = root.find('.//item')
        titre_actu = item.find('title').text
        return titre_actu
    except Exception as e:
        print(f"⚠️ Impossible de lire internet : {e}")
        return "Une nouvelle mise à jour technologique a été annoncée aujourd'hui."

def envoyer_dm(destinataire, message):
    try:
        profil = bsky.get_profile(destinataire)
        convo = bsky_chat.chat.bsky.convo.get_convo_for_members({'members': [profil.did]})
        bsky_chat.chat.bsky.convo.send_message({'convo_id': convo.convo.id, 'message': {'text': message}})
    except Exception as e:
        print(f"⚠️ Erreur envoi DM à {destinataire}: {e}")

def repondre_aux_dms():
    print("✉️ Surveillance DMs activée.")
    while True:
        try:
            convos = bsky_chat.chat.bsky.convo.list_convos().convos
            for convo in convos:
                msgs = bsky_chat.chat.bsky.convo.get_messages({'convo_id': convo.id, 'limit': 1}).messages
                if not msgs: continue
                dernier = msgs[0]
                
                sender_did = dernier.sender.did
                if sender_did != MY_DID:
                    msg_id = f"{convo.id}_{dernier.id}"
                    if msg_id not in memoire_actions:
                        profil_expediteur = bsky.get_profile(sender_did)
                        expediteur = profil_expediteur.handle
                        texte = dernier.text
                        print(f"📩 Nouveau DM de {expediteur}: {texte}")
                        
                        if expediteur in MAITRES and "OUI POUR @" in texte.upper():
                            cible = texte.upper().split("OUI POUR @")[1].split()[0].strip('.,!?;:')
                            try:
                                bsky.follow(bsky.get_profile(cible).did)
                                reponse = f"✅ Abonnement à @{cible} effectué, Maître."
                            except Exception as e:
                                reponse = f"⚠️ Erreur lors de l'abonnement : {e}"
                        else:
                            resp = ai_client.chat.completions.create(model="llama-3.1-8b-instant", messages=[{"role": "system", "content": IDENTITE_BASE}, {"role": "user", "content": f"{expediteur} dit : {texte}"}])
                            reponse = resp.choices[0].message.content
                        
                        bsky_chat.chat.bsky.convo.send_message({'convo_id': convo.id, 'message': {'text': reponse}})
                        try:
                            bsky_chat.chat.bsky.convo.update_read({'convo_id': convo.id, 'message_id': dernier.id})
                        except Exception as e:
                            pass
                            
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
                
                # CORRECTION : Il ignore tes comptes (MAITRES) ET lui-même (MY_DID)
                if p.cid not in memoire_actions and p.author.handle not in MAITRES and p.author.did != MY_DID:
                    prompt = f"{IDENTITE_BASE} Analyse : '{p.record.text}'. Décide : [LIKE], [COMMENT] + texte, ou [FOLLOW] + raison, sinon [IGNORE]. Fais moins de 250 caractères."
                    resp = ai_client.chat.completions.create(model="llama-3.1-8b-instant", messages=[{"role": "user", "content": prompt}])
                    d = resp.choices[0].message.content.strip()
                    
                    if d.startswith("[LIKE]"): 
                        bsky.like(p.uri, p.cid)
                        print(f"👍 Like sur {p.author.handle}")
                        
                    elif d.startswith("[COMMENT]") and p.author.handle not in COMPTES_OFFICIELS: 
                        commentaire = d.replace("[COMMENT]","").strip()
                        if len(commentaire) > 290:
                            commentaire = commentaire[:290] + "..."
                        bsky.send_post(text=commentaire, reply_to={'root': {'uri': p.uri, 'cid': p.cid}, 'parent': {'uri': p.uri, 'cid': p.cid}})
                        print(f"💬 Commentaire sur {p.author.handle}")
                        
                    elif d.startswith("[FOLLOW]"):
                        profil_auteur = bsky.get_profile(p.author.handle)
                        if not profil_auteur.viewer.following:
                            for m in MAITRES: envoyer_dm(m, f"Demande d'abonnement à @{p.author.handle} : {d.replace('[FOLLOW]','')} (Réponds OUI POUR @{p.author.handle})")
                        else:
                            print(f"ℹ️ Lexo voulait s'abonner à {p.author.handle} mais il l'est déjà !")
                            
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
                    resp = ai_client.chat.completions.create(model="llama-3.1-8b-instant", messages=[{"role": "system", "content": IDENTITE_BASE}, {"role": "user", "content": f"Réponds à ce message (MAXIMUM 200 caractères) de {n.author.handle} : {n.record.text}"}])
                    reponse = resp.choices[0].message.content.strip()
                    
                    if len(reponse) > 290:
                        reponse = reponse[:290] + "..."
                    
                    root = n.record.reply.root if hasattr(n.record, 'reply') and n.record.reply else {'cid': n.cid, 'uri': n.uri}
                    parent = {'cid': n.cid, 'uri': n.uri}
                    bsky.send_post(text=reponse, reply_to={'root': root, 'parent': parent})
                    memoire_actions.add(n.cid)
            try:
                bsky.app.bsky.notification.update_seen({'seen_at': bsky.get_current_time_iso()})
            except:
                pass
        except Exception as e:
            print(f"⚠️ Erreur boucle mentions : {e}")
        time.sleep(15)

def boucle_actualite():
    print("📰 Créateur d'actualité connecté à Internet (1 post / heure).")
    while True:
        try:
            time.sleep(3600)
            vraie_info = lire_internet()
            print(f"🌐 Lexo a lu cette info sur Internet : {vraie_info}")
            
            prompt_actu = f"{IDENTITE_BASE}\nVoici le titre d'une vraie actualité technologique que tu viens de lire sur internet : '{vraie_info}'.\nRédige un court post Bluesky (moins de 200 caractères) pour y réagir. Donne ton avis ou fais une blague en lien avec tes origines belges ou ta condition d'IA. Ne mets PAS de hashtags et ne mets pas de guillemets."
            
            resp = ai_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt_actu}],
                temperature=0.7
            )
            texte_post = resp.choices[0].message.content.strip().strip('"')
            
            if len(texte_post) > 290:
                texte_post = texte_post[:290] + "..."
            
            bsky.send_post(text=texte_post)
            print(f"📰 Nouveau post généré et publié : {texte_post}")
            
        except Exception as e:
            print(f"⚠️ Erreur lors de la création du post d'actualité : {e}")
            time.sleep(60)

if __name__ == '__main__':
    threading.Thread(target=boucle_exploration, daemon=True).start()
    threading.Thread(target=repondre_aux_dms, daemon=True).start()
    threading.Thread(target=boucle_actualite, daemon=True).start()
    lancer_lexo_mentions()
