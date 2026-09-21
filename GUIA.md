# Guias do Claude Session Linker

As formas de instalar, iniciar, fechar o Claude Desktop e recuperar o ambiente são diferentes em cada sistema operacional. Use apenas o guia correspondente ao computador onde o Session Linker será executado.

Comece pelo [código atual da branch master](https://github.com/brunoflma/claude-session-linker/archive/refs/heads/master.zip). Esse ZIP contém os iniciadores dos dois sistemas; extraia todo o conteúdo, inclusive a pasta `.app`. Confira no [README](README.md#comece-pelo-seu-sistema) a distinção entre o código atual e os pacotes de releases.

## Windows

Use o iniciador de setup `.vbs` do código atual. Se optar por uma release específica, escolha o pacote com sufixo `-windows.zip`.

[Abrir o Guia do Claude Session Linker para Windows](GUIA-WINDOWS.md)

## macOS

Use o iniciador de setup `.command` do código atual. Se optar por uma release específica, escolha o pacote com sufixo `-macos.zip`.

[Abrir o Guia do Claude Session Linker para macOS](GUIA-MACOS.md)

## Informações comuns

Nos dois sistemas, o aplicativo:

- funciona somente com dados locais do Claude Desktop;
- exige que cada conta tenha sido usada ao menos uma vez no computador;
- deve ser usado com o Claude Desktop completamente fechado ao vincular ou remover sessões;
- cria backups em `.app/backups` antes de alterar dados locais.

Para uma visão geral do projeto, consulte o [README](README.md).
