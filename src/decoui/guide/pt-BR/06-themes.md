# Temas

O botão de engrenagem no canto superior direito abre as Configurações, que lista todos os temas disponíveis e inicia com o tema atualmente em vigor selecionado.

Os temas são aplicados uma única vez, quando o aplicativo é iniciado, de modo que qualquer alteração entra em vigor na **próxima** vez em que for executado. Nada na janela aberta é alterado quando a caixa de diálogo é fechada; a própria caixa de diálogo avisa sobre isso antes de você fazer a escolha.

O decoui vem com 4 temas integrados: um tema claro padrão e três temas com estilo de painel.

Seus temas personalizados são lidos de ``~/.decoui/themes`` — um arquivo JSON para cada tema, sem necessidade de código Python. Um arquivo de tema define suas cores, raios de canto e fontes; a maneira mais simples de criar um é começar a partir de um tema integrado usando ``extends`` e sobrescrever apenas o que você deseja alterar.

Como o tema é apenas uma configuração de apresentação, um arquivo com defeito nunca é fatal: um arquivo ilegível é ignorado e todos os outros temas continuam carregando normalmente, e uma seleção que não puder ser resolvida reverte para o tema claro padrão. Em ambos os casos, um aviso é exibido quando o aplicativo é iniciado.

Sua escolha é armazenada por ID, portanto, renomear um tema não faz com que ele seja perdido, e um tema temporariamente ausente não é desmarcado — ele voltará a ser aplicado assim que o arquivo estiver disponível novamente.
