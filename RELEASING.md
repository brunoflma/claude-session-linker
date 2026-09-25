# Publicação de versões

A `main` contém o desenvolvimento atual. Cada release corresponde a um commit específico e mantém seus próprios pacotes. A partir desta configuração, uma nova tag `vX.Y.Z` executa a validação e a publicação automática.

## Regra para alterações futuras

Mudanças no aplicativo, instaladores, recursos de runtime ou dependências exigem aumentar `.app/VERSION` e escrever a entrada correspondente no `CHANGELOG.md`. O CI falha quando encontra mudanças nesses arquivos reutilizando uma versão já marcada. Alterações apenas no site e na documentação podem continuar com a mesma versão.

O processo não cria releases a cada commit nem altera as versões antigas. A publicação é iniciada pelo envio da nova tag, depois da validação da atualização autorizada.

## Preparar e validar

Na raiz de uma cópia de trabalho limpa:

```text
python -m unittest discover -s .app -p "test_*.py"
python -m unittest discover -s scripts -p "test_*.py"
python -m compileall -q .app/session_linker.py .app/setup_gui.py scripts
python scripts/verify-site.py
git diff --check
```

Use um ambiente Python com as dependências de `.app/requirements.txt`. Os testes não exigem conversas reais. Para limitar a descoberta inicial a uma pasta de teste, configure `CLAUDE_SESSION_LINKER_CLAUDE_DIR` para uma pasta temporária vazia.

Depois de revisar o diff, publique a branch e aguarde `Validate application`. A matriz cobre Windows com Python 3.10 e 3.14, além de macOS Intel e Apple Silicon com Python 3.14. Os runners abrem o aplicativo extraído com um perfil sintético; isso não substitui uma verificação manual com versões específicas do Claude Desktop.

## Criar a tag

Verifique se as duas cópias locais e `origin/main` apontam para o commit validado. Troque os valores abaixo pela versão e pelo commit dessa publicação:

```text
git tag -a vX.Y.Z COMMIT_VALIDADO -m "Claude Session Linker X.Y.Z"
git push origin vX.Y.Z
```

A tag precisa corresponder exatamente a `.app/VERSION`. Não use `--force` e não reaproveite uma tag publicada.

## O que a automação faz

1. Repete a validação de aplicativo e pacotes em Windows/macOS para a tag.
2. Gera os pacotes a partir de uma lista explícita de arquivos do commit. Arquivos locais não rastreados, ambientes e dados de usuários não entram.
3. Gera os dois ZIPs versionados, seus aliases para download estável, o manifesto e a lista de hashes.
4. Cria a release em rascunho com as notas daquela versão no changelog.
5. Envia os assets ausentes e confere tamanho e SHA-256 de todos eles.
6. Publica, marca Latest quando apropriado e baixa os arquivos públicos para confirmar os bytes.

Os ZIPs usam armazenamento sem compressão, tamanho pequeno para este aplicativo e metadados fixados ao commit. Isso mantém o pacote reproduzível entre ambientes Python sem depender da versão da biblioteca de compressão.

## Reproduzir os pacotes

Use as ferramentas do próprio commit marcado pela tag:

```text
python scripts/release_bundle.py --ref vX.Y.Z --output release-artifacts
python scripts/release_bundle.py --ref vX.Y.Z --output release-artifacts --check
python scripts/publish_release.py --tag vX.Y.Z --directory release-artifacts --verify-only
```

O último comando exige GitHub CLI autenticado e apenas verifica uma release já publicada. Os arquivos são:

- `claude-session-linker-X.Y.Z-windows.zip`
- `claude-session-linker-X.Y.Z-macos.zip`
- `claude-session-linker-windows.zip` e `claude-session-linker-macos.zip`, idênticos aos correspondentes versionados.
- `release-manifest.json`, com os arquivos, hashes e origem de cada pacote.
- `SHA256SUMS.txt`, com os hashes dos ZIPs e do manifesto.

## Falha ou repetição de execução

Se a validação falhar, a publicação não é executada. Corrija a atualização na branch e valide novamente antes de criar uma nova tag. Depois de criar um rascunho, o script aguarda brevemente sua visibilidade na API do GitHub. Se a falha ocorrer durante o upload de um rascunho, é possível repetir o workflow: ele verifica os assets existentes e envia somente os ausentes. Um asset divergente exige investigação; o script não usa sobrescrita.

Se a release já foi publicada, a repetição apenas verifica sua integridade. Para corrigir código ou pacotes publicados, faça uma nova versão. Para voltar a uma versão anterior, baixe o pacote histórico em uma pasta separada e preserve a instalação atual e os backups. Não restaure dados de conversas automaticamente.
