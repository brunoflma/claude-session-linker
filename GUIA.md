# Guia do Claude Session Linker

Este guia cobre o fluxo normal para instalar e usar o Claude Session Linker no Windows e no macOS.

## Instalar

1. Baixe o `.zip` da versão mais recente em Releases.
2. Extraia a pasta em um local permanente. Não execute de dentro do visualizador de zip do Windows.
3. Dê duplo clique em `00 - Setup Claude Session Linker.vbs`.
4. Acompanhe o progresso na janela de configuração.
5. Ao final, escolha abrir o aplicativo ou dê duplo clique em `Claude Session Linker.vbs`.

O setup não precisa de administrador. Ele cria `.app\venv`, instala `customtkinter`, `darkdetect` e `pillow`, mostra o progresso ao vivo e grava o resultado em `.app\logs\setup-result.txt`.

## Preparar o Claude Desktop

1. Abra o Claude Desktop.
2. Entre em cada conta que você quer usar com o Session Linker.
3. Em cada conta, abra pelo menos uma vez a aba `Code` ou `Cowork`.
4. Feche o Claude Desktop pela bandeja do sistema antes de vincular ou remover sessões.

## Vincular sessão

1. Abra `Claude Session Linker.vbs`.
2. Escolha a aba `Code` ou `Cowork`.
3. Localize a sessão na conta de origem.
4. Clique em `Vincular conta`.
5. Escolha a conta de destino.
6. Reabra o Claude Desktop logado na conta de destino.

Para sessões `Code`, o app copia o índice local e mantém o transcript compartilhado em `.claude\projects`. Para sessões `Cowork`, o app copia também a pasta local da conversa.

## Comparar sessão

Use `Comparar` para ver qual cópia tem mais mensagens ou atividade mais recente. Isso ajuda quando a mesma conversa aparece em mais de uma conta.

## Remover sessão de uma conta

Use `Remover` quando uma sessão não deve mais aparecer em uma conta específica.

O app cria backup antes de apagar. Em `Code`, remove apenas o índice daquela conta. Em `Cowork`, remove o índice e a pasta local da sessão naquela conta.

## Perfis Claude alternativos

O Claude Session Linker detecta mais de uma raiz local do Claude, incluindo `%APPDATA%\Claude`, perfis em `%LOCALAPPDATA%\Claude*`, como `%LOCALAPPDATA%\Claude-3p`, e instalações Microsoft Store/MSIX em `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude`.

Para limitar a execução a uma raiz específica:

```powershell
$env:CLAUDE_SESSION_LINKER_CLAUDE_DIR = "$env:LOCALAPPDATA\Claude-3p"
wscript "Claude Session Linker.vbs"
```

## Recuperar de problema

Backups ficam em `.app\backups`.

Se o setup falhar, use `Tentar novamente` na janela de configuração. O resultado também fica em `.app\logs\setup-result.txt`.

Se o erro indicar falta de permissão para gravar em `.app`, mova a pasta do projeto para um local gravável do seu usuário e rode o setup de novo.

Se uma sessão vinculada não aparecer no Claude Desktop, feche o Claude Desktop completamente pela bandeja do sistema e abra novamente na conta de destino.

## Instalar no macOS

### Instalar

1. Clone ou baixe o projeto em um local permanente, por exemplo dentro de `~/Documents`.
2. Dê duplo clique em `00 - Setup Claude Session Linker.command`.
   - No primeiro uso, o Gatekeeper do macOS pode bloquear o arquivo por ele não ser assinado. Clique com o botão direito no arquivo → **Abrir**, ou libere em **Ajustes do Sistema → Privacidade e Segurança → Abrir Assim Mesmo**.
3. O duplo clique abre uma janela de Terminal e mostra o progresso do setup ali. O setup procura um Python 3.10 ou superior já instalado, usa o Homebrew (https://brew.sh) para instalar o `python-tk` automaticamente caso o `tkinter` esteja faltando, cria o ambiente isolado em `.app/venv` e instala `customtkinter`, `darkdetect` e `pillow`.
4. Ao final, pressione Enter no Terminal para abrir o aplicativo automaticamente, ou dê duplo clique em `Claude Session Linker.command`.

O setup não precisa de administrador. O resultado também fica registrado em `.app/logs/setup-result.txt`.

Se uma nova tentativa continuar falhando por causa do ambiente Python existente, abra o Terminal na pasta do projeto e execute `bash ".app/setup.sh" --recreate-venv` para recriar `.app/venv`.

### Preparar o Claude Desktop

1. Abra o Claude Desktop.
2. Entre em cada conta que você quer usar com o Session Linker.
3. Em cada conta, abra pelo menos uma vez a aba `Code` ou `Cowork`.
4. Feche o Claude Desktop completamente (Cmd+Q, não só a janela) antes de vincular ou remover sessões.

### Vincular, comparar e remover sessão

1. Dê duplo clique em `Claude Session Linker.command`.
2. Escolha a aba `Code` ou `Cowork`.
3. Localize a sessão na conta de origem.
4. Clique em `Vincular conta`, escolha a conta de destino e depois reabra o Claude Desktop logado nela.
5. Clique em `Comparar` para ver qual cópia tem mais mensagens ou atividade mais recente entre contas.
6. Clique em `Remover` para apagar uma sessão apenas de uma conta. O app cria backup antes de remover; em sessões `Code` só o índice daquela conta é removido, o transcript em `~/.claude/projects` é preservado, e em sessões `Cowork` o índice e a pasta local daquela sessão são removidos da conta selecionada.

### Perfis Claude alternativos no macOS

O Claude Session Linker detecta `~/Library/Application Support/Claude` e qualquer perfil alternativo que combine com `Claude*` na mesma pasta, como `~/Library/Application Support/Claude-3p`. Os transcripts ficam em `~/.claude/projects`, a mesma pasta usada no Windows.

Para limitar a execução a uma raiz específica, abra o Terminal na pasta do projeto e rode:

```bash
export CLAUDE_SESSION_LINKER_CLAUDE_DIR="$HOME/Library/Application Support/Claude-3p"
bash "Claude Session Linker.command"
```

### Recuperar de problema no macOS

Backups ficam em `.app/backups`.

Se o setup falhar, dê duplo clique novamente em `00 - Setup Claude Session Linker.command`. O resultado também fica em `.app/logs/setup-result.txt`.

Se o Gatekeeper continuar bloqueando o arquivo depois do clique com o botão direito → Abrir, confirme em **Ajustes do Sistema → Privacidade e Segurança → Abrir Assim Mesmo**.

Se o erro indicar falta de permissão para gravar em `.app`, mova a pasta do projeto para um local gravável do seu usuário (por exemplo dentro de `~/Documents`) e rode o setup de novo.

Se uma sessão vinculada não aparecer no Claude Desktop, feche o Claude Desktop completamente (Cmd+Q) e abra novamente na conta de destino.
