# Sortie et Journaux

Tout ce qu'un outil affiche (print) ou consigne dans les journaux apparaît en temps réel dans la console de sortie sous le formulaire pendant son exécution. Les niveaux de journalisation sont identifiés par un code couleur, et la sortie standard de ``print`` dispose de sa propre couleur afin de rester bien distincte des messages de journalisation.

* ``Copier`` (``Copy``) : copie l'intégralité de la console dans le presse-papiers.
* ``Voir le journal`` (``View Log``) : ouvre la sortie de cette exécution dans une fenêtre distincte et redimensionnable.

La fenêtre de journalisation est recommandée en cas de volume important de sorties. Elle apporte les fonctionnalités suivantes :

* Un bouton bascule par niveau de journalisation : désactivez ``DEBUG`` pour n'afficher que l'essentiel, ou cliquez sur ``Aucun`` (``None``) puis ``ERROR`` pour ne voir que les erreurs.
* Un champ de recherche filtrant les lignes correspondantes.
* ``Tout copier`` (``Copy All``).

Le filtrage dans cette fenêtre ne modifie en aucun cas la console de la page d'origine ; la fenêtre conserve sa propre copie des lignes.

La sortie de chaque exécution étant enregistrée, le même journal peut être rouvert ultérieurement depuis l'historique, même longtemps après la fermeture de l'onglet.
