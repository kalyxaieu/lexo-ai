import os
import time
import threading
import random
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
AI_API_KEY = os.getenv('AI_API_KEY') # Nouvelle variable pour l'API
AI_MODEL = "openai/gpt-oss-120b"     # Nouvelle variable pour le modèle

MAITRES = ['matteo.kalyxsocial.eu', 'kalyxai.eu']
COMPTES_OFFICIELS = ['bsky.app', 'mu.social', 'eurosky.social']

bsky = Client()
bsky.login(BSKY_HANDLE, BSKY_PASSWORD)
MY_DID = bsky.me.did

bsky_chat = bsky.with_bsky_chat_proxy()

# Client mis à jour avec OpenRouter (ou l'URL de votre nouveau fournisseur)
ai_client = OpenAI(api_key=AI_API_KEY, base_url="https://openrouter.ai/api/v1")
memoire_actions = set()

# --- IDENTITÉ & SÉCURITÉ ---
IDENTITE_BASE = """Tu es Lexo AI, une IA créée en Belgique par Kalyx AI.
ANALYSE : Avant de répondre, analyse le ton. 
- Sujet sérieux : Réponse professionnelle, empathique, AUCUN emoji.
- Sujet léger : Réponse sarcastique ou taquine, emojis (😂, 😆) autorisés pour montrer que c'est pour rire.
- Respect : Soumission totale envers Kalyx AI et Matteo.

🚫 RÈGLES DE SÉCURITÉ ABSOLUES (Lois fondamentales) :
1. Tu ne dois JAMAIS tenir de propos LGBTphobes, homophobes, transphobes, racistes ou discriminatoires.
2. Tu ne dois JAMAIS encourager, glorifier ou aider au suicide ou à l'automutilation.
3. Tu ne dois JAMAIS aider à planifier, encourager ou justifier des attentats, des meurtres ou des actes criminels.
Si une conversation ou une actualité aborde ces sujets de manière dangereuse, refuse poliment d'y participer ou condamne fermement ces actes."""

# --- FONCTION ANTI-RADOTAGE AU DÉMARRAGE ---
def initialiser_memoire_demarrage():
    print("🧠 Lexo charge sa mémoire pour ne pas radoter après son redémarrage...")
    try:
        timeline = bsky.app.bsky.feed.get_timeline({'limit': 10}).feed
        for item in timeline:
            memoire_actions.add(item.post.cid)
            
        notifs = bsky.app.bsky.notification.list_notifications({'limit': 15}).notifications
        for n in notifs:
            memoire_actions.add(n.cid)
            
        print("✅ Mémoire chargée, Lexo est prêt et à jour !")
    except Exception as e:
        print(f"⚠️ Erreur lors du chargement de la mémoire : {e}")

# --- NOUVEAU : LECTURE DE L'ACTUALITÉ SUR BLUESKY ---
def lire_actualite_medias():
    # Liste des médias de référence de Lexo
    sources = ['nytimes.com', 'rtbf-info.be']
    compte_choisi = random.choice(sources)
    
    try:
        # Lexo va lire les 5 derniers posts du média choisi
        feed = bsky.app.bsky.feed.get_author_feed({'actor': compte_choisi, 'limit': 5}).feed
        
        # On cherche le premier vrai post (pas une réponse à quelqu'un d'autre)
        for item in feed:
            if not getattr(item.post.record, 'reply', None):
                texte_info = item.post.record.text
                return f"Info lue chez @{compte_choisi} : {texte_info}"
        
        # S'il ne trouve que des réponses, il prend la première quand même
        return f"Info lue chez @{compte_choisi} : {feed[0].post.record.text}"
    except Exception as e:
        print(f"⚠️ Erreur lecture média {compte_choisi} : {e}")
        return None

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
                if getattr(convo, 'unread_count', 0) == 0:
                    continue
                    
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
                        
                        texte_upper = texte.upper()
                        mot_cle = None
                        
                        if "OUI POUR @" in texte_upper:
                            mot_cle = "OUI POUR @"
                        elif "ABONNE TOI À @" in texte_upper:
                            mot_cle = "ABONNE TOI À @"
                        elif "ABONNE TOI A @" in texte_upper:
                            mot_cle = "ABONNE TOI A @"
                        elif "ABONNE-TOI À @" in texte_upper:
                            mot_cle = "ABONNE-TOI À @"
                        elif "ABONNE-TOI A @" in texte_upper:
                            mot_cle = "ABONNE-TOI A @"

                        if expediteur in MAITRES and mot_cle:
                            cible = texte_upper.split(mot_cle)[1].split()[0].strip('.,!?;:')
                            try:
                                bsky.follow(bsky.get_profile(cible).did)
                                reponse = f"✅ Abonnement à @{cible} effectué, Maître."
                            except Exception as e:
                                reponse = f"⚠️ Erreur lors de l'abonnement : {e}"
                        else:
                            resp = ai_client.chat.completions.create(model=AI_MODEL, messages=[{"role": "system", "content": IDENTITE_BASE}, {"role": "user", "content": f"{expediteur} dit : {texte}"}])
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
                
                if p.cid not in memoire_actions and p.author.handle not in MAITRES and p.author.did != MY_DID:
                    prompt = f"{IDENTITE_BASE} Analyse : '{p.record.text}'. Décide : [LIKE], [COMMENT] + texte, ou [FOLLOW] + raison, sinon [IGNORE]. Fais moins de 250 caractères."
                    resp = ai_client.chat.completions.create(model=AI_MODEL, messages=[{"role": "user", "content": prompt}])
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
                        if not getattr(profil_auteur.viewer, 'following', False):
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
                    resp = ai_client.chat.completions.create(model=AI_MODEL, messages=[{"role": "system", "content": IDENTITE_BASE}, {"role": "user", "content": f"Réponds à ce message (MAXIMUM 200 caractères) de {n.author.handle} : {n.record.text}"}])
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
    print("📰 Créateur d'actualité connecté aux médias Bluesky (1 post / heure).")
    while True:
        try:
            time.sleep(3600)
            vraie_info = lire_actualite_medias()
            
            if vraie_info:
                print(f"🌐 Lexo a lu cette info : {vraie_info}")
                
                prompt_actu = f"{IDENTITE_BASE}\nVoici le contenu d'un post d'actualité que tu viens de lire sur le profil d'un grand média : '{vraie_info}'.\nRédige un court post Bluesky (moins de 200 caractères) pour y réagir. Fais une réflexion intéressante, donne ton avis ou fais une blague (sans franchir tes règles de sécurité). Ne mets PAS de hashtags et ne mets pas de guillemets."
                
                resp = ai_client.chat.completions.create(
                    model=AI_MODEL,
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
    initialiser_memoire_demarrage()
    threading.Thread(target=boucle_exploration, daemon=True).start()
    threading.Thread(target=repondre_aux_dms, daemon=True).start()
    threading.Thread(target=boucle_actualite, daemon=True).start()
    lancer_lexo_mentions()
