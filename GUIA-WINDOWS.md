# Guia do Claude Session Linker para Windows

Este guia é exclusivo para Windows 10 e Windows 11.

## 1. Pré-requisitos

- Claude Desktop instalado.
- Pelo menos duas contas Claude já usadas nesse computador.
- Python 3.10 ou superior.
- PowerShell, já incluído no Windows.

O setup instala `customtkinter`, `darkdetect` e `pillow` automaticamente em um ambiente isolado.

O primeiro setup precisa de acesso à internet para baixar as dependências Python.

## 2. Baixar e instalar

1. Abra a [release mais recente](https://github.com/brunoflma/claude-session-linker/releases/latest).
2. Baixe `claude-session-linker-<versão>-windows.zip`.
3. Extraia todo o conteúdo para uma pasta permanente, por exemplo:

   ```text
   C:\Users\<voce>\.claude\Claude Session Linker
   ```

4. Não execute o programa de dentro do visualizador de ZIP.
5. Dê duplo clique em `00 - Setup Claude Session Linker.vbs`.
6. Acompanhe a instalação na janela de configuração.
7. Ao terminar, abra o aplicativo pela própria janela ou dê duplo clique em `Claude Session Linker.vbs`.

O setup cria `.app\venv` e registra o resultado em `.app\logs\setup-result.txt`. Não é necessário executar como administrador.

## 3. Preparar as contas do Claude Desktop

1. Abra o Claude Desktop.
2. Entre em cada conta que deseja usar com o Session Linker.
3. Em cada conta, abra pelo menos uma vez a aba `Code` ou `Cowork`.
4. Feche o Claude Desktop completamente pela bandeja do sistema. Fechar apenas a janela não encerra necessariamente o processo.

## 4. Vincular uma sessão

1. Dê duplo clique em `Claude Session Linker.vbs`.
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

- `%APPDATA%\Claude`
- `%LOCALAPPDATA%\Claude*`, incluindo `%LOCALAPPDATA%\Claude-3p`
- `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude` para instalações Microsoft Store/MSIX

Para limitar uma execução a um perfil específico, abra o PowerShell na pasta do projeto e rode:

```powershell
$env:CLAUDE_SESSION_LINKER_CLAUDE_DIR = "$env:LOCALAPPDATA\Claude-3p"
wscript "Claude Session Linker.vbs"
```

## 7. Backups e dados locais

Os backups ficam em `.app\backups`.

- Sessões `Code`: backup da pasta de índices que será alterada.
- Sessões `Cowork`: backup do workspace de destino.

O aplicativo não envia sessões, mensagens, tokens ou dados de contas para servidores externos.

## 8. Solução de problemas

### Python não encontrado

Instale Python 3.10 ou superior pelo [python.org para Windows](https://www.python.org/downloads/windows/) e execute novamente `00 - Setup Claude Session Linker.vbs`.

### O setup falhou

Use `Tentar novamente` na janela de configuração e consulte:

```text
.app\logs\setup-result.txt
```

Se houver erro de permissão, mova a pasta extraída para um local gravável do seu usuário.

Para diagnóstico manual, abra o PowerShell na pasta do projeto e rode:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .app\setup.ps1
```

Adicione `-PauseOnExit` para manter a janela aberta ao final.

Para descartar um ambiente Python incompleto e recriá-lo:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .app\setup.ps1 -RecreateVenv -PauseOnExit
```

Se o setup terminar, mas o aplicativo falhar ao abrir, consulte também `.app\logs\session-linker-error.log`.

### A conta de destino não aparece

Abra o Claude Desktop nessa conta e acesse a aba correspondente (`Code` ou `Cowork`) pelo menos uma vez.

### A sessão vinculada não aparece

Encerre o Claude Desktop pela bandeja do sistema e abra novamente na conta de destino.

### O Windows bloqueou o arquivo

Confirme que o ZIP foi extraído por completo. Nas propriedades do ZIP ou do arquivo bloqueado, use `Desbloquear` quando essa opção estiver disponível e extraia novamente.

## 9. Atualizar

Baixe o novo ZIP do Windows, extraia em uma pasta nova e execute `00 - Setup Claude Session Linker.vbs`. Se quiser preservar backups antigos, copie somente `.app\backups` da instalação anterior. Não reutilize `.app\venv`, `.app\logs` nem arquivos de dados de contas e sessões.

Se o problema continuar, abra uma [issue](https://github.com/brunoflma/claude-session-linker/issues) informando a versão do Windows e o erro observado. Antes de anexar `setup-result.txt` ou `session-linker-error.log`, remova caminhos, nomes de conta e qualquer conteúdo de sessão.

[Voltar ao índice de guias](GUIA.md)
