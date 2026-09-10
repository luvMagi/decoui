# Exécuter un Outil

Le formulaire d'un outil est automatiquement généré à partir des paramètres déclarés par sa fonction, de sorte que les champs correspondent exactement aux besoins de cet outil spécifique.

* Un champ marqué d'un astérisque rouge (*) est obligatoire et n'a pas de valeur par défaut.
* ``Paramètres`` (``Parameters``) replie le formulaire une fois rempli afin de laisser plus de place à la zone de sortie.
* ``Exécuter`` (``Run``) démarre l'outil. Pendant l'exécution, le bouton ``Exécuter`` est remplacé par ``Arrêter`` (``Stop``).
* ``Réinitialiser`` (``Reset``) remet tous les champs à leurs valeurs par défaut déclarées.

Certains outils demandent une confirmation avant de démarrer ; cela est déclaré par l'outil lui-même et n'est pas une décision prise par l'application.

``Arrêter`` interrompt un outil en cours d'exécution. Un outil qui effectue uniquement des calculs ou est en veille (sleep) s'arrête immédiatement. Un outil qui attend un programme externe ne s'arrête que si son auteur a prévu un traitement de nettoyage pour ce cas — sinon, la page revient à l'état inactif pendant que le programme externe continue de tourner.

La barre de progression effectue un mouvement de va-et-vient lorsque l'outil n'a pas indiqué la quantité totale de travail, et affiche un pourcentage réel lorsque celle-ci est définie.
