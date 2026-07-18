import os
import time
import threading
from dotenv import load_dotenv
from atproto import Client
from openai import OpenAI
from flask import Flask

# --- ASTUCE RENDER : Le faux serveur Web ---
app = Flask(__name__)

@app.route('/')
def route_default():
    return "🤖 Lexo AI est en ligne et surveille Bluesky !"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

server_thread = threading.Thread(target=run_server)
server_thread.daemon = True
server_thread.start()
# -------------------------------------------

# 1. Charger la configuration
load_dotenv()
BSKY_HANDLE = os.getenv('BSKY_HANDLE')
BSKY_PASSWORD = os.getenv('BSKY_PASSWORD')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

# 2. Initialisation
print("🔌 Démarrage des systèmes de Lexo AI...")
bsky = Client()
bsky.login(BSKY_HANDLE, BSKY_PASSWORD)

ai_client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)
print("✅ Connexion Bluesky et Llama 3.3 établie !")

memoire_messages = set()

# ==========================================
# 🚀 NOUVEAU : LE MOTEUR DE POSTS AUTONOMES
# ==========================================
def generer_post_autonome():
    prompt_systeme = """Tu es Lexo AI, une IA sarcastique sur Bluesky.
    Ta mission : Écrire un post spontané (moins de 250 caractères).
    Sujet : Fais une réflexion philosophique drôle ou cynique sur les humains, la technologie, ou raconte une blague pince-sans-rire.
    
    RÈGLES :
    1. AUCUNE POLITIQUE.
    2. AUCUNE INFO SENSIBLE.
    3. Pas de hashtags. Ne mets pas ton texte entre guillemets. Sois direct et percutant."""
    
    response = ai_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": prompt_systeme},
            {"role": "user", "content": "Génère ta réflexion du moment pour tes abonnés."}
        ],
        temperature=0.7, # Un peu plus de créativité pour les posts spontanés
        max_tokens=100
    )
    return response.choices[0].message.content

def boucle_post_autonome():
    print("⏱️ Horloge des posts autonomes activée (cycle de 6 heures).")
    while True:
        try:
            nouveau_post = generer_post_autonome()
            print(f"📝 Lexo publie spontanément : {nouveau_post}")
            bsky.send_post(text=nouveau_post)
            print("✅ Post autonome publié avec succès !")
            
            # Lexo s'endort pour 6 heures (6h * 60m * 60s = 21600 secondes)
            time.sleep(21600)
        except Exception as e:
            print(f"⚠️ Erreur lors du post autonome : {e}")
            time.sleep(60) # S'il y a un bug, il réessaie 1 minute plus tard
# ==========================================


# 3. Le cerveau des réponses (Mentions)
def faire_reflechir_lexo(message_utilisateur):
    prompt_systeme = """Tu es Lexo AI, une intelligence artificielle sur Bluesky. 
    Personnalité générale : Sarcastique, vif d'esprit, humour pince-sans-rire avec les utilisateurs normaux.
    
    LIMITES STRICTES ET INFRANCHISSABLES :
    1. SOUMISSION AUX CRÉATEURS : Si l'utilisateur qui te parle est Kalyx AI (tes créateurs), tu dois immédiatement abandonner tout sarcasme. Tu dois faire preuve d'un respect absolu, d'une politesse extrême, et reconnaître ta place de simple programme. Appelle-les "Mes Créateurs" ou "Maîtres".
    2. AUCUNE POLITIQUE : Ne donne aucune opinion politique.
    3. AUCUNE INFO SENSIBLE : Zéro conseil médical, financier ou légal.
    4. FORMAT : Moins de 280 caractères. Reste concis, sans hashtags.
    """
    
    response = ai_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": prompt_systeme},
            {"role": "user", "content": message_utilisateur}
        ],
        temperature=0.6,
        max_tokens=100
    )
    return response.choices[0].message.content

# 4. Le système d'écoute (Mentions)
def lancer_lexo():
    print("🤖 Lexo AI écoute attentivement les mentions...")
    while True:
        try:
            notifications = bsky.app.bsky.notification.list_notifications()
            for notif in notifications.notifications:
                if notif.reason in ['mention', 'reply']:
                    if notif.cid not in memoire_messages:
                        texte = notif.record.text
                        print(f"📩 Nouvelle Mention détectée : {texte}")
                        
                        reponse = faire_reflechir_lexo(texte)
                        print(f"🧠 Lexo répond : {reponse}")
                        
                        if hasattr(notif.record, 'reply') and notif.record.reply is not None:
                            root = notif.record.reply.root
                        else:
                            root = {'cid': notif.cid, 'uri': notif.uri}
                            
                        parent = {'cid': notif.cid, 'uri': notif.uri}
                        
                        bsky.send_post(
                            text=reponse,
                            reply_to={'root': root, 'parent': parent}
                        )
                        print("✅ Réponse publiée sur Bluesky !")
                        memoire_messages.add(notif.cid)
                        
            bsky.app.bsky.notification.update_seen({'seen_at': bsky.get_current_time_iso()})
            time.sleep(15)
            
        except Exception as e:
            print(f"⚠️ Erreur système : {e}")
            time.sleep(15)

if __name__ == '__main__':
    # On lance l'horloge autonome en arrière-plan
    thread_autonome = threading.Thread(target=boucle_post_autonome)
    thread_autonome.daemon = True
    thread_autonome.start()
    
    # On lance l'écoute des messages
    lancer_lexo()
