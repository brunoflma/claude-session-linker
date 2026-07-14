# Claude Session Linker

Interface local para visualizar, vincular, comparar e remover sessões do Claude Desktop entre contas diferentes no mesmo computador.

Versão atual: 1.10.0.

Compatível com Windows 10/11 e macOS.

## Início rápido

1. Abra a [release mais recente](https://github.com/brunoflma/claude-session-linker/releases/latest).
2. Baixe o ZIP correspondente ao seu sistema operacional.
3. Extraia o ZIP em uma pasta permanente e siga o guia específico:

| Sistema | Pacote | Guia |
|---|---|---|
| Windows | `claude-session-linker-<versão>-windows.zip` | [Guia para Windows](GUIA-WINDOWS.md) |
| macOS | `claude-session-linker-<versão>-macos.zip` | [Guia para macOS](GUIA-MACOS.md) |

O [índice de guias](GUIA.md) ajuda a escolher a documentação correta.

## O que a ferramenta faz

- Lista sessões locais do Claude Desktop nas abas `Code` e `Cowork`.
- Vincula uma sessão de uma conta Claude a outra conta usada no mesmo computador.
- Em sessões `Code`, clona o transcript ao criar um novo vínculo, permitindo que as contas avancem de forma independente.
- Em sessões `Cowork`, copia o índice e a pasta local da conversa.
- Compara cópias vinculadas por quantidade de mensagens e atividade mais recente.
- Remove uma sessão somente da conta escolhida.
- Cria backups antes de alterar os arquivos locais do Claude Desktop.
- Detecta instalações oficiais, perfis alternativos como `Claude-3p` e, no Windows, instalações Microsoft Store/MSIX.

## Pré-requisitos

Comuns aos dois sistemas:

- Claude Desktop instalado.
- Pelo menos duas contas já usadas no Claude Desktop nesse computador.
- Python 3.10 ou superior.

Requisitos específicos:

- Windows: PowerShell, já incluído no sistema.
- macOS: Homebrew pode ser necessário para instalar o `tkinter` quando ele não estiver disponível no Python encontrado.

O setup instala automaticamente `customtkinter`, `darkdetect` e `pillow` em `.app/venv`. Não são necessários Node.js, npm, banco de dados, servidor local ou chave de API.

## Uso básico

1. Abra o Claude Desktop e use cada conta pelo menos uma vez.
2. Em cada conta, abra a aba `Code` ou `Cowork` para criar as pastas locais correspondentes.
3. Feche completamente o Claude Desktop antes de vincular ou remover sessões.
4. Abra o Claude Session Linker e escolha `Code` ou `Cowork`.
5. Use `Vincular conta`, `Comparar` ou `Remover` conforme necessário.
6. Reabra o Claude Desktop na conta de destino para atualizar a barra lateral.

Consulte as instruções de fechamento, instalação e recuperação específicas do seu sistema:

- [Windows](GUIA-WINDOWS.md)
- [macOS](GUIA-MACOS.md)

## Segurança, privacidade e backups

O Claude Session Linker funciona localmente. Ele não envia sessões, mensagens, tokens, caminhos ou dados de contas para servidores externos.

O primeiro setup acessa a internet somente para instalar as dependências Python e, no macOS, para instalar `python-tk` pelo Homebrew quando necessário.

Os backups ficam em `.app/backups`:

- `Code`: backup da pasta local de índices antes de escrever ou remover.
- `Cowork`: backup do workspace que será alterado.

Perfis e arquivos de sessão que sejam links simbólicos são ignorados ou recusados nas operações sensíveis.

## Limitações

- O formato de armazenamento do Claude Desktop não é uma API pública e pode mudar.
- A ferramenta não mescla conversas que divergiram entre contas.
- A comparação depende dos arquivos locais ainda disponíveis no computador.
- O pacote macOS usa scripts locais e não é um aplicativo assinado ou notarizado; o Gatekeeper pode exigir confirmação no primeiro uso.

## Documentação

- [Escolher o guia do sistema operacional](GUIA.md)
- [Instalação e uso no Windows](GUIA-WINDOWS.md)
- [Instalação e uso no macOS](GUIA-MACOS.md)

## Aviso

Este projeto não é uma ferramenta oficial da Anthropic ou do Claude. Use por sua conta e mantenha backups dos dados locais importantes.
