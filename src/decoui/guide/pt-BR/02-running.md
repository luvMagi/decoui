# Executando uma Ferramenta

O formulário de uma ferramenta é construído a partir dos parâmetros declarados por sua função, de modo que os campos correspondem exatamente ao que aquela ferramenta específica necessita.

* Um campo marcado com um asterisco vermelho (*) é obrigatório e não possui valor padrão.
* ``Parâmetros`` (``Parameters``) recolhe o formulário depois de preenchido, para dar mais espaço à área de saída.
* ``Executar`` (``Run``) inicia a ferramenta. Enquanto ela estiver em execução, o botão ``Executar`` é substituído por ``Parar`` (``Stop``).
* ``Redefinir`` (``Reset``) restaura todos os campos para seus valores padrão declarados.

Algumas ferramentas solicitam confirmação antes de iniciar; isso é declarado pela própria ferramenta, não sendo uma decisão do aplicativo.

``Parar`` interrompe uma ferramenta em execução. Uma ferramenta que está apenas realizando cálculos ou em espera (sleep) para imediatamente. Aquela que está aguardando um programa externo só para se seu autor tiver implementado uma rotina de limpeza para esse caso — caso contrário, a página retorna ao estado ocioso enquanto o programa externo continua em execução.

A barra de progresso oscila de um lado para o outro quando a ferramenta não informou a quantidade total de trabalho, e exibe uma porcentagem real quando essa informação foi fornecida.

Depois que uma execução termina, há três coisas a fazer com o que ela retornou:

* ``Copiar resultado`` coloca o valor na área de transferência.
* ``Enviar resultado`` preenche com ele o campo de outra ferramenta, abrindo
  essa ferramenta e trazendo-a para a frente. Só aparece quando outra
  ferramenta declara aceitar esse tipo de valor, e sobrescreve o que estava no
  campo.
* A aplicação também pode ter pedido que o valor seja impresso no console de
  saída -- veja a próxima página.

Os dois botões mostram o valor na dica de tela e permanecem desabilitados até
que uma execução retorne algo.
