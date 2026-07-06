# Claude Session Linker

Interface local para visualizar, vincular, comparar e remover sessões do Claude Desktop entre contas diferentes no mesmo computador.

Versão atual: 1.5.

## O que a ferramenta faz

- Lista sessões locais do Claude Desktop na aba Code.
- Lista sessões locais do Cowork / Agent Mode.
- Vincula uma sessão de uma conta Claude para outra conta Claude no mesmo Windows.
- Remove uma sessão de uma conta quando você não quer mais mantê-la naquela conta.
- Mostra a origem e o rastreamento de vínculos entre contas.
- Compara sessões vinculadas para indicar qual conversa tem mais mensagens ou atividade mais recente.
- Cria backups antes de escrever nas pastas locais do Claude Desktop.

## Pré-requisitos

Obrigatórios:

- Windows 10 ou 11.
- Claude Desktop instalado.
- Perfis alternativos do Claude Desktop, como `Claude-3p`, também são detectados quando ficam em `%LOCALAPPDATA%`.
- Pelo menos duas contas Claude já usadas no Claude Desktop neste computador.
- Python 3.10 ou superior.
- PowerShell, já incluído no Windows.

Instalados automaticamente pelo setup:

- `customtkinter`
- `darkdetect`
- `pillow`

Não é necessário:

- Node.js.
- npm.
- Banco de dados.
- Chave de API.
- Servidor local.

## Instalação rápida

1. Baixe o arquivo `.zip` da versão mais recente em Releases.
2. Extraia a pasta em um local permanente, por exemplo `C:\Users\<voce>\.claude\Claude Session Linker`.
3. Dê duplo clique em `00 - Setup Claude Session Linker.vbs`.
4. Quando o setup terminar, abra com duplo clique em `Claude Session Linker.vbs`.

O setup cria o ambiente Python isolado em `.app\venv` e instala as dependências automaticamente.

Para instalação por Git, clone o repositório e rode o mesmo `00 - Setup Claude Session Linker.vbs`.

## Como usar

1. Abra o Claude Desktop e use cada conta pelo menos uma vez para que as pastas locais sejam criadas.
2. Feche o Claude Desktop completamente pela bandeja do sistema antes de vincular sessões.
3. Abra o Claude Session Linker.
4. Escolha a aba `Code` ou `Cowork`.
5. Clique em `Vincular conta` na sessão desejada.
6. Escolha a conta de destino.
7. Reabra o Claude Desktop logado na conta de destino.

Para comparar progresso entre contas, clique em `Comparar`. Quando existir uma sessão vinculada correspondente, a comparação abre direto nela.

Para remover uma sessão apenas de uma conta, clique em `Remover`. O app cria backup antes de apagar. Em sessões Code, só o índice daquela conta é removido; o transcript compartilhado em `.claude\projects` é preservado. Em sessões Cowork, o índice e a pasta local de dados daquela sessão são removidos da conta selecionada.

## Segurança e privacidade

Esta ferramenta roda somente no seu computador.

Ela não envia sessões, mensagens, tokens, caminhos locais ou dados de contas para servidores externos. As alterações são feitas em arquivos locais do Claude Desktop.

Arquivos locais que podem conter dados privados ficam ignorados pelo Git:

- `.app/account_labels.json`
- `.app/session_links.json`
- `.app/backups/`
- `.app/logs/`
- `.app/venv/`
- `.claude/`
- `.conversation-esaa/`
- `.grok/`

## Backups

Antes de vincular sessões, o app cria backups em `.app\backups`.

- Para sessões Code, o backup cobre a pasta local de índices de sessões Code.
- Para sessões Cowork, o backup cobre o workspace de destino, evitando copiar árvores muito grandes sem necessidade.
- Antes de remover sessões, o app também cria backup do escopo que será alterado.

## Limitações

- O formato de armazenamento do Claude Desktop não é uma API pública e pode mudar.
- A ferramenta copia e registra vínculos; ela não mescla conversas divergentes.
- A comparação conta mensagens e última atividade a partir dos arquivos locais disponíveis no computador.

## Solução de problemas

### Python não encontrado

Instale Python 3.10 ou superior em [python.org](https://www.python.org/downloads/) e execute novamente `00 - Setup Claude Session Linker.vbs`.

### A conta de destino não aparece

Abra o Claude Desktop logado nessa conta pelo menos uma vez e acesse a aba correspondente (`Code` ou `Cowork`) para que o Claude crie as pastas locais.

### Limitar a um perfil Claude específico

Por padrão, o Session Linker carrega todas as raízes locais válidas do Claude entre `%APPDATA%\Claude` e perfis `%LOCALAPPDATA%\Claude*`, como `%LOCALAPPDATA%\Claude-3p`. Assim as contas oficiais e o Claude 3p aparecem na mesma lista.

Para limitar a ferramenta a uma raiz específica nesta execução:

```powershell
$env:CLAUDE_SESSION_LINKER_CLAUDE_DIR = "$env:LOCALAPPDATA\Claude-3p"
wscript "Claude Session Linker.vbs"
```

### A sessão não aparece no Claude Desktop depois do vínculo

Feche o Claude Desktop completamente pela bandeja do sistema e abra novamente logado na conta de destino.

### O setup falhou

Veja o arquivo:

```text
.app\logs\setup-result.txt
```

Depois rode o setup novamente.

Se o erro indicar falta de permissão para gravar em `.app`, mova a pasta extraída para um local gravável do seu usuário e rode o setup de novo.

### Setup manual por PowerShell

O caminho recomendado é o VBS. Se precisar diagnosticar manualmente, abra o PowerShell na pasta do projeto e rode:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .app\setup.ps1
```

Adicione `-PauseOnExit` no final do comando se quiser manter a janela aberta após o setup.

## Desenvolvimento

Rodar testes:

```powershell
.app\venv\Scripts\python.exe .app\test_session_linker.py
```

Verificar sintaxe:

```powershell
.app\venv\Scripts\python.exe -m py_compile .app\session_linker.py .app\test_session_linker.py
```

## Guia

Veja [GUIA.md](GUIA.md) para o passo a passo de instalação, uso diário e recuperação.

## Aviso

Este projeto não é uma ferramenta oficial da Anthropic ou do Claude. Use por sua conta e mantenha backups dos dados locais importantes.
