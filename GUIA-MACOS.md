# Guia do Claude Session Linker para macOS

Este guia é exclusivo para macOS.

## 1. Pré-requisitos

- Claude Desktop instalado.
- Pelo menos duas contas Claude já usadas nesse Mac.
- Python 3.10 ou superior, com `tkinter`.
- Homebrew quando o Python encontrado não inclui `tkinter`.

O setup instala `customtkinter`, `darkdetect` e `pillow` automaticamente em um ambiente isolado.

O primeiro setup precisa de acesso à internet para baixar dependências. Se necessário, instale o [Python para macOS](https://www.python.org/downloads/macos/) ou o [Homebrew](https://brew.sh/).

## 2. Baixar e instalar

1. Abra a [release mais recente](https://github.com/brunoflma/claude-session-linker/releases/latest).
2. Baixe `claude-session-linker-<versão>-macos.zip`.
3. Extraia todo o conteúdo para uma pasta permanente, por exemplo `~/Documents/Claude Session Linker`.
4. Clique com o botão direito em `00 - Setup Claude Session Linker.command` e escolha **Abrir**.
5. Se o Gatekeeper bloquear o arquivo, abra **Ajustes do Sistema → Privacidade e Segurança** e escolha **Abrir Assim Mesmo**.
6. Acompanhe o progresso na janela do Terminal.
7. Ao terminar, pressione Enter para iniciar o aplicativo ou abra `Claude Session Linker.command`.

O setup cria `.app/venv` e registra o resultado em `.app/logs/setup-result.txt`. Não é necessário usar `sudo`.

## 3. Preparar as contas do Claude Desktop

1. Abra o Claude Desktop.
2. Entre em cada conta que deseja usar com o Session Linker.
3. Em cada conta, abra pelo menos uma vez a aba `Code` ou `Cowork`.
4. Feche completamente o Claude Desktop com `Cmd+Q`. Fechar apenas a janela não encerra o aplicativo.

## 4. Vincular uma sessão

1. Abra `Claude Session Linker.command`.
2. Escolha a aba `Code` ou `Cowork`.
3. Localize a sessão na conta de origem.
4. Clique em `Vincular conta`.
5. Escolha a conta de destino.
6. Reabra o Claude Desktop na conta de destino.

Em `Code`, um novo vínculo copia o índice e clona o transcript local para que as contas possam continuar a conversa de forma independente. Em `Cowork`, o índice e a pasta local da conversa são copiados.

## 5. Comparar e remover

- `Comparar`: mostra qual cópia tem mais mensagens ou atividade mais recente.
- `Remover`: apaga a sessão somente da conta selecionada, depois de criar um backup.

Em `Code`, a remoção apaga apenas o índice daquela conta. Em `Cowork`, remove o índice e a pasta local correspondente.

## 6. Perfis Claude detectados

O Session Linker procura raízes válidas em:

- `~/Library/Application Support/Claude`
- `~/Library/Application Support/Claude*`, incluindo `Claude-3p`

Os transcripts de `Code` ficam em `~/.claude/projects`.

Para limitar uma execução a um perfil específico, abra o Terminal na pasta do projeto e rode:

```bash
export CLAUDE_SESSION_LINKER_CLAUDE_DIR="$HOME/Library/Application Support/Claude-3p"
bash "Claude Session Linker.command"
```

## 7. Backups e dados locais

Os backups ficam em `.app/backups`.

- Sessões `Code`: backup da pasta de índices que será alterada.
- Sessões `Cowork`: backup do workspace de destino.

O aplicativo não envia sessões, mensagens, tokens ou dados de contas para servidores externos.

## 8. Solução de problemas

### O Gatekeeper bloqueou o arquivo

Use botão direito → **Abrir**. Se ainda houver bloqueio, confirme em **Ajustes do Sistema → Privacidade e Segurança → Abrir Assim Mesmo**.

### O arquivo `.command` não abre

Abra o Terminal na pasta do projeto e restaure as permissões executáveis:

```bash
chmod +x "00 - Setup Claude Session Linker.command" "Claude Session Linker.command" ".app/setup.sh"
```

Depois execute:

```bash
bash "00 - Setup Claude Session Linker.command"
```

### Python ou tkinter não foi encontrado

Instale o Homebrew, se necessário, e rode novamente o setup. O script tenta instalar a fórmula `python-tk` compatível com o Python detectado.

### O ambiente Python está corrompido

Recrie `.app/venv` pelo Terminal:

```bash
bash ".app/setup.sh" --recreate-venv
```

Para manter o Terminal aberto e ver o resultado:

```bash
bash ".app/setup.sh" --recreate-venv --pause-on-exit
```

### O setup falhou

Consulte `.app/logs/setup-result.txt`. Se o setup terminar, mas o aplicativo falhar ao abrir, consulte também `.app/logs/session-linker-error.log`. Se houver erro de permissão, mova o projeto para uma pasta gravável do usuário, como `~/Documents`, e rode o setup novamente. Não use `sudo` para contornar o problema.

### A conta de destino não aparece

Abra o Claude Desktop nessa conta e acesse a aba correspondente (`Code` ou `Cowork`) pelo menos uma vez.

### A sessão vinculada não aparece

Encerre o Claude Desktop com `Cmd+Q` e abra novamente na conta de destino.

## 9. Atualizar

Baixe o novo ZIP do macOS, extraia em uma pasta nova e execute `00 - Setup Claude Session Linker.command`. Se quiser preservar backups antigos, copie somente `.app/backups` da instalação anterior. Não reutilize `.app/venv`, `.app/logs` nem arquivos de dados de contas e sessões.

Se o problema continuar, abra uma [issue](https://github.com/brunoflma/claude-session-linker/issues) informando a versão do macOS e o erro observado. Antes de anexar `setup-result.txt` ou `session-linker-error.log`, remova caminhos, nomes de conta e qualquer conteúdo de sessão.

[Voltar ao índice de guias](GUIA.md)
