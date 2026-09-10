# Reutilizando Parâmetros

A funcionalidade Repetir (Replay) restaura os argumentos de uma execução anterior no formulário. Ela **não** executa nada novamente de forma automática — nada é executado até que você mesmo pressione ``Executar`` (``Run``). Esse comportamento é intencional: permite que você restaure uma execução que realiza alterações críticas, modifique apenas um campo e só então decida prosseguir.

Existem duas maneiras de acessá-la:

* Na página de uma ferramenta, ``Repetir`` (``Replay``) abre o histórico já filtrado para essa ferramenta, permitindo escolher entre as execuções da própria ferramenta em vez de todas as ferramentas.
* No histórico, selecione qualquer linha e pressione ``Reutilizar parâmetros`` (``Replay Params``).

O instantâneo salvo é texto, portanto, os valores são restaurados em sua forma literal de texto e convertidos novamente na próxima execução da ferramenta. Um caminho de arquivo, por exemplo, retorna como texto em vez de um objeto de caminho — o qual a ferramenta relê exatamente da mesma forma como se você o tivesse digitado.
