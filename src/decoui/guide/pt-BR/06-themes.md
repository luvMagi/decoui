# Temas

O botão de engrenagem no canto superior direito abre as Configurações, que lista todos os temas disponíveis e inicia com o tema atualmente em vigor selecionado.

Themes are applied at once. Choosing one restyles every window that is open,
without rebuilding anything: a tool that is running goes on running, forms keep
what was typed into them, and output already printed is re-inked in the new
colours. The console's scroll position is the one casualty -- it returns to the
newest line.

The **language**, chosen in the same dialog, is the exception: it takes effect
the next time the application runs. Text is read as each widget is built, in far
more places than colour is, and there is nothing that can catch the rest the way
the stylesheet catches colour.

O decoui vem com 4 temas integrados: um tema claro padrão e três temas com estilo de painel.

Seus temas personalizados são lidos de ``~/.decoui/themes`` — um arquivo JSON para cada tema, sem necessidade de código Python. Um arquivo de tema define suas cores, raios de canto e fontes; a maneira mais simples de criar um é começar a partir de um tema integrado usando ``extends`` e sobrescrever apenas o que você deseja alterar.

Como o tema é apenas uma configuração de apresentação, um arquivo com defeito nunca é fatal: um arquivo ilegível é ignorado e todos os outros temas continuam carregando normalmente, e uma seleção que não puder ser resolvida reverte para o tema claro padrão. Em ambos os casos, um aviso é exibido quando o aplicativo é iniciado.

Sua escolha é armazenada por ID, portanto, renomear um tema não faz com que ele seja perdido, e um tema temporariamente ausente não é desmarcado — ele voltará a ser aplicado assim que o arquivo estiver disponível novamente.
