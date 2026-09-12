# Ein Werkzeug ausführen

Das Formular eines Werkzeugs wird aus den von seiner Funktion deklarierten Parametern erstellt, sodass die Eingabefelder genau dem entsprechen, was dieses spezielle Werkzeug benötigt.

* Ein mit einem roten Sternchen (*) markiertes Feld ist ein Pflichtfeld und hat keinen Standardwert.
* ``Parameter`` (``Parameters``) klappt das Formular nach dem Ausfüllen zusammen, um mehr Platz für die Ausgabe zu schaffen.
* ``Ausführen`` (``Run``) startet das Werkzeug. Während der Ausführung wird die Schaltfläche ``Ausführen`` durch ``Stoppen`` (``Stop``) ersetzt.
* ``Zurücksetzen`` (``Reset``) setzt jedes Feld auf seinen deklarierten Standardwert zurück.

Einige Werkzeuge fordern vor dem Start eine Bestätigung an; dies wird vom Werkzeug selbst festgelegt und nicht von der Anwendung vorgegeben.

``Stoppen`` unterbricht ein laufendes Werkzeug. Ein Werkzeug, das reine Rechenoperationen ausführt oder wartet (sleep), stoppt unverzüglich. Eines, das auf ein externes Programm wartet, stoppt nur, wenn der Entwickler eine Bereinigungsroutine für diesen Fall implementiert hat — andernfalls kehrt die Seite in den Leerlaufzustand zurück, während das externe Programm weiterläuft.

Der Fortschrittsbalken bewegt sich hin und her, wenn ein Werkzeug den Gesamtarbeitsaufwand nicht angegeben hat, und zeigt einen prozentualen Fortschritt an, wenn dies der Fall ist.

Nach einem Lauf lässt sich mit dem Rückgabewert dreierlei tun:

* ``Ergebnis kopieren`` legt den Wert in die Zwischenablage.
* ``Ergebnis senden`` füllt damit das Feld eines anderen Werkzeugs, öffnet
  dieses Werkzeug und holt es nach vorn. Die Schaltfläche erscheint nur, wenn
  ein anderes Werkzeug erklärt, einen solchen Wert anzunehmen, und sie
  überschreibt, was im Feld stand.
* Die Anwendung kann den Wert außerdem in die Ausgabekonsole drucken lassen --
  siehe die nächste Seite.

Beide Schaltflächen zeigen den Wert im Tooltip und bleiben deaktiviert, bis ein
Lauf etwas zurückgibt.
