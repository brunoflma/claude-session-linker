# Changelog

## [2.1.0] - 2026-09-21

Esta versão reúne as correções e melhorias incorporadas depois da 2.0.0 e estabelece a publicação verificável de pacotes para Windows e macOS.

### Aplicativo

- Melhorias no tratamento de caminhos, links simbólicos, permissões e limites de leitura de arquivos locais.
- Otimizações na descoberta de sessões, leitura de metadados e comparação de cópias.
- Ajustes de estados de carregamento, botões e mensagens da interface.
- Resolução de executáveis do macOS independente das convenções de caminhos do Windows, com validação de nomes e sem consulta ao PATH do usuário.
- Teste de backup exercitando a criação real do ZIP e as permissões correspondentes, sem simular outro sistema por meio de os.name.

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
