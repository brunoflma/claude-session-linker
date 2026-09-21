# Guias do Claude Session Linker

As formas de instalar, iniciar, fechar o Claude Desktop e recuperar o ambiente são diferentes em cada sistema operacional. Use apenas o guia correspondente ao computador onde o Session Linker será executado.

Comece pela [última release](https://github.com/brunoflma/claude-session-linker/releases/latest) e escolha o ZIP do seu sistema. Extraia todo o conteúdo, inclusive a pasta `.app`. Cada pacote inclui a versão e o commit de origem em `RELEASE.json`.

## Windows

Escolha o pacote com sufixo `-windows.zip` e use o iniciador de setup `.vbs`.

[Abrir o guia visual para Windows](https://brunoflma.github.io/claude-session-linker/install-windows.html) · [Referência em Markdown](GUIA-WINDOWS.md)

## macOS

Escolha o pacote com sufixo `-macos.zip` e use o iniciador de setup `.command`.

[Abrir o guia visual para macOS](https://brunoflma.github.io/claude-session-linker/install-macos.html) · [Referência em Markdown](GUIA-MACOS.md)

## Informações comuns

Nos dois sistemas, o aplicativo:

- funciona somente com dados locais do Claude Desktop;
- exige que cada conta tenha sido usada ao menos uma vez no computador;
- deve ser usado com o Claude Desktop completamente fechado ao vincular ou remover sessões;
- cria backups em `.app/backups` antes de alterar dados locais.

Para uma visão geral do projeto, consulte o [README](README.md).
