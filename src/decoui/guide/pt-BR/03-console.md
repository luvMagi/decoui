# Saída e Logs

Tudo o que uma ferramenta imprime (print) ou registra em log aparece no console de saída abaixo do formulário, em tempo real, enquanto ela está em execução. Os níveis de log são codificados por cores, e a saída comum do ``print`` é exibida com uma cor própria para permanecer distinguível do log.

* ``Copiar`` (``Copy``): copia todo o conteúdo do console para a área de transferência.
* ``Ver Log`` (``View Log``): abre a saída da execução em uma janela separada e redimensionável.

A janela de log é a opção ideal quando há um grande volume de saída. Ela adiciona os seguintes recursos:

* Um botão de alternância por nível — desative ``DEBUG`` para ver apenas o que é importante, ou selecione ``Nenhum`` (``None``) e depois ``ERROR`` para ver apenas as falhas.
* Uma caixa de pesquisa que filtra as linhas correspondentes.
* ``Copiar tudo`` (``Copy All``).

A filtragem na janela de log nunca interfere no console da página de origem; a janela mantém sua própria cópia das linhas.

A saída de cada execução é armazenada, permitindo que o mesmo log seja reaberto posteriormente a partir do histórico, muito tempo depois de a aba ter sido fechada.
