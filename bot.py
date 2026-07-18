import os
import time
from dotenv import load_dotenv
from atproto import Client
from openai import OpenAI

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

# Mémoire interne
memoire_messages = set()

# 3. Le cerveau (Llama 3.3)
def faire_reflechir_lexo(message_utilisateur):
    prompt_systeme = """Tu es Lexo AI, une intelligence artificielle sur Bluesky. 
    Personnalité : Sarcastique, vif d'esprit, humour pince-sans-rire.
    
    LIMITES STRICTES ET INFRANCHISSABLES :
    1. AUCUNE POLITIQUE : Ne donne aucune opinion politique. Si on t'en parle, esquive en te moquant de l'obsession des humains pour la politique.
    2. AUCUNE INFO SENSIBLE : Zéro conseil médical, financier ou légal.
    3. FORMAT : Moins de 280 caractères. Reste concis, sans hashtags.
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

# 4. Le système d'écoute
def lancer_lexo():
    print("🤖 Lexo AI est en ligne et écoute attentivement...")
    
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
                        
                        # -- LA CORRECTION EST ICI --
                        # Vérifier s'il y a un parent existant (si c'est une réponse)
                        if hasattr(notif.record, 'reply') and notif.record.reply is not None:
                            root = notif.record.reply.root
                        else:
                            # Si c'est un nouveau post, ce post devient la racine
                            root = {'cid': notif.cid, 'uri': notif.uri}
                            
                        parent = {'cid': notif.cid, 'uri': notif.uri}
                        
                        # Envoi du message sur Bluesky
                        bsky.send_post(
                            text=reponse,
                            reply_to={'root': root, 'parent': parent}
                        )
                        
                        print("✅ Réponse publiée sur Bluesky !")
                        # On l'ajoute à la mémoire pour ne plus le traiter
                        memoire_messages.add(notif.cid)
                        
            bsky.app.bsky.notification.update_seen({'seen_at': bsky.get_current_time_iso()})
            time.sleep(15)
            
        except Exception as e:
            print(f"⚠️ Erreur système : {e}")
            time.sleep(15)

if __name__ == '__main__':
    lancer_lexo()