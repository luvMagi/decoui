# Thèmes

L'icône d'engrenage en haut à droite ouvre les Paramètres, qui listent l'ensemble des thèmes disponibles et sélectionnent par défaut celui actuellement actif.

Themes are applied at once. Choosing one restyles every window that is open,
without rebuilding anything: a tool that is running goes on running, forms keep
what was typed into them, and output already printed is re-inked in the new
colours. The console's scroll position is the one casualty -- it returns to the
newest line.

The **language**, chosen in the same dialog, is the exception: it takes effect
the next time the application runs. Text is read as each widget is built, in far
more places than colour is, and there is nothing that can catch the rest the way
the stylesheet catches colour.

decoui est fourni avec 4 thèmes intégrés : un thème clair par défaut et trois thèmes inspirés des interfaces à panneaux.

Vos thèmes personnalisés sont lus depuis ``~/.decoui/themes`` — un fichier JSON par thème, sans aucune ligne de code Python requise. Un fichier de thème définit ses couleurs, rayons d'arrondi et polices ; le moyen le plus simple d'en créer un est d'hériter d'un thème intégré via ``extends`` et de ne surcharger que les propriétés souhaitées.

Un thème n'étant qu'une configuration de présentation, un fichier défectueux n'est jamais bloquant : un fichier illisible est ignoré et tous les autres thèmes se chargent normalement, et une sélection impossible à résoudre bascule sur le thème clair par défaut. Dans les deux cas, une notification s'affiche au démarrage de l'application.

Votre sélection étant stockée par identifiant (ID), renommer un thème ne fait pas perdre votre préférence, et un thème temporairement introuvable n'est pas désélectionné : il sera réappliqué automatiquement dès que le fichier sera restauré.
