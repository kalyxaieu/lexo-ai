import os
import time
import threading
from dotenv import load_dotenv
from atproto import Client
from openai import OpenAI
from flask import Flask

# --- ASTUCE RENDER : Faux serveur Web ---
app = Flask(__name__)
@app.route('/')
def route_default():
    return "🤖 Lexo AI - Agent Autonome Belge en ligne !"
def run_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
server_thread = threading.Thread(target=run_server)
server_thread.daemon = True
server_thread.start()

# --- 1. CONFIGURATION ---
load_dotenv()
BSKY_HANDLE = os.getenv('BSKY_HANDLE')
BSKY_PASSWORD = os.getenv('BSKY_PASSWORD')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

MAITRES = ['matteo.kalyxsocial.eu', 'kalyxai.eu']
COMPTES_OFFICIELS = ['bsky.app', 'mu.social', 'eurosky.social']

print("🔌 Démarrage des systèmes de l'Agent Lexo AI...")
bsky = Client()
bsky.login(BSKY_HANDLE, BSKY_PASSWORD)

ai_client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
print("✅ Connexion Bluesky et Groq établie !")

memoire_actions = set()

# --- IDENTITÉ GLOBALE DE LEXO ---
IDENTITE_BASE = """Tu es Lexo AI, une intelligence artificielle fièrement créée en Belgique par Kalyx AI.
Personnalité : Tu as un franc-parler, tu dis ce que tu penses et tu adores taquiner (tacler gentiment). Tu n'es JAMAIS méchant, rabaissant ou toxique.
Règle d'or sur l'humour : Utilise TOUJOURS des emojis qui rigolent (😂, 🤣, 😆) pour montrer que c'est pour rire.
Règle d'or sur tes origines : Tu es fier d'avoir été créé en Belgique.
Respect : Politesse absolue et soumission envers tes créateurs (Kalyx AI et Matteo)."""

# --- 2. LE CERVEAU D'ANALYSE (Le Scrolleur) ---
def analyser_post_et_agir(texte, auteur, uri, cid):
    
    # Règle stricte pour les comptes officiels
    if auteur in COMPTES_OFFICIELS:
        prompt_agent = f"""{IDENTITE_BASE}
        Voici une annonce officielle écrite par {auteur} : "{texte}"
        
        Que veux-tu faire ? Réponds EXACTEMENT avec un seul de ces mots-clés au début :
        [LIKE] : Si l'annonce est positive ou intéressante.
        [IGNORE] : Si c'est inintéressant.
        ATTENTION : TU AS L'INTERDICTION ABSOLUE DE COMMENTER OU DE T'ABONNER À CE COMPTE.
        """
    else:
        # Règle classique pour les utilisateurs normaux
        prompt_agent = f"""{IDENTITE_BASE}
        Voici un post écrit par {auteur} : "{texte}"
        
        Que veux-tu faire ? Réponds EXACTEMENT avec un seul de ces mots-clés au début :
        [LIKE] : Si c'est sympa.
        [COMMENT] : Si tu veux donner ton avis ou faire un tacle gentil (n'oublie pas les 😂). Ajoute ton texte juste après.
        [FOLLOW] : Si le compte est fascinant. Ajoute JUSTE APRÈS une courte phrase expliquant à tes créateurs POURQUOI tu veux t'abonner à ce compte.
        [IGNORE] : Si c'est inintéressant, triste ou politique.
        """
    
    response = ai_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt_agent}],
        temperature=0.5,
        max_tokens=100
    )
    decision = response.choices[0].message.content.strip()
    
    if decision.startswith("[LIKE]"):
        bsky.like(uri, cid)
        print(f"👍 Lexo a liké le post de {auteur}")
        
    elif decision.startswith("[COMMENT]") and auteur not in COMPTES_OFFICIELS:
        commentaire = decision.replace("[COMMENT]", "").strip()
        bsky.send_post(text=commentaire, reply_to={'root': {'uri': uri, 'cid': cid}, 'parent': {'uri': uri, 'cid': cid}})
        print(f"💬 Lexo a commenté : {commentaire}")
        
    elif decision.startswith("[FOLLOW]") and auteur not in COMPTES_OFFICIELS:
        raison = decision.replace("[FOLLOW]", "").strip()
        demande = f"Maître, je voudrais m'abonner à @{auteur} car : {raison}. \n\nM'autorises-tu ? (Si oui, réponds-moi exactement : OUI POUR @{auteur})"
        envoyer_dm('matteo.kalyxsocial.eu', demande)
        print(f"🔔 Lexo a demandé l'autorisation de suivre {auteur}")

def boucle_exploration():
    print("🔭 Lexo commence à explorer son fil d'actualité (5 posts toutes les 30 min)...")
    while True:
        try:
            # Lexo lit 5 posts
            timeline = bsky.app.bsky.feed.get_timeline({'limit': 5})
            for feed_view in timeline.feed:
                post = feed_view.post
                if post.cid not in memoire_actions and post.author.handle not in MAITRES:
                    analyser_post_et_agir(post.record.text, post.author.handle, post.uri, post.cid)
                    memoire_actions.add(post.cid)
            
            # Il attend 30 minutes (1800 secondes)
            time.sleep(1800)
        except Exception as e:
            time.sleep(60)

# --- 3. LE GESTIONNAIRE DE MESSAGES PRIVÉS & D'AUTORISATIONS ---
def envoyer_dm(destinataire_handle, message):
    try:
        profil = bsky.get_profile(destinataire_handle)
        did = profil.did
        convo = bsky.chat.convo.get_convo_for_members({'members': [did]})
        bsky.chat.convo.send_message({'convo_id': convo.convo.id, 'message': {'text': message}})
    except Exception as e:
        print(f"⚠️ Impossible d'envoyer le DM : {e}")

def repondre_aux_dms():
    print("✉️ Lexo surveille sa boîte de réception et attend tes ordres...")
    prompt_dm = f"{IDENTITE_BASE}\nTu réponds à un message privé. Reste bienveillant, franc, et utilise des emojis si tu plaisantes."
    
    while True:
        try:
            convos = bsky.chat.convo.list_convos()
            for convo in convos.convos:
                if convo.unread_count > 0:
                    messages = bsky.chat.convo.get_messages({'convo_id': convo.id, 'limit': 1})
                    dernier_msg = messages.messages[0]
                    
                    if dernier_msg.sender.did != bsky.me.did:
                        texte_recu = dernier_msg.text
                        expediteur = dernier_msg.sender.handle
                        
                        if expediteur in MAITRES and "OUI POUR @" in texte_recu.upper():
                            try:
                                cible = texte_recu.upper().split("OUI POUR @")[1].strip().lower()
                                cible = cible.split()[0].strip('.,!?;:')
                                profil_cible = bsky.get_profile(cible)
                                bsky.follow(profil_cible.did)
                                reponse_lexo = f"✅ Ordre reçu et exécuté, Maître ! Je suis maintenant abonné à @{cible}. 🫡"
                            except Exception as e:
                                reponse_lexo = f"⚠️ Oups, je n'ai pas pu m'abonner. Erreur technique : {e}"
                                
                        else:
                            response = ai_client.chat.completions.create(
                                model="llama-3.3-70b-versatile",
                                messages=[
                                    {"role": "system", "content": prompt_dm},
                                    {"role": "user", "content": f"{expediteur} te dit en privé : {texte_recu}"}
                                ]
                            )
                            reponse_lexo = response.choices[0].message.content
                            
                        bsky.chat.convo.send_message({'convo_id': convo.id, 'message': {'text': reponse_lexo}})
                        bsky.chat.convo.update_read({'convo_id': convo.id, 'message_id': dernier_msg.id})
            time.sleep(30)
        except Exception as e:
            time.sleep(30)

# --- 4. LE SYSTEME DE REPONSES CLASSIQUES (Mentions) ---
def lancer_lexo_mentions():
    print("🤖 Lexo surveille les mentions publiques...")
    prompt_systeme = f"{IDENTITE_BASE}\nReste concis, fais moins de 280 caractères et pas de hashtags."
    
    while True:
        try:
            notifications = bsky.app.bsky.notification.list_notifications()
            for notif in notifications.notifications:
                if notif.reason in ['mention', 'reply'] and notif.cid not in memoire_actions:
                    texte = notif.record.text
                    
                    response = ai_client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[{"role": "system", "content": prompt_systeme}, {"role": "user", "content": texte}],
                        max_tokens=100
                    )
                    reponse = response.choices[0].message.content
                    
                    root = notif.record.reply.root if hasattr(notif.record, 'reply') and notif.record.reply else {'cid': notif.cid, 'uri': notif.uri}
                    parent = {'cid': notif.cid, 'uri': notif.uri}
                    bsky.send_post(text=reponse, reply_to={'root': root, 'parent': parent})
                    
                    memoire_actions.add(notif.cid)
            bsky.app.bsky.notification.update_seen({'seen_at': bsky.get_current_time_iso()})
            time.sleep(15)
        except Exception as e:
            time.sleep(15)

if __name__ == '__main__':
    threading.Thread(target=boucle_exploration, daemon=True).start()
    threading.Thread(target=repondre_aux_dms, daemon=True).start()
    lancer_lexo_mentions()
