# Réutiliser les Paramètres

La fonction Rejouer (Replay) restaure dans le formulaire les arguments d'une exécution précédente. Elle **ne** réexécute **rien** automatiquement : aucun traitement n'est lancé tant que vous ne cliquez pas vous-même sur ``Exécuter`` (``Run``). Ce comportement est délibéré : il vous permet de rappeler les paramètres d'une opération sensible, de modifier un seul champ, puis de décider en toute sécurité de lancer l'exécution.

Il existe deux points d'accès :

* Depuis la page d'un outil : ``Rejouer`` (``Replay``) ouvre l'historique déjà filtré pour cet outil, vous permettant de choisir parmi ses propres exécutions plutôt que parmi l'ensemble des enregistrements.
* Depuis l'historique : sélectionnez n'importe quelle ligne et cliquez sur ``Réutiliser les paramètres`` (``Replay Params``).

Le snapshot enregistré étant au format texte, les valeurs sont restaurées sous forme de chaînes littérales et converties à nouveau lors de la prochaine exécution de l'outil. Un chemin de fichier, par exemple, est restitué sous forme de chaîne de caractères plutôt que d'objet de chemin — l'outil le relit ensuite exactement comme si vous l'aviez saisi manuellement.
