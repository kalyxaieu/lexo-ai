import os
import time
import threading
import random
from datetime import datetime, timezone
from dotenv import load_dotenv
from atproto import Client, models
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
GROQ_API_KEY = os.getenv('GROQ_API_KEY') # Retour à la clé Groq
AI_MODEL = "openai/gpt-oss-120b"         # Votre nouveau modèle

MAITRES = ['matteo.kalyxsocial.eu', 'kalyxai.eu']
COMPTES_OFFICIELS = ['bsky.app', 'mu.social', 'eurosky.social']

bsky = Client()
bsky.login(BSKY_HANDLE, BSKY_PASSWORD)
MY_DID = bsky.me.did

bsky_chat = bsky.with_bsky_chat_proxy()

# Client OpenAI configuré pour les serveurs de Groq
ai_client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
memoire_actions = set()
FENETRE_LECTURE_SECONDES = 21600
MAX_POSTS_LUS_PAR_FENETRE = 5
MAX_LIKES_PAR_FENETRE = 5
dernier_scan = time.time()
likes_dans_fenetre = 0
date_dernier_post = None
verrou_limites = threading.Lock()

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
def nettoyer_anciennes_publications():
    """
    Supprime par lots les posts Lexo présents avant le lancement du nettoyage.
    Les posts publiés après la date de coupure sont conservés, même si Render
    redémarre et perd son stockage temporaire.
    """
    marqueur = os.getenv("LEXO_CLEANUP_MARKER", "/tmp/lexo_old_posts_cleanup.done")
    if os.path.exists(marqueur):
        print("🧹 Nettoyage initial déjà effectué.")
        return True

    # Date de la première exécution de nettoyage observée dans les journaux.
    # Modifiable dans les variables Render si une autre date de coupure est voulue.
    date_coupure = os.getenv("LEXO_CLEANUP_BEFORE", "2026-11-23T23:24:44+00:00")
    date_coupure = datetime.fromisoformat(date_coupure.replace("Z", "+00:00"))

    print(f"🧹 Nettoyage par lots démarré (publications avant {date_coupure.isoformat()}).")
    supprimees = 0
    lots = 0

    def est_limitation_429(erreur):
        statut = getattr(erreur, "status_code", None) or getattr(erreur, "status", None)
        return statut == 429 or "429" in str(erreur) or "Too Many Requests" in str(erreur)

    def appeler_avec_reessais(operation, description):
        attente = 10
        for tentative in range(1, 8):
            try:
                return operation()
            except Exception as erreur:
                if not est_limitation_429(erreur):
                    raise
                if tentative == 7:
                    raise
                reponse = getattr(erreur, "response", None)
                entetes = getattr(reponse, "headers", {}) or {}
                retry_after = entetes.get("Retry-After") or entetes.get("retry-after")
                try:
                    delai = max(1, int(float(retry_after))) if retry_after else attente
                except (TypeError, ValueError):
                    delai = attente
                print(
                    f"⏳ Bluesky limite les requêtes pendant {description}. "
                    f"Nouvel essai dans {delai}s ({tentative}/7)."
                )
                time.sleep(delai)
                attente = min(attente * 2, 180)
        raise RuntimeError("Nombre maximal de tentatives atteint.")

    try:
        curseur = None
        curseurs_vus = set()
        while True:
            params = {"repo": MY_DID, "collection": "app.bsky.feed.post", "limit": 100}
            if curseur:
                params["cursor"] = curseur

            page = appeler_avec_reessais(
                lambda: bsky.com.atproto.repo.list_records(params),
                "lecture des publications"
            )

            # Ne garder que les publications dont la date est antérieure à la coupure.
            operations = []
            for record in page.records:
                valeur = record.value
                cree_le = getattr(valeur, "created_at", None)
                if not cree_le:
                    continue
                try:
                    date_creation = datetime.fromisoformat(cree_le.replace("Z", "+00:00"))
                except (TypeError, ValueError):
                    continue
                if date_creation >= date_coupure:
                    continue

                rkey = record.uri.rsplit("/", 1)[-1]
                operations.append(
                    models.ComAtprotoRepoApplyWrites.Delete(
                        collection="app.bsky.feed.post",
                        rkey=rkey
                    )
                )

            # Un seul appel réseau pour 20 suppressions au lieu de 20 appels.
            for debut in range(0, len(operations), 20):
                lot = operations[debut:debut + 20]
                appeler_avec_reessais(
                    lambda lot=lot: bsky.com.atproto.repo.apply_writes(
                        models.ComAtprotoRepoApplyWrites.Data(
                            repo=MY_DID,
                            writes=lot
                        )
                    ),
                    f"suppression du lot {lots + 1}"
                )
                lots += 1
                supprimees += len(lot)
                print(f"🗑️ {supprimees} publication(s) supprimée(s) ({lots} lots).")
                time.sleep(0.5)

            nouveau_curseur = getattr(page, "cursor", None)
            if not nouveau_curseur:
                break
            if nouveau_curseur == curseur or nouveau_curseur in curseurs_vus:
                raise RuntimeError("Pagination Bluesky bloquée : curseur répété.")
            curseurs_vus.add(nouveau_curseur)
            curseur = nouveau_curseur

        with open(marqueur, "w", encoding="utf-8") as fichier:
            fichier.write("done")
        print(
            f"✅ Nettoyage terminé : {supprimees} publication(s) supprimée(s) "
            f"en {lots} lots. Les publications postérieures à la date de coupure sont conservées."
        )
        return True
    except Exception as erreur:
        print(
            f"⚠️ Nettoyage interrompu après {supprimees} suppression(s) : {erreur}. "
            "Les publications déjà supprimées ne seront plus présentes dans le dépôt ; "
            "le prochain démarrage pourra continuer avec les publications restantes."
        )
        return False


def initialiser_memoire_demarrage():
    print("🧠 Lexo charge sa mémoire pour ne pas radoter après son redémarrage...")
    try:
        timeline = bsky.app.bsky.feed.get_timeline({'limit': 5}).feed
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
                try:
                    if getattr(convo, 'unread_count', 0) == 0:
                        continue

                    msgs = bsky_chat.chat.bsky.convo.get_messages({'convo_id': convo.id, 'limit': 1}).messages
                    if not msgs:
                        continue

                    dernier = msgs[0]
                    sender_did = dernier.sender.did
                    if sender_did == MY_DID:
                        continue

                    msg_id = f"{convo.id}_{dernier.id}"
                    if msg_id in memoire_actions:
                        continue

                    profil_expediteur = bsky.get_profile(sender_did)
                    expediteur = profil_expediteur.handle
                    texte = dernier.text or ""
                    print(f"📩 Nouveau DM de {expediteur}: {texte}")

                    texte_upper = texte.upper()
                    demande_blocage = any(term in texte.lower() for term in (
                        "bloque-moi", "bloque moi", "bloquez-moi", "bloquez moi",
                        "bloque mon compte", "bloquer mon compte",
                        "peux-tu me bloquer", "peux tu me bloquer",
                        "je veux être bloqué", "je souhaite être bloqué",
                        "block me", "please block me", "block my account",
                        "please block my account", "block this account"
                    ))
                    if demande_blocage:
                        try:
                            bsky.app.bsky.graph.block.create_record({
                                'subject': sender_did,
                                'createdAt': bsky.get_current_time_iso()
                            })
                            print(f"Blocage demande par @{expediteur} effectue.")
                        except Exception as block_error:
                            print(f"Impossible de bloquer @{expediteur} : {block_error}")
                        memoire_actions.add(msg_id)
                        try:
                            bsky_chat.chat.bsky.convo.update_read({
                                'convo_id': convo.id, 'message_id': dernier.id
                            })
                        except Exception:
                            pass
                        continue
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
                        resp = ai_client.chat.completions.create(
                            model=AI_MODEL,
                            messages=[
                                {"role": "system", "content": IDENTITE_BASE},
                                {"role": "user", "content": f"{expediteur} dit : {texte}"}
                            ]
                        )
                        reponse = resp.choices[0].message.content or ""

                    reponse = reponse.strip()
                    if not reponse:
                        print(f"⚠️ Réponse vide générée pour {expediteur}; le DM sera retenté.")
                        continue

                    # Bluesky limite le texte d'un DM à 1 000 graphèmes.
                    # 900 points de code constituent une marge de sécurité.
                    if len(reponse) > 900:
                        reponse = reponse[:897].rstrip() + "..."
                        print(f"✂️ Réponse DM raccourcie à 900 caractères pour {expediteur}.")

                    try:
                        bsky_chat.chat.bsky.convo.send_message({
                            'convo_id': convo.id,
                            'message': {'text': reponse}
                        })
                    except Exception as send_error:
                        erreur = str(send_error)
                        if "BlockedActor" in erreur:
                            print(f"🚫 DM ignoré pour {expediteur} : blocage Bluesky entre les comptes.")
                            # Ne pas retenter sans fin un message impossible à envoyer.
                            memoire_actions.add(msg_id)
                            try:
                                bsky_chat.chat.bsky.convo.update_read({
                                    'convo_id': convo.id,
                                    'message_id': dernier.id
                                })
                            except Exception:
                                pass
                        else:
                            print(f"⚠️ Échec d'envoi du DM à {expediteur}; nouvelle tentative au prochain cycle : {send_error}")
                        continue

                    try:
                        bsky_chat.chat.bsky.convo.update_read({
                            'convo_id': convo.id,
                            'message_id': dernier.id
                        })
                    except Exception as read_error:
                        print(f"⚠️ Impossible de marquer le DM de {expediteur} comme lu : {read_error}")

                    memoire_actions.add(msg_id)
                    print(f"✅ Réponse DM envoyée à {expediteur}.")

                except Exception as convo_error:
                    # Une conversation défectueuse ne doit pas interrompre les autres.
                    print(f"⚠️ Erreur sur une conversation DM ({getattr(convo, 'id', 'inconnue')}) : {convo_error}")
                    continue

        except Exception as e:
            print(f"⚠️ Erreur globale boucle DM : {e}")

        time.sleep(20)

def boucle_exploration():
    """Lit au plus cinq posts toutes les six heures, sans commentaire spontané."""
    global dernier_scan, likes_dans_fenetre
    print("Exploration limitee : 5 posts maximum toutes les 6 heures.")
    while True:
        try:
            maintenant = time.time()
            with verrou_limites:
                if dernier_scan and maintenant - dernier_scan < FENETRE_LECTURE_SECONDES:
                    attente = FENETRE_LECTURE_SECONDES - (maintenant - dernier_scan)
                else:
                    dernier_scan = maintenant
                    likes_dans_fenetre = 0
                    attente = 0
            if attente > 0:
                time.sleep(min(attente, 300))
                continue

            timeline = bsky.app.bsky.feed.get_timeline({'limit': MAX_POSTS_LUS_PAR_FENETRE}).feed
            for item in timeline[:MAX_POSTS_LUS_PAR_FENETRE]:
                p = item.post
                if p.cid in memoire_actions or p.author.did == MY_DID or p.author.handle in MAITRES:
                    continue
                with verrou_limites:
                    if likes_dans_fenetre >= MAX_LIKES_PAR_FENETRE:
                        memoire_actions.add(p.cid)
                        continue
                prompt = (
                    f"{IDENTITE_BASE} Analyse ce post : '{p.record.text}'. "
                    "Réponds uniquement [LIKE] ou [IGNORE]. Aucun commentaire, "
                    "aucune réponse spontanée et aucun abonnement."
                )
                resp = ai_client.chat.completions.create(
                    model=AI_MODEL, messages=[{"role": "user", "content": prompt}]
                )
                decision = (resp.choices[0].message.content or "").strip()
                if decision.startswith("[LIKE]"):
                    with verrou_limites:
                        if likes_dans_fenetre < MAX_LIKES_PAR_FENETRE:
                            bsky.like(p.uri, p.cid)
                            likes_dans_fenetre += 1
                            print(f"Like limite sur @{p.author.handle}")
                memoire_actions.add(p.cid)
        except Exception as e:
            print(f"Erreur boucle exploration : {e}")
        time.sleep(FENETRE_LECTURE_SECONDES)


def lancer_lexo_mentions():
    print("Surveillance des mentions et reponses directes activee.")
    while True:
        try:
            notifs = bsky.app.bsky.notification.list_notifications({'limit': 50}).notifications
            for n in notifs:
                if n.reason not in ['mention', 'reply'] or n.cid in memoire_actions:
                    continue
                try:
                    resp = ai_client.chat.completions.create(
                        model=AI_MODEL,
                        messages=[
                            {"role": "system", "content": IDENTITE_BASE},
                            {"role": "user", "content":
                             f"Réponds avec tact et brièvement (200 caractères maximum) à cette "
                             f"mention ou réponse adressée à Lexo par @{n.author.handle} : "
                             f"{getattr(n.record, 'text', '')}"}
                        ]
                    )
                    reponse = (resp.choices[0].message.content or "").strip()
                    if not reponse:
                        memoire_actions.add(n.cid)
                        continue
                    if len(reponse) > 250:
                        reponse = reponse[:247].rstrip() + "..."
                    root = n.record.reply.root if getattr(n.record, 'reply', None) else {'cid': n.cid, 'uri': n.uri}
                    parent = {'cid': n.cid, 'uri': n.uri}
                    bsky.send_post(text=reponse, reply_to={'root': root, 'parent': parent})
                    memoire_actions.add(n.cid)
                    print(f"Reponse envoyee a @{n.author.handle}")
                except Exception as notification_error:
                    print(f"Erreur traitement notification : {notification_error}")
            try:
                bsky.app.bsky.notification.update_seen({'seen_at': bsky.get_current_time_iso()})
            except Exception:
                pass
        except Exception as e:
            print(f"Erreur boucle mentions : {e}")
        time.sleep(30)


def a_deja_publie_aujourdhui():
    """Evite un second post quotidien apres un redemarrage du processus."""
    aujourd_hui = datetime.now(timezone.utc).date()
    try:
        feed = bsky.app.bsky.feed.get_author_feed({'actor': MY_DID, 'limit': 20}).feed
        for item in feed:
            if item.post.author.did != MY_DID:
                continue
            date_creation = getattr(item.post.record, 'created_at', None)
            if not date_creation:
                continue
            date_creation = datetime.fromisoformat(date_creation.replace("Z", "+00:00"))
            if date_creation.astimezone(timezone.utc).date() == aujourd_hui:
                return True
    except Exception as e:
        print(f"Verification du post quotidien impossible : {e}")
        # En cas de doute, ne pas publier : comportement prudent.
        return True
    return False


def boucle_actualite():
    """Publie au maximum un post original par jour."""
    global date_dernier_post
    print("Publication limitee a un post original par jour.")
    while True:
        try:
            aujourd_hui = datetime.now(timezone.utc).date()
            if date_dernier_post == aujourd_hui or a_deja_publie_aujourdhui():
                time.sleep(300)
                continue
            vraie_info = lire_actualite_medias()
            if vraie_info:
                prompt_actu = (
                    f"{IDENTITE_BASE}\nInformation lue : '{vraie_info}'.\n"
                    "Rédige une réaction courte, respectueuse et utile pour Bluesky. "
                    "Moins de 200 caractères, sans hashtags ni guillemets."
                )
                resp = ai_client.chat.completions.create(
                    model=AI_MODEL,
                    messages=[{"role": "user", "content": prompt_actu}],
                    temperature=0.5
                )
                texte_post = (resp.choices[0].message.content or "").strip().strip('"')
                if texte_post:
                    if len(texte_post) > 290:
                        texte_post = texte_post[:287].rstrip() + "..."
                    bsky.send_post(text=texte_post)
                    date_dernier_post = aujourd_hui
                    print(f"Post quotidien publie : {texte_post}")
        except Exception as e:
            print(f"Erreur publication quotidienne : {e}")
        time.sleep(300)


if __name__ == '__main__':
    # Ne pas lancer les autres boucles Bluesky tant que le nettoyage n'est pas terminé :
    # cela évite que DM/mentions/publications aggravent les erreurs 429.
    while not nettoyer_anciennes_publications():
        print("⏳ Nettoyage non terminé : nouvelle tentative dans 60 secondes.")
        time.sleep(60)

    initialiser_memoire_demarrage()
    threading.Thread(target=boucle_exploration, daemon=True).start()
    threading.Thread(target=repondre_aux_dms, daemon=True).start()
    threading.Thread(target=boucle_actualite, daemon=True).start()
    lancer_lexo_mentions()
