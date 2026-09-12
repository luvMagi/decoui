# Ausgabe und Protokolle

Alles, was ein Werkzeug ausgibt (print) oder protokolliert, wird während der Ausführung in Echtzeit in der Ausgabekonsole unter dem Formular angezeigt. Die Protokollierungsstufen sind farblich gekennzeichnet, und reguläre ``print``-Ausgaben werden in einer eigenen Farbe dargestellt, um sie von Logmeldungen unterscheidbar zu machen.

Wenn die Anwendung es einschaltet, wird der Rückgabewert eines erfolgreichen Laufs am Ende der Ausgabe gedruckt: eine Leerzeile, eine Linie ``========== Ergebnis ==========``, dann der Wert. Bei einem fehlgeschlagenen oder abgebrochenen Lauf und bei einem Lauf ohne Rückgabewert wird nichts gedruckt.

* ``Kopieren`` (``Copy``): Kopiert den gesamten Inhalt der Konsole in die Zwischenablage.
* ``Protokoll anzeigen`` (``View Log``): Öffnet die Ausgabe des aktuellen Laufs in einem separaten, in der Größe anpassbaren Fenster.

Das Protokollfenster empfiehlt sich bei umfangreichen Ausgaben. Es bietet folgende zusätzliche Funktionen:

* Ein Umschalter pro Protokollstufe: Deaktivieren Sie ``DEBUG``, um nur wichtige Meldungen zu sehen, oder drücken Sie ``Keine`` (``None``) und dann ``ERROR``, um nur Fehler anzuzeigen.
* Ein Suchfeld zur Filterung nach übereinstimmenden Zeilen.
* ``Alles kopieren`` (``Copy All``).

Das Filtern im Protokollfenster hat keinerlei Einfluss auf die Konsole der Ursprungsseite; das Fenster verwaltet eine eigene Kopie der Zeilen.

Die Ausgabe jeder Ausführung wird gespeichert, sodass dasselbe Protokoll auch lange nach dem Schließen des Tabs jederzeit aus dem Verlauf erneut geöffnet werden kann.
