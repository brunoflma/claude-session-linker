# Orientação Web para o site e os guias

## Uso consultivo

Antes de alterar HTML, CSS ou JavaScript, consulte o [Modern Web Guidance](https://developer.chrome.com/docs/modern-web-guidance?hl=pt-br) e o [guia de adoção](https://developer.chrome.com/docs/modern-web-guidance/get-started?hl=pt-br). Use **Baseline Widely Available** como alvo inicial, detecção de recursos e melhoria progressiva quando houver incompatibilidade. Uma recomendação externa é evidência para revisão, não permissão para mudar o contrato do produto.

Não instale componentes globais, não adicione dependências ao produto e não execute refatoração automática nem scanner obrigatório no CI. Primeiro descreva o problema observado, consulte o guia específico e proponha uma mudança pequena. Preserve aparência, privacidade, comportamento e testes existentes. Não afirme melhora de desempenho sem medir antes e depois.

## Escopo e critérios

Esta referência vale para `docs/index.html`, `docs/install-windows.html`, `docs/install-macos.html` e seus recursos web. Não transforma a interface Python nativa em uma aplicação web nem autoriza acesso a sessões reais do Claude.

- Confira navegação, accordions, copiar prompt e links dos dois sistemas com Tab, Shift+Tab e teclado. Ao ocultar conteúdo, não mantenha foco em controles invisíveis.
- Teste copiar com Clipboard indisponível ou recusado: o texto deve continuar selecionável manualmente, sem abrir ou executar comandos.
- Preserve os links estáveis de release e a distinção entre baixar, instalar e vincular uma sessão. Um clique em guia não deve iniciar instalação.
- Verifique 320, 390 e 1440 px, zoom de 200% e redução de movimento, sem cortar comandos e sem rolagem horizontal da página inteira.
- Execute `python scripts/verify-site.py`. Esse teste confere a apresentação e os destinos estáticos; não comprova a instalação Windows/macOS.
- Continue seguindo `AGENTS.md` e `RELEASING.md`. Uma mudança somente nesta documentação não exige nova versão do aplicativo nem publicação de release.

## Evidência de aceitação

Registre commit, caminho/URL, cenário, navegador, viewport e resultado. Separe teste estático, automação de navegador e avaliação manual. Chrome/Edge, Firefox e Safari fazem parte da matriz; emulação de viewport e Playwright WebKit não comprovam Safari em iPhone real. Use apenas arquivos e perfis sintéticos. A presença desta orientação não é evidência de uma auditoria concluída nem autorização para publicar.
