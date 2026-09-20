<img src="docs/cover.svg" width="100%" alt="Claude Session Linker. Suas conversas organizadas entre contas locais.">

# Claude Session Linker

**Encontre, vincule e compare sessões do Claude Desktop entre contas no mesmo computador.**

Uma interface local para organizar as conversas das abas **Code** e **Cowork**. Você escolhe a sessão e a conta de destino, compara as cópias disponíveis e mantém backups antes das alterações.

**[Baixar a versão mais recente ↗](https://github.com/brunoflma/claude-session-linker/releases/latest)** · [Windows](GUIA-WINDOWS.md) · [macOS](GUIA-MACOS.md) · [Todos os guias](GUIA.md)

## Quando ele ajuda

| Situação | Recurso |
| :--- | :--- |
| Uma conversa ficou em outra conta usada neste computador | Localize e vincule a sessão à conta de destino. |
| Existem cópias da mesma conversa | Compare a quantidade de mensagens e a atividade mais recente. |
| Você quer continuar uma sessão Code de forma independente | O vínculo cria uma cópia do transcript. |
| Uma sessão precisa sair de uma conta específica | Remova apenas da conta escolhida, com backup prévio. |

## Comece pelo seu sistema

| Sistema | Arquivo na release | Passo a passo |
| :--- | :--- | :--- |
| Windows 10/11 | `claude-session-linker-<versão>-windows.zip` | [Guia para Windows](GUIA-WINDOWS.md) |
| macOS | `claude-session-linker-<versão>-macos.zip` | [Guia para macOS](GUIA-MACOS.md) |

1. Baixe o ZIP na [release mais recente](https://github.com/brunoflma/claude-session-linker/releases/latest).
2. Extraia o pacote em uma pasta permanente.
3. Siga o guia do seu sistema para instalar e abrir a ferramenta.

## O fluxo de uso

1. Use cada conta no Claude Desktop pelo menos uma vez.
2. Abra a aba Code ou Cowork em cada conta para criar as pastas correspondentes.
3. **Feche completamente o Claude Desktop** antes de vincular ou remover sessões.
4. Abra o Linker, escolha Code ou Cowork e selecione a operação.
5. Reabra o Claude Desktop na conta de destino para atualizar a barra lateral.

### Code e Cowork

- **Code:** o transcript é clonado ao criar um novo vínculo. Cada conta pode continuar a conversa de forma independente.
- **Cowork:** a ferramenta copia o índice e a pasta local da conversa.
- **Comparação:** usa os arquivos disponíveis no computador. Não mescla automaticamente conversas que divergiram.

## Requisitos

- Claude Desktop instalado e pelo menos duas contas já usadas no computador.
- Python **3.10 ou superior**.
- No Windows, PowerShell.
- No macOS, o Homebrew pode ser necessário para disponibilizar o `tkinter`.

O setup instala `customtkinter`, `darkdetect` e `pillow` em `.app/venv`. O uso normal não exige Node.js, banco de dados, servidor ou chave de API.

## Dados locais e recuperação

A ferramenta opera sobre os arquivos locais do Claude Desktop. As operações de sessão não enviam mensagens ou dados de contas a servidores externos. O setup acessa a internet para instalar dependências e, quando necessário no macOS, o `python-tk`.

Os backups ficam em `.app/backups`:

- **Code:** backup da pasta local de índices antes de escrever ou remover.
- **Cowork:** backup do workspace que será alterado.

Perfis e arquivos de sessão que sejam links simbólicos são ignorados ou recusados nas operações sensíveis. A ferramenta reconhece instalações oficiais, perfis alternativos como `Claude-3p` e instalações Windows Store/MSIX.

## Limites importantes

O armazenamento do Claude Desktop não é uma API pública e pode mudar entre versões. O Linker não transfere sessões entre computadores nem faz uma fusão de conversas divergentes. O pacote macOS utiliza scripts locais e não é um aplicativo assinado ou notarizado.

Este projeto é independente da Anthropic. Mantenha os backups e confira os [guias de instalação e recuperação](GUIA.md) antes de operar sobre sessões importantes.

## Ajuda e contribuições

[Relatar um problema](https://github.com/brunoflma/claude-session-linker/issues) · [Documentação](GUIA.md) · [Bruno Ferreira](https://github.com/brunoflma)

Ao abrir uma issue, informe sistema operacional, versão do Linker e tipo de sessão. Não anexe transcripts, credenciais, identificadores de contas ou arquivos de conversas.
