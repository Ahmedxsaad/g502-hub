# Parité avec l’interface Python — mise à jour du 29 octobre 2026

Les écarts fonctionnels recensés dans le premier audit ont été portés dans la version native. Ce document précise les vérifications réalisées ; il ne donne pas un pourcentage de conformité que les essais ne permettraient pas d’établir.

## Corrections réalisées

| Domaine | Comportement porté |
| --- | --- |
| Présentation | Ready vert `#3ddc84`, halo de fond identique en coordonnées/couleurs, halos LED, formes de survol et de sélection. |
| Couleurs | Roue, luminosité, HEX/RGB, palette et couleurs personnelles : ajout, réutilisation, clic droit pour supprimer, limite de dix, absence de doublons. |
| Éclairage embarqué | Période minimale de 1 000 ms, arrêt du live lorsqu’on modifie l’éclairage sauvegardé, aperçu matériel, synchronisation des deux zones et mise à jour des LED alternatives uniquement quand elles changent. |
| DPI | Limites et pas lus depuis le capteur, clic sur la piste pour insérer un niveau, glisser avec aperçu matériel, insertion/suppression compactes conservant défaut/sniper/niveau actif, avertissement quand aucun bouton n’active le sniper. |
| Assignations | Profils d’usine lus sur la souris pour Restore default ; G-Shift retrouve Unassigned ; listes complètes de raccourcis/médias ; capture d’une combinaison ; confirmation avant de retirer le dernier clic gauche. |
| Macros assignées | Nom et mode de stockage affichés dans la fiche et au survol au lieu de la valeur physique Disabled ; sélection dans la liste ; résumé des emplacements ; retrait de l’assignation du service quand on choisit une autre commande. |
| Éditeur de macros | Once imposé pour une macro stockée sur la souris, capacité et erreurs de conversion affichées avant sauvegarde, validation d’une macro vide/trop grande, enregistrement et remise en ordre des événements, liste média complète, attente jusqu’à 600 000 ms. |
| Texte | Clavier virtuel limité aux capacités réellement utilisées, délai d’attachement du premier périphérique, noms/erreurs de macro visibles, test de lecture des événements uinput et confirmation de fonctionnement par l’utilisateur. |
| Répétition | Cycle de 10 ms incluant les pauses des événements, proche de 100 CPS ; test de non-régression. |
| Règles | Sept modèles Python, suggestions récentes, historique des applications/médias, choix d’une valeur récente, descriptions du déclencheur et de l’action, aides par effet, validation du texte recherché. L’observation du contexte demandée par l’interface expire après sa fermeture, sauf lorsqu’une règle l’utilise. |
| Réglages | Téléchargement initial et nouveau téléchargement de la photo, assistant de permissions via pkexec, état/boutons GSI pour CS2/Dota, bridge Proton affiché par jeu et disponibilité des DLL. |
| À propos | Auteur, liens, crédits, licence, mentions de marques, informations système/périphérique et copie pour rapport de bug. |
| Effets numériques | Zones de capture, mode Vivid/Average, ajustement HSV, direction de la vague, analyse audio FFT/gain/gate/release/centroïde/beat, Pulse/Spectrum/Rainbow et palette des pochettes alignés sur les formules Python. |
| GSI | Séquences CS2/Dota alignées sur Python : santé, équipes, bombe/countdown, brûlures/flashs, kills, mana, silence/stun, pause et respawn ; historiques séparés par jeu. |
| Défaillance de capture | Arrêt de l’effet manuel ou abandon temporaire de l’override de règle et restauration de l’éclairage sauvegardé. |

## Validation

- `cargo fmt --check`, `cargo check --locked`, compilation release et vérification du diff.
- **51 tests automatiques réussis**, plus **un test réel uinput activé explicitement et réussi**. Le test uinput ne s’exécute pas par défaut en CI : il exige les permissions sur le périphérique et réserve son propre clavier virtuel avant d’envoyer les touches.
- Contrats de référence extraits des sources Python : catalogues UI, raccourcis AZERTY, modèles, régions et couleurs d’écran, effets audio/vague, palette, analyse audio, événements CS2/Dota. Les fixtures et tests sont conservés dans `tests/`.
- Comparaison numérique des résultats aux valeurs Python, avec tolérances documentées dans les assertions ; conservation exacte des octets non modifiés dans les tests de profils.
- Rendu des huit pages sur X11 isolé, sans écriture de réglages au repos ; examen des captures.
- Essais interactifs sur faux service : ajout de DPI, restauration des assignations d’usine/G-Shift, règles, affichage du nom d’une macro et couleurs personnelles. Ces essais ne modifient pas la mémoire réelle de la souris.
- Sur la souris réelle : lecture des cinq profils utilisateur et des cinq profils d’usine, plage capteur 100–25 600 par pas de 50, reconnexion et démarrage du service installé.
- Le test uinput a reçu les 54 événements clavier attendus d’une macro de texte après relâchement de sa touche. L’utilisateur a ensuite confirmé que sa propre macro écrit correctement dans un champ de texte.

## Limites de la conclusion

La présence et les tests des fonctions ne constituent pas une preuve d’égalité à 100 % pour toute interaction ou tout environnement. Le rendu des widgets Qt et egui, l’anticrénelage et le redimensionnement des images peuvent différer. La capture clavier egui normalise certaines touches (notamment du pavé numérique) ; l’égalité de toutes les séquences de touches physiques n’est pas établie.

Les configurations/launchers natifs gardent les chemins historiques séparés de Python ; les informations système affichent naturellement la pile native. Le sélecteur de fichiers utilise Zenity avec saisie de chemin en secours. Les scénarios réels de portail Wayland, jeux en cours d’exécution et préfixes Proton restent à éprouver, en complément des tests numériques et du protocole.

Ces limites doivent être conservées dans les annonces : les écarts identifiés ont été corrigés, mais une promesse de parité parfaite serait plus forte que les preuves disponibles.

## Personnalisation du bandeau demandée après cet audit

Le nom G502 Hub et les contrôles de fenêtre sont intégrés au bandeau : réduction, agrandissement/restauration, fermeture après sauvegarde, déplacement, double-clic et redimensionnement par les bords. F11 contrôle le plein écran (hors capture/enregistrement de touches). Cette présentation remplace volontairement la décoration externe de Python. Les actions ont été vérifiées avec Xfwm sur un affichage X11 isolé, y compris une fermeture pendant une écriture retardée sur faux service.

## Reprise des macros après veille et réinitialisation USB

Le service compare les horloges Linux BOOTTIME et MONOTONIC pour détecter une veille sans dépendre de l’heure civile. Au réveil, il arrête les anciennes exécutions, remet à zéro les boutons, recrée le périphérique virtuel à la prochaine macro et réouvre la souris. Si elle n’est pas encore disponible, la reconnexion existante réessaie toutes les deux secondes.

Lorsqu’une macro applicative est affectée, l’abonnement Mouse Button Spy est renouvelé toutes les cinq secondes. Cela couvre une perte silencieuse de notifications même si les requêtes de profil répondent encore. Ce renouvellement ne stoppe pas les macros maintenues et conserve les événements reçus pendant la requête. Aucun renouvellement n’est envoyé sans macro applicative affectée.

Les tests couvrent plusieurs cycles de veille simulés par les horloges, une longue activité sans veille et des renouvellements HID++ successifs avec notifications intercalées, sans écriture de mémoire flash. Sur la souris réelle, un arrêt volontaire de l’abonnement a été suivi de son renouvellement automatique acquitté après 2,74 secondes, avec le service toujours connecté et sans erreur. Une véritable mise en veille reste à confirmer sur le PC de l’utilisateur.
