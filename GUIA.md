# Guia do Claude Session Linker

Este guia cobre o fluxo normal para instalar e usar o Claude Session Linker 1.5 no Windows.

## Instalar

1. Baixe o `.zip` da versão mais recente em Releases.
2. Extraia a pasta em um local permanente. Não execute de dentro do visualizador de zip do Windows.
3. Dê duplo clique em `00 - Setup Claude Session Linker.vbs`.
4. Se o Windows perguntar, permita a execução do script local.
5. Ao final, escolha abrir o aplicativo ou dê duplo clique em `Claude Session Linker.vbs`.

O setup não precisa de administrador. Ele cria `.app\venv`, instala `customtkinter`, `darkdetect` e `pillow`, e grava o resultado em `.app\logs\setup-result.txt`.

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

A versão 1.5 detecta mais de uma raiz local do Claude, incluindo `%APPDATA%\Claude` e perfis em `%LOCALAPPDATA%\Claude*`, como `%LOCALAPPDATA%\Claude-3p`.

Para limitar a execução a uma raiz específica:

```powershell
$env:CLAUDE_SESSION_LINKER_CLAUDE_DIR = "$env:LOCALAPPDATA\Claude-3p"
wscript "Claude Session Linker.vbs"
```

## Recuperar de problema

Backups ficam em `.app\backups`.

Se o setup falhar, veja `.app\logs\setup-result.txt` e rode `00 - Setup Claude Session Linker.vbs` novamente.

Se o erro indicar falta de permissão para gravar em `.app`, mova a pasta do projeto para um local gravável do seu usuário e rode o setup de novo.

Se uma sessão vinculada não aparecer no Claude Desktop, feche o Claude Desktop completamente pela bandeja do sistema e abra novamente na conta de destino.
