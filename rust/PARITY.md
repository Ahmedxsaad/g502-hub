# Vérification de parité G502 Hub — 29 octobre 2026

La parité parfaite n'est **pas acquise**. Ce bilan compare le code des deux interfaces et leurs chemins d'exécution ; il distingue la présence d'une fonction, un test automatisé et une validation en situation réelle. Il ne constitue pas une certification de tous les périphériques, jeux et environnements.

Références locales : dépôt Python `g502-hub` (branche avec service en arrière-plan) et dépôt natif `g502-hub-rust` (modifications locales actuelles). Les captures publiques ne suffisent pas à vérifier les interactions : le code des pages Python est la référence principale.

## Corrections de cette passe

- Statut Ready : vert `#3ddc84`, identique à `theme.OK` en Python. Les erreurs restent rouges et les états d'attente neutres.
- Halo derrière la souris : centre `(300, 560)`, rayon `620`, mêmes trois étapes de couleur/transparence que le dégradé Python, peint avant la photo. Les halos colorés des LED restent distincts.
- Couleurs personnelles : bouton « + » rond de 24 px avec contour pointillé et infobulle ; absence de doublons, sans tenir compte de la casse ; réutilisation et suppression par clic droit. Limite de 10 couleurs identique à Python.
- La roue ne change plus la couleur lors d'un clic dans les coins extérieurs au disque.
- Infobulles sur les couleurs et indication du clic droit pour les couleurs enregistrées.

## Fonctions comparées

| Domaine | Présence dans la version native | Écarts confirmés / limites |
| --- | --- | --- |
| Fenêtre et navigation | Barre de 64 px, rail de 92 px, marges, pages, choix du profil, statut et DPI | Polices et widgets Qt/egui différents : aucune égalité pixel par pixel garantie. |
| Souris | Photo, masques LED, formes de survol et de sélection, badges, légendes, animations, halo de fond | En l'absence de photo, Rust affiche un texte ; Python possède aussi un téléchargement initial et un bouton de téléchargement. |
| Éclairage embarqué | Deux zones, synchronisation, Fixed/Breathing/Color cycle/Off, roue, valeur, HEX, RGB, palette, couleurs personnelles, période et intensité | La borne basse du curseur de période Rust est 100 ms contre 1 000 ms côté Python. Modifier l'éclairage embarqué n'arrête pas explicitement l'effet live comme Python. |
| Effets live | Screen/Audio/Wave/DPI ; grilles de choix, activation, descriptions, curseurs et couleurs ; nouveau choix d'écran | Les contrôles sont présents. Audio, portail Wayland et écran multiple ne sont pas intégralement validés sur une session réelle. |
| DPI | Piste logarithmique, glisser des niveaux, ajout/suppression, défaut/sniper, taux de rapport | Clic sur une zone libre de la piste pour ajouter un niveau absent ; Python compacte les niveaux et conserve les indices lors d'une suppression ; Rust utilise des cases vacantes. Bornes Rust fixées à 100–25 600 par pas de 50 plutôt que déterminées à partir du périphérique. |
| Assignations | Primaire/G-Shift, commandes souris/défilement/DPI/profils, raccourcis, médias et macros | Liste de raccourcis et de médias plus courte. Capture d'une combinaison remplacée par saisie textuelle. Restauration des boutons basée sur une liste fixe, pas sur le profil usine correspondant ; G-Shift ne retrouve pas le comportement « Unassigned » de Python. Confirmation de retrait du dernier clic gauche absente. |
| Macros | Création, édition, suppression, réorganisation d'étapes, clavier/texte/attente/souris/média, enregistrement, exécution app ou souris | Python force « Once » pour une macro stockée sur la souris et affiche sa capacité utilisée ; ces aides ne sont pas reproduites dans l'éditeur Rust. Il faut aussi comparer les messages d'erreur au moment de sauvegarder puis d'assigner. |
| Répétition des clics | Temporisation corrigée : cycle minimal de 10 ms incluant les pauses des événements | Test du moteur à environ 99 CPS ; le résultat d'un compteur dans un jeu dépend aussi du jeu et de sa lecture des entrées. |
| Règles | Édition, priorité, activation, suppression ; jeux/app/titre/média ; éclairage et profil | Menu de modèles prêts à l'emploi absent. Historique des applications/médias récents et suggestions absents. Présentation des résumés différente. |
| Profils et sauvegardes | Cinq cartes, nom, activation, inclusion dans le cycle, import/export, copie, reset usine, sauvegarde/restauration | Dialogues via Zenity ou alternative interne ; présentation et messages différents. Les écritures réelles ne sont pas déclenchées par les tests de cette passe. |
| Réglages | Démarrage automatique, arrêt complet, popup DPI, disposition clavier, rafraîchissement, bridge Proton, paramètres avancés | Téléchargement de photo et assistant de permissions absents. Commandes GSI existantes dans le service mais sans boutons équivalents dans cette page. Interface du bridge différente. |
| À propos | Nom, version expérimentale, lien au projet, licence/crédit principal | Présentation complète auteur/liens/crédits et copie des informations système pour un rapport de bug absentes. |
| Service et intégrations | Service séparé, socket IPC, reconnexion, macros, règles, RGB, GSI et bridge natifs | Présence du code ne prouve pas le comportement identique dans CS2/Dota/Proton ; ces scénarios nécessitent des essais dédiés. |

## Vérifications exécutées

- Compilation release ; formatage et vérification du diff.
- Suite de 35 tests réussie : protocole/transport, codecs et sauvegarde exacte de profils réels, protections d'écriture, macros, géométrie de souris, cycle des clics, capture Vivid, cycle de vie du service.
- Capture et examen visuel de l'interface avec Ready vert et halo.
- Test interactif du sélecteur de couleurs sur un service isolé : saisie HEX, ajout, refus d'un doublon, choix d'une autre couleur, réutilisation et suppression d'une couleur enregistrée. Les mutations sont envoyées à un faux service pour ne pas écrire la mémoire de la souris pendant ce test.
- Les sélecteurs d'éclairage embarqué, live audio/DPI et de règles appellent le même composant de couleur. Le câblage de sauvegarde globale est présent dans chacun ; tous leurs scénarios ne font pas l'objet d'un test d'interaction séparé.

## Conclusion

Ready, halo et couleurs personnelles sont corrigés et vérifiés. La migration reste fonctionnelle mais **ne doit pas être présentée comme une copie parfaite**. La liste ci-dessus décrit les écarts identifiés ; des essais d'usage sur la souris, les jeux et la capture Wayland restent nécessaires pour conclure sur la parité de comportement.
