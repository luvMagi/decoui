# Thèmes

L'icône d'engrenage en haut à droite ouvre les Paramètres, qui listent l'ensemble des thèmes disponibles et sélectionnent par défaut celui actuellement actif.

Les thèmes sont appliqués une seule fois au démarrage de l'application : toute modification ne prendra donc effet qu'au **prochain** lancement. Aucun élément de la fenêtre ouverte ne changera à la fermeture du dialogue ; la boîte de dialogue vous en informe d'ailleurs avant votre choix.

decoui est fourni avec 4 thèmes intégrés : un thème clair par défaut et trois thèmes inspirés des interfaces à panneaux.

Vos thèmes personnalisés sont lus depuis ``~/.decoui/themes`` — un fichier JSON par thème, sans aucune ligne de code Python requise. Un fichier de thème définit ses couleurs, rayons d'arrondi et polices ; le moyen le plus simple d'en créer un est d'hériter d'un thème intégré via ``extends`` et de ne surcharger que les propriétés souhaitées.

Un thème n'étant qu'une configuration de présentation, un fichier défectueux n'est jamais bloquant : un fichier illisible est ignoré et tous les autres thèmes se chargent normalement, et une sélection impossible à résoudre bascule sur le thème clair par défaut. Dans les deux cas, une notification s'affiche au démarrage de l'application.

Votre sélection étant stockée par identifiant (ID), renommer un thème ne fait pas perdre votre préférence, et un thème temporairement introuvable n'est pas désélectionné : il sera réappliqué automatiquement dès que le fichier sera restauré.
