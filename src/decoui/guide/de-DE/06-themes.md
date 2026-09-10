# Designs

Das Zahnrad-Symbol oben rechts öffnet die Einstellungen, in denen alle verfügbaren Designs aufgelistet sind und das aktuell aktive Design vorausgewählt ist.

Designs werden einmalig beim Start der Anwendung geladen, sodass eine Änderung erst beim **nächsten** Start wirksam wird. Beim Schließen des Dialogs ändert sich am aktuellen Fenster nichts; der Dialog weist Sie vor der Auswahl auch darauf hin.

decoui enthält 4 Standarddesigns: ein helles Standarddesign und drei Designs im Panel-Stil.

Eigene Designs werden aus ``~/.decoui/themes`` geladen — jeweils eine JSON-Datei pro Design, ganz ohne Python-Code. Eine Designdatei definiert Farben, Eckenradien und Schriftarten. Der einfachste Weg zur Erstellung besteht darin, ein integriertes Design mit ``extends`` zu erweitern und nur die gewünschten Eigenschaften zu überschreiben.

Da Designs reine Präsentationssache sind, führt eine fehlerhafte Designdatei niemals zum Absturz: Nicht lesbare Dateien werden übersprungen und alle anderen Designs wie gewohnt geladen. Kann ein ausgewähltes Design nicht aufgelöst werden, wird auf das helle Standarddesign zurückgegriffen. In beiden Fällen wird beim Start der Anwendung ein Hinweis angezeigt.

Ihre Auswahl wird anhand der ID gespeichert, sodass das Umbenennen einer Datei die Einstellung nicht zurücksetzt. Auch wenn eine Designdatei vorübergehend fehlt, bleibt die Auswahl erhalten und wird wieder aktiv, sobald die Datei zurückkehrt.
