# Changelog

## [2.1.8] - 2026-10-27

### Segurança

- Validação de esquema de URL (`http://` e `https://`) no instalador visual (`setup_gui.py`) antes de abrir links externos com `os.startfile` ou `webbrowser.open`.
- Verificação contra links simbólicos nos scripts e executáveis do instalador (`setup.ps1` e atalho launcher) para prevenir a execução de scripts arbitrários via symlink hijacking.

## [2.1.7] - 2026-10-26

Esta publicação reúne as melhorias incorporadas desde a última versão distribuída, a 2.1.0, incluindo as correções posteriores à preparação da 2.1.6.

### Segurança e integridade

- Gravações e cópias de arquivos usam substituição atômica, com testes de preservação dos dados originais quando uma operação falha.
- Movimentações de diretórios verificam a identidade da origem e removem o destino inválido quando detectam uma troca por link simbólico durante a operação.
- A rotação de logs verifica o tamanho pelo descritor do arquivo aberto e substitui o backup de forma atômica.
- Leitura de arquivos rejeita travessia de diretórios; a leitura do resultado do instalador tem limite de tamanho.
- Dependência Pillow atualizada para 13.0.0. Os instaladores passam a exigir Python 3.11 ou superior.

### Desempenho e interface

- Busca de transcrições e descoberta de sessões reduzem operações de disco e criação repetida de objetos de caminho.
- Comparação de conversas reutiliza a resolução de caminhos.
- Botões e rótulos clicáveis oferecem retorno visual mais claro; ações assíncronas exibem seu estado e protegem operações em andamento contra o fechamento da janela.

### Distribuição

- Pacotes Windows e macOS gerados do mesmo commit, com manifesto, hashes e aliases estáveis de download.
- Verificação semanal das alterações relevantes já integradas à `main`, com publicação condicionada à validação completa do aplicativo e dos pacotes.

## [2.1.6] - 2026-10-21

### Security
- Upgraded Pillow to 13.0.0 resolving 10 CVEs (including AIKIDO-2026-455429, CVE-2026-112403, and related buffer overflow vulnerabilities).
- Raised minimum supported Python runtime requirement to Python 3.11+ across installer scripts, documentation, and CI matrices.

## [2.1.5] - 2026-10-21

### Security
- Fixed TOCTOU symlink attack vector in appending logs mechanism on Windows by replacing `os.open` with a secure atomic file write pattern using `tempfile.mkstemp` and `os.replace`.

## [2.1.4] - 2026-09-24

### UX
- Melhorias na interface de usuário durante ações de carregamento, prevenindo encerramentos forçados (WM_DELETE_WINDOW) durante ações críticas e mostrando textos de estado mais claros em botões.

## [2.1.3] - 2026-09-24

### Security
- Hardened directory move/rename operations against TOCTOU symlink hijacking.

## [2.1.2] - 2026-09-22

### Performance
- Improved session loading performance by avoiding O(N) `pathlib.Path` instantiations during deep directory traversal, speeding up operations on machines with thousands of Claude Code project instances.

## [2.1.1] - 2026-09-21

### Security
- Mitigates Time-of-Check to Time-of-Use (TOCTOU) file write vulnerabilities during directory copying by injecting an atomic file copy function into `shutil.copytree` invocations in the backend.

## [2.1.0] - 2026-09-21

Esta versão reúne as correções e melhorias incorporadas depois da 2.0.0 e estabelece a publicação verificável de pacotes para Windows e macOS.

### Aplicativo

- Melhorias no tratamento de caminhos, links simbólicos, permissões e limites de leitura de arquivos locais.
- Otimizações na descoberta de sessões, leitura de metadados e comparação de cópias.
- Ajustes de estados de carregamento, botões e mensagens da interface.
- Resolução de executáveis do macOS independente das convenções de caminhos do Windows, com validação de nomes e sem consulta ao PATH do usuário.
- Teste de backup exercitando a criação real do ZIP e as permissões correspondentes, sem simular outro sistema por meio de os.name.
- Cenário de descoberta de perfis com datas de arquivos e pastas determinísticas em todos os sistemas e versões de Python testados.

### Distribuição

- Validação em Windows e macOS, incluindo macOS Intel e Apple Silicon.
- Pacotes por sistema gerados apenas a partir dos arquivos permitidos do commit marcado pela tag.
- Arquivo RELEASE.json dentro de cada ZIP, manifesto de distribuição e SHA256SUMS.txt.
- Nomes versionados e aliases estáveis para os downloads da última release.
- Publicação automática por tag, com verificação dos assets antes de publicar o rascunho e dos downloads depois da publicação.
- Guias visuais e apresentação do projeto no GitHub Pages.

### Atualização

Extraia o pacote do seu sistema em uma pasta nova e execute o setup correspondente. Preserve a instalação anterior e seus backups até conferir a nova. Não transporte o ambiente .app/venv nem publique arquivos de contas, sessões, logs ou backups.

As operações continuam locais ao mesmo computador. Encerre o Claude Desktop antes de vincular ou remover sessões. A comparação não mescla conversas divergentes.

## [2.0.0] - 2026-07-14

Versão anterior, preservada em sua tag e nos pacotes originais. Consulte as notas históricas no GitHub Releases.
