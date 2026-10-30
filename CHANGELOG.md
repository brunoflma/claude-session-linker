# Changelog

## [2.2.0] - 2026-10-30

### Interface

- Visual redesenhado: barra lateral escura com marca, seletor Code/Cowork segmentado e contas com avatar, área de trabalho clara com cartões mais compactos e uma única cor de destaque.
- Busca instantânea por título, pasta do projeto, conta ou ID (Ctrl+F; Esc limpa) e opção para ocultar sessões arquivadas, que agora aparecem marcadas.
- Lista paginada (40 sessões por vez), mantendo a janela leve em perfis com centenas de conversas.
- Datas relativas ("há 3 h", "ontem"), nome curto do projeto e caminho completo em dica de contexto; clique copia o caminho.
- Aviso de Claude Desktop aberto em faixa visível no topo, com botão para verificar novamente; atalho F5 para atualizar.
- Diálogos de vínculo, remoção, comparação e renomeação reorganizados, com mensagens de estado coloridas e textos mais claros.
- Botão para abrir a pasta de backups. Fontes nativas no Windows e no macOS; emojis removidos dos controles.
- Novo ícone: duas conversas ligadas sobre o mesmo terracota da interface, com versão simplificada para 16 a 32 px. O favicon do site acompanha o novo desenho.
- Instalador do Windows com a mesma identidade visual do aplicativo e lista de etapas que avança durante o setup.
- Títulos das sessões se ajustam à largura quando a janela é redimensionada; a lista volta ao topo ao trocar de conta, busca ou filtro.

### Correções

- Contas que já abriram Code ou Cowork, mas ainda não têm sessões, passam a aparecer e podem receber vínculos.
- Falha ao criar o backup de um vínculo Cowork não deixa mais o diálogo travado em "Aguarde...".
- Uma pasta Cowork residual de uma cópia interrompida não impede mais um novo vínculo.
- Revincular uma sessão Code a uma conta que já tem cópia independente informa que nada foi sobrescrito, em vez de relatar uma atualização.
- Erros em tarefas de segundo plano são registrados e exibidos; a lista não fica mais presa em "Carregando" quando uma pasta não pode ser lida.
- Índices com título, data ou ID em formato inesperado não interrompem mais a leitura de todas as sessões.
- O texto do aviso de possível duplicata não desaparece mais ao passar o mouse; cópias vinculadas diretamente não são mais apontadas como duplicatas.
- A transcrição recém-clonada é encontrada imediatamente após o vínculo.
- Falha ao gravar nomes de contas é informada no diálogo e não interrompe a interface.
- O `icon.ico` distribuído tinha apenas o quadro de 16×16, o que deixava o ícone borrado na barra de tarefas e na janela do Windows; agora traz nove tamanhos, de 16 a 256 px.
- As mensagens dos atalhos `.vbs` saíam com acentos corrompidos no Windows; os caracteres passam a ser gerados por código, independentemente da página de código do sistema.
- O setup recria automaticamente um `.app/venv` montado com Python anterior ao 3.11, e o atalho do Windows não recorre mais a Python 3.9 ou 3.10.
- Scripts do macOS traduzidos para o português, como o restante do aplicativo.

### Dependências e Python

- Dependências revisadas: customtkinter 6.0.0, darkdetect 0.8.0 e Pillow 13.0.0 já são as versões mais recentes. A dependência transitiva `packaging` passa a ser fixada (26.3), para que toda instalação e todo pacote resolvam o mesmo conjunto.
- Suporte declarado ao Python 3.11 a 3.15: o Pillow 13 publica binários para 3.15 no Windows e no macOS. Os atalhos e o setup procuram o 3.15 primeiro, e o CI ganha execuções com 3.15 no Windows e no macOS Apple Silicon. O mínimo continua 3.11, exigido pelo Pillow 13.
- Verificação do site no CI passa a usar Node.js 24.

### Site e repositório

- Site redesenhado no mesmo visual do aplicativo, com uma réplica ilustrativa da janela no topo, cartões, faixa escura na demonstração e o novo ícone; guias de instalação no mesmo padrão.
- Nova imagem de prévia social, capa do README e captura da interface com dados fictícios, incluída também nos pacotes.
- README reorganizado, com instalação, fluxo de uso, atalhos, requisitos, estrutura do repositório e comandos de desenvolvimento. Guias em Markdown atualizados com os novos nomes dos botões.
- Corrigido no site: palavras coladas nos cartões em telas estreitas e uma frase sobre o Finder do macOS que aparecia no guia do Windows.

### Desempenho e manutenção

- O registro de erros passou a anexar linhas em vez de regravar o arquivo inteiro a cada mensagem (de cerca de 3 ms para 0,007 ms por linha com um log de 4 MB), mantendo a proteção contra links simbólicos também no Windows.
- As varreduras de Code e Cowork compartilham uma única implementação, eliminando cerca de 90 linhas duplicadas.
- Rótulos padrão de contas novas são gravados em uma única escrita.

## [2.1.8] - 2026-10-27

### Segurança

- Validação de esquema de URL (`http://` e `https://`) no instalador visual (`setup_gui.py`) antes de abrir links de download com `os.startfile` ou `webbrowser.open`.

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
