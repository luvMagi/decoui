# Parameter wiederverwenden

Die Wiederholungsfunktion (Replay) stellt die Argumente eines früheren Laufs im Formular wieder her. Es wird dabei **nichts** automatisch erneut ausgeführt — erst wenn Sie selbst auf ``Ausführen`` (``Run``) drücken, startet die Verarbeitung. Dies ist ein bewusstes Design: So können Sie die Parameter eines sicherheitskritischen Laufs wiederherstellen, ein einzelnes Feld anpassen und erst dann entscheiden, fortzufahren.

Es gibt zwei Wege:

* Auf der Werkzeugseite: ``Wiederholen`` (``Replay``) öffnet den Verlauf bereits gefiltert nach diesem Werkzeug, sodass Sie aus den Läufen dieses Werkzeugs statt aus allen Einträgen auswählen können.
* Im Verlauf: Wählen Sie eine beliebige Zeile aus und drücken Sie ``Parameter wiederverwenden`` (``Replay Params``).

Der gespeicherte Snapshot liegt im Textformat vor, sodass Werte in ihrer Textform wiederhergestellt und beim nächsten Start des Werkzeugs erneut konvertiert werden. Ein Dateipfad wird beispielsweise als Textzeichenfolge statt als Pfadobjekt zurückgegeben — das Werkzeug liest ihn dann exakt so ein, als hätten Sie ihn manuell eingegeben.
