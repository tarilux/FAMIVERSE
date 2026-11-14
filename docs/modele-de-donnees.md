# Modèle de données proposé — FAMIVERSE V1

Cette conception suit une architecture Django + PostgreSQL. Les comptes,
missions, habitudes, occurrences, journaux de progression, niveaux, badges,
boutique de récompenses, messages, notifications et le socle d'aperçu
d'impression disposent de modèles, migrations et tests. Le manifeste PWA, le
service worker et le service des fichiers statiques complètent l'architecture
de l'interface sans stocker les pages ni données privées hors connexion. Les
autres entités décrites restent une proposition de conception tant qu'elles ne
sont pas implémentées.

## Entités et relations

### Famille et accès

- **Family** : foyer, fuseau horaire et paramètres communs.
- **Account** : membre authentifié rattaché à une famille, avec un rôle parent
  ou enfant, un état actif/archivé et un justificatif d'accès stocké sous forme
  de hash. Plusieurs comptes parents et profils enfants peuvent appartenir à la
  même famille.
- **ChildProfile** : extension d'un compte enfant ; prénom, date de naissance,
  avatar, langue et préférences. L'âge et la tranche d'âge sont calculés depuis
  la date de naissance. Le profil de maturité est indépendant de l'âge.

Les connexions enfant et parent sont autorisées par le serveur selon le rôle.
Chaque requête portant sur un enfant doit être limitée au profil de la session,
sauf opération parent autorisée.

### Missions, habitudes et planning

- **MissionCategory** : catégorie archivable, avec libellés français et arabe.
- **MissionTemplate** : modèle créé par un parent, avec titre et description en
  français, traduction arabe facultative, catégorie, âge conseillé indicatif,
  valeurs proposées en pièces et XP, et règle simple de récurrence. L'âge
  conseillé n'est jamais un critère d'attribution.
- **MissionOccurrence** : exécution attribuée à un enfant donné. Une attribution
  à plusieurs enfants crée une occurrence distincte par enfant. Elle conserve
  des copies du titre et de la description dans les deux langues, de l'échéance,
  du statut et de la catégorie. Au moment de la validation, elle conserve les
  valeurs accordées en pièces et XP.
- **HabitTemplate** : habitude distincte d'une mission ponctuelle, assignée à
  un ou plusieurs enfants, avec fréquence quotidienne ou hebdomadaire, jours
  choisis, moment de la journée et heure facultative, date d'activation, état
  actif, suspendu ou archivé et valeurs facultatives en pièces et XP.
- **HabitOccurrence** : occurrence datée d'une habitude pour un enfant, avec
  copies des contenus et de l'horaire, état, historique de soumission/validation
  et valeurs accordées figées lors de la validation. Une contrainte garantit au
  plus une occurrence par habitude, enfant et date ; les périodes demandées par
  le planning sont générées de façon idempotente.

Les statuts et changements sont contrôlés par le serveur. Seul un parent peut
valider ou refuser une occurrence. La création d'une occurrence ne produit pas
de doublon pour le même enfant et la même date. Les vues de planning disponibles
sont quotidiennes et hebdomadaires pour l'enfant, quotidiennes, hebdomadaires
et mensuelles pour le parent. Les objectifs hebdomadaires avancés, exceptions
et reports restent hors V1.

### Progression, pièces et badges

- **CoinTransaction** : mouvement signé du solde de pièces ; motif, date,
  auteur parent, enfant et source éventuelle (mission, habitude, récompense,
  ajustement ou correction).
- **XpTransaction** : mouvement signé d'XP, avec les mêmes informations
  essentielles, dans une table distincte des pièces. Un ajustement parental
  enregistre un nouveau mouvement avec son montant, son sens, son motif, sa
  date et son auteur ; le solde est revérifié sous verrou avant un retrait.
- **LevelDefinition** : numéro, nom français/arabe et seuil cumulatif d'XP.
  Les dix seuils V1 sont initialisés par une migration ; l'XP reste cumulative.
- **BadgeDefinition** : définition bilingue des badges initiaux, catégorie et
  condition identifiée par une clé de règle connue du code ; aucune règle
  arbitraire exécutable n'est stockée en base. Les conditions non mesurées
  automatiquement sont attribuées par un parent.
- **BadgeAward** : badge accordé une seule fois à un enfant, date d'obtention
  et auteur parent pour une attribution manuelle.

Les soldes sont calculés depuis les mouvements. Une opération qui peut rendre
le solde négatif est rejetée dans une transaction atomique. Pour
éviter que deux validations simultanées dépassent le solde, le service verrouille
la ligne du profil enfant, recalcule le solde puis écrit le mouvement avant de
libérer la transaction. Un mouvement passé n'est jamais modifié ou supprimé :
une correction est un nouveau mouvement lié au précédent. Des contraintes
d'unicité sur les sources de récompense empêchent une double attribution ou un
double débit.

### Récompenses

- **Reward** : article individuel de la boutique, catégorie, nom et description
  en français/arabe, prix en pièces et état actif/archivé.
- **RewardRequest** : enfant demande une récompense ; enfant, article, prix figé,
  dates, statut demandé/accepté/refusé et décision du parent. Une contrainte
  unique empêche deux demandes simultanées identiques par enfant.

L'acceptation et le débit des pièces s'effectuent ensemble en transaction. Un
refus ne débite rien. Le prix historique ne change pas si l'article est modifié
par la suite. Les demandes et mouvements de pièces liés ne peuvent être
supprimés ; l'archivage masque seulement l'article du catalogue. Les récompenses
collectives sont exclues de la V1.

### Messages, notifications et journal

- **FamilyMessage** : famille, auteur parent, contenu français/arabe,
  destinataires enfants et date d'expiration facultative.
- **MessageRecipient** : réception et état lu/non lu par enfant, afin de garder
  un suivi individuel des messages envoyés à tous. Les messages expirés restent
  accessibles dans l'historique.
- **Notification** : destinataire, catégorie, titre et résumé français/arabe,
  source idempotente, dates de création/lecture et état lu/non lu. Les
  notifications peuvent référencer un message et sont limitées à l'utilisateur
  destinataire.
- **ActivityEvent** : journal append-only des opérations importantes, acteur,
  date, objet concerné et détails structurés minimaux.

Les journaux ne doivent pas contenir de code secret ni de données sensibles
inutiles. L'archivage des profils et modèles préserve les événements historiques.
Les notifications couvrent les événements de missions, habitudes, récompenses
et messages décrits ci-dessus ; les déclencheurs d'« événement familial » au
sens général restent à préciser avant automatisation.

### Impression, fichiers et sauvegardes

- **PrintJob** : demande parent/enfant avec instantané de ticket, enfant,
  demandeur, statut et date. L'aperçu et l'annulation d'une demande en attente
  sont disponibles ; le statut reste « en attente de configuration » tant que
  le protocole USB n'est pas vérifié et qu'aucun moteur d'impression n'est
  configuré.
- **PrintSettings** : paramètres 80 mm liés à la famille, horaire/jours prévus,
  marges, densité, avance, coupe et confirmation manuelle du calendrier.
  L'impression automatique et le paramètre de configuration matérielle
  restent désactivés dans cette étape.
- **PrintCalendarBlock** : période manuelle de vacances scolaires ou jour férié,
  avec dates et libellé fournis par la famille. Aucun calendrier n'est
  prérempli ou déduit.
- **StoredFile** : métadonnées et chemin interne des photos/documents ; le
  contenu est conservé dans le volume privé de l'application, jamais dans le
  dépôt de code.
- **BackupRun** : date, résultat, emplacement logique, empreinte d'intégrité et
  version de sauvegarde ; journal des succès, échecs, rétention et restaurations.
- **BackupSettings** : programmation quotidienne ou hebdomadaire et nombre de
  versions automatiques conservées, par famille.
- **DocumentTemplate** : modèle simple de liste, document ou certificat, avec
  contenu traduisible et état actif/archivé. Il ne constitue pas un éditeur
  avancé.
- **LibraryItem** : référence à un support initial fourni avec l'application,
  sa catégorie et les langues disponibles. Les éléments réellement fournis
  devront être versionnés avec le code et leurs licences vérifiées.

## Relations principales

```text
Family 1---N Account 1---0..1 ChildProfile
Family 1---N MissionTemplate 1---N MissionOccurrence N---1 ChildProfile
Family 1---N HabitTemplate 1---N HabitOccurrence N---1 ChildProfile
ChildProfile 1---N CoinTransaction
ChildProfile 1---N XpTransaction
ChildProfile 1---N RewardRequest N---1 Reward
ChildProfile N---N BadgeDefinition (via BadgeAward)
Family 1---N FamilyMessage 1---N MessageRecipient N---1 ChildProfile
Account 1---N Notification
Family 1---N PrintJob, BackupRun, ActivityEvent, DocumentTemplate
```

## Règles d'intégrité à couvrir par des tests

1. Une famille ne consulte que ses propres données ; un enfant ne consulte et
   ne modifie que son espace autorisé.
2. Un enfant ne peut ni approuver ses occurrences ni décider d'une demande de
   récompense ni modifier ses transactions.
3. La validation d'une mission ou d'une habitude et l'écriture de ses gains sont
   atomiques, sérialisées par verrou de profil et ne peuvent réussir qu'une fois.
4. Les pièces et XP restent distincts ; aucun solde ne peut devenir négatif.
5. Une demande acceptée débite exactement le prix figé, une seule fois.
6. Un ajustement parental crée un mouvement distinct et ne rend jamais le solde
   de pièces ou d'XP négatif.
7. Archiver un profil, une mission ou une récompense ne supprime pas l'historique.
8. Le changement de date de naissance ou de tranche ne modifie ni les soldes,
   ni le niveau, ni les badges obtenus.
9. Toute requête récurrente produit au plus une occurrence par enfant et période.
10. Un badge ne peut être accordé deux fois au même enfant, sauf si une règle
   future explicite définit des niveaux ou des occurrences multiples.

Les archives comprennent l'export de la base et les fichiers média, un
manifeste signé par la clé Django et les empreintes SHA-256. La restauration
est limitée aux installations mono-famille et exige le même état de migrations ;
une sauvegarde de protection est créée avant de remplacer les données. Les
archives ne sont pas chiffrées et le fichier `.env` n'est pas inclus.

## Hors périmètre de ce modèle V1

Pas de délégation entre enfants, note hebdomadaire, pénalités, récompenses
collectives, badges personnalisables, campagnes avancées, moteur
d'automatisations configurable ou fonctions familiales prévues pour les phases
ultérieures. Le modèle pourra évoluer par migrations sans implémenter ces
fonctions par anticipation.
