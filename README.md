# FAMIVERSE

Application familiale bilingue (français/arabe), conçue pour être testée depuis
GitHub puis installée sur un serveur familial compatible Docker, notamment un
Raspberry Pi 5. Le serveur reste accessible sur le réseau local ; aucune
publication sur Internet n'est configurée.

## Prérequis

- Git
- Docker avec Docker Compose v2
- Pour une installation ultérieure sur Raspberry Pi : système 64 bits et
  Docker Compose. La compatibilité du matériel et de la mémoire sera vérifiée
  avant la mise en service.

## Application installable (PWA)

L'interface fournit un manifeste d'installation et un service worker. Hors
connexion, celui-ci peut afficher une page bilingue et garder en cache les
ressources statiques (style et icônes) uniquement ; les pages de connexion,
profils et autres données ne sont jamais mises en cache.

L'installation PWA exige un contexte sécurisé : HTTPS avec un certificat
reconnu sur les autres appareils, ou `localhost` sur l'ordinateur qui exécute
le navigateur. Le HTTP local fourni par Compose sert aux essais, mais une
adresse en `http://<IP_DU_SERVEUR>:8088` ne permet pas l'installation PWA sur
un téléphone. Compose ne configure pas encore de terminaison HTTPS. Les
options `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_SESSION_COOKIE_SECURE` et
`DJANGO_CSRF_COOKIE_SECURE` restent désactivées dans `.env.example` pour ne
pas bloquer ce mode HTTP ; ne les activez qu'après avoir configuré et testé
une terminaison HTTPS de confiance. Derrière un proxy TLS qui remplace
systématiquement `X-Forwarded-Proto` et empêche l'accès direct au port de
l'application, définissez aussi `DJANGO_TRUST_X_FORWARDED_PROTO=True`.
N'activez HSTS qu'une fois HTTPS confirmé et stable.

## Démarrage depuis GitHub

1. Cloner le dépôt indiqué par la personne qui le partage :

   ```sh
   git clone https://github.com/tarilux/FAMIVERSE.git famiverse
   cd famiverse
   ```

2. Créer le fichier local de configuration :

   ```sh
   cp .env.example .env
   ```

   Sous Windows PowerShell, utiliser `Copy-Item .env.example .env`.

3. Ouvrir `.env` et remplacer les valeurs `replace-with-...` par des secrets
   uniques. Pour générer une clé Django ou un mot de passe PostgreSQL avec Python :

   ```sh
   python -c "import secrets; print(secrets.token_urlsafe(50))"
   ```

   Pour accéder depuis d'autres appareils, ajoutez l'adresse locale de l'hôte
   dans `DJANGO_ALLOWED_HOSTS`, séparée par des virgules. Ne partagez pas le
   fichier `.env` et ne le versez pas dans GitHub.

   `BACKUP_HOST_PATH` définit le dossier hôte des archives. Pour une
   installation sur Pi, remplacez `./backups` par le chemin d'un disque externe
   ou d'un partage réseau déjà monté, par exemple `/mnt/famiverse-backups`.
   Créez le dossier, puis, après la construction de l'image, accordez l'accès
   au compte applicatif :

   ```sh
   sudo mkdir -p /mnt/famiverse-backups
   docker compose build web
   docker compose run --rm --no-deps --user root web chown -R app:app /app/backups
   ```

4. Démarrer l'application :

   ```sh
   docker compose up --build -d
   ```

5. Vérifier son état et consulter les journaux :

   ```sh
   docker compose ps
   docker compose logs -f web
   ```

   Quand le socle est prêt, l'application sera accessible sur
   `http://localhost:8088` par défaut. Depuis un autre appareil du réseau local,
   utilisez l'adresse réseau de l'ordinateur qui l'héberge.

6. Après le premier démarrage, créer la famille et son compte parent :

   ```sh
   docker compose exec web python manage.py setup_family
   ```

7. Ajouter les modèles de missions initiaux (suggestions modifiables) :

   ```sh
   docker compose exec web python manage.py seed_missions
   ```

8. Ajouter le catalogue initial des récompenses suggérées :

   ```sh
   docker compose exec web python manage.py seed_rewards
   ```

   La commande s'exécute une seule fois après la création d'une famille. Si
   l'installation comprend plusieurs familles, précisez l'identifiant voulu
   avec `docker compose exec web python manage.py seed_rewards --family-id 1`.
   Elle est idempotente et ne remplace pas les récompenses déjà personnalisées.

## Boutique de récompenses

Le parent peut créer, modifier et archiver des récompenses bilingues en
français et en arabe, puis consulter toutes les demandes. L'enfant voit les
récompenses de sa famille, son solde et l'historique de ses demandes. Une demande
n'est possible que si le solde couvre le prix ; elle conserve le prix affiché
au moment de la demande. Seule l'acceptation du parent débite les pièces, une
fois, dans la même transaction que la décision. Le refus ne débite rien et
l'archivage conserve les demandes et leurs historiques.

## Habitudes et planning

1. Le parent ouvre **Habitudes**, crée une habitude quotidienne ou
   hebdomadaire, choisit les enfants concernés et, pour une fréquence
   hebdomadaire, sélectionne les jours actifs. Un moment de la journée et une
   heure précise sont facultatifs.
2. L'enfant retrouve ses habitudes dans **Mon planning** et peut signaler une
   occurrence terminée.
3. Le parent ouvre **Habitudes à valider**, puis confirme explicitement la
   validation ou le refus. Une validation attribue les pièces et l'XP configurés
   pour l'habitude ; un refus ne modifie aucun solde.
4. Le parent peut consulter le planning par jour, semaine ou mois et filtrer
   par enfant. Le planning enfant propose une vue quotidienne ou hebdomadaire.

Les occurrences sont générées de façon idempotente lorsque la période du
planning est consultée ; aucun service de planification en arrière-plan n'est
nécessaire. Suspendre une habitude arrête les occurrences futures et conserve
leur historique. Les objectifs hebdomadaires avancés, exceptions et reports
restent prévus pour une version ultérieure.

## Niveaux et badges

L'XP est cumulative : les niveaux initiaux sont calculés aux seuils de 0, 100,
250, 450, 700, 1 000, 1 400, 1 900, 2 500 et 3 200 XP, sans remise à zéro lors
d'un changement de niveau. Les badges correspondant aux missions validées,
aux jours consécutifs d'activité, à certaines catégories de mission et aux
pièces sont attribués automatiquement et une seule fois.

Le parent peut attribuer les badges spéciaux depuis la page de progression d'un
enfant. Les badges qui supposent des informations non suivies par la V1
(rappels, entraide spontanée ou projets familiaux) restent attribués par le
parent ; aucune de ces conditions n'est déduite automatiquement.

## Ajustements des soldes et historique

Depuis la fiche de progression d'un enfant, le parent peut ajouter ou retirer
des pièces et/ou de l'XP en indiquant un montant et un motif. Chaque opération
est un nouveau mouvement signé, horodaté et attribué au compte parent ; aucun
mouvement antérieur n'est modifié ou effacé. Un retrait qui rendrait l'un des
soldes négatif est refusé. L'enfant et le parent peuvent consulter les
historiques distincts des pièces et de l'XP depuis la page de progression ;
l'enfant n'a aucun accès à la commande d'ajustement.

## Messages et notifications

Le parent peut envoyer un message en français et/ou en arabe à un enfant ou à
tous les enfants de sa famille, avec une date d'expiration facultative. Chaque
enfant ne voit que ses propres messages et peut les marquer lus ou non lus ;
les messages expirés restent dans l'historique.

Les notifications internes sont accessibles depuis la barre de navigation,
avec un compteur des éléments non lus et un historique marquable lu/non lu.
Elles sont générées pour les attributions, soumissions, validations et refus de
missions et d'habitudes, les demandes et décisions de récompense, et les
nouveaux messages. Aucune notification n'est envoyée par courriel ou à
l'extérieur de l'application. Les autres événements familiaux devront être
précisés avant d'ajouter de nouveaux déclencheurs.

## Parcours de mission disponible

1. Le parent ouvre **Missions**, crée ou choisit un modèle, puis l'attribue à un
   ou plusieurs enfants.
2. L'enfant se connecte avec son identifiant et son code personnel, ouvre
   **Mes missions** et signale une mission terminée.
3. Le parent ouvre **Missions à valider**, choisit une ou plusieurs demandes,
   puis confirme explicitement la validation ou le refus.
4. Une validation attribue les pièces et l'XP du modèle au moment de la
   décision ; le refus ne modifie aucun solde.

Les âges indiqués dans la bibliothèque sont des suggestions seulement et ne
bloquent jamais une attribution.

Le socle, les missions, les habitudes, les vues principales du planning, les
niveaux, les badges, les ajustements parentaux, la boutique, les messages et
les notifications internes sont disponibles pour les essais. L'impression
propose maintenant des aperçus 80 mm, des demandes historisées annulables et
des réglages familiaux ; l'envoi matériel à l'imprimante USB reste en attente
d'identification et de vérification du protocole. Les demandes restent
explicitement en attente de configuration et aucun contenu n'est envoyé à
l'imprimante. L'aperçu utilise le nom FAMIVERSE, car le logo n'est pas encore
fourni.

## Aperçu et configuration d'impression

Le parent ou l'enfant peut créer un aperçu des missions dues aujourd'hui ou de
la progression. Le contenu est figé au moment de la demande ; l'historique
indique que l'imprimante n'est pas configurée, et une demande en attente peut
être annulée. La mise en page de l'aperçu cible un rouleau de 80 mm.

Le parent peut saisir manuellement les vacances scolaires et jours fériés,
confirmer le calendrier, choisir les jours et l'heure prévue (par défaut du
lundi au vendredi à 16 h 15), et régler les marges, la densité, l'avance papier
et la coupe. Aucune date n'est préremplie. L'impression automatique et l'envoi
USB restent désactivés tant que le pilote/protocole et le matériel n'ont pas
été vérifiés ; les options de réglage ne constituent pas une confirmation de
compatibilité matérielle.

Cette configuration initiale sert aux essais sur un réseau de confiance. La
connexion HTTP n'est pas chiffrée ; ne l'utilisez pas pour transmettre des codes
ou des données personnelles depuis un réseau partagé. La configuration HTTPS
sera nécessaire avant un usage familial réel ou une exposition hors du réseau
privé.

## Arrêt et redémarrage

```sh
docker compose stop
docker compose start
```

`docker compose down` arrête et retire les conteneurs, mais conserve les
volumes nommés. Ne supprimez pas les volumes : ils contiennent la base et les
fichiers utilisateurs.

## Sauvegarde et restauration

L'espace parent propose la sauvegarde manuelle avec téléchargement, un
historique, ainsi qu'une programmation quotidienne à 02 h par défaut. Les
versions automatiques sont limitées à 30 ; les téléchargements manuels et les
copies de protection avant restauration ne sont pas supprimés par cette règle.
Le service `backup_scheduler` exécute la programmation sans dépendre d'Internet.

Une archive contient l'export de la base, les fichiers de `MEDIA_ROOT` et un
manifeste non secret. Une signature et les empreintes des fichiers sont
vérifiées avant le téléchargement ou la restauration. Le fichier `.env` et les
secrets ne sont jamais exportés : conservez `DJANGO_SECRET_KEY` séparément et
gardez la même valeur pour vérifier une archive. Les archives ne sont pas
chiffrées ; protégez le disque ou le partage de destination et les téléchargements.

La restauration n'est proposée qu'aux parents d'une installation contenant une
seule famille, afin d'éviter d'écraser les données d'autres familles. Elle peut
utiliser une sauvegarde présente sur le serveur ou importer une archive exportée.
Elle exige la saisie de `RESTAURER`, vérifie l'intégrité et l'état des
migrations, crée d'abord une sauvegarde de protection et restaure les médias
avec la base. Utilisez la même version du code et le même `DJANGO_SECRET_KEY`
que ceux ayant créé l'archive. Les sessions de connexion peuvent être
invalidées. Les erreurs sont consignées dans l'historique ; une restauration
n'est considérée réussie qu'après un test effectif.

Les ressources statiques sont collectées au démarrage puis servies par
WhiteNoise. Les pages dynamiques et les données des comptes ne sont pas mises
en cache hors connexion.

## Dépannage

- État des services : `docker compose ps`
- Journaux : `docker compose logs --tail=100 web`
- Si le port 8088 est déjà utilisé, changez `APP_PORT` dans `.env`, puis
  redémarrez avec `docker compose up -d`.
- Ne publiez pas le port de la base de données et n'ouvrez pas l'accès depuis
  Internet.
