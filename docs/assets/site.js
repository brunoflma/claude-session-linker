const byId = (id) => document.getElementById(id);
const state = { kind: 'code', action: 'link' };
const examples = {
  code: {
    link: ['Uma cópia para continuar', '42', 'mensagens de exemplo', 'O transcript clonado pode evoluir de forma independente.', 'O mesmo começo. Próximos passos independentes.', 'O novo vínculo copia o índice e clona o transcript local. Depois disso, cada conta pode continuar a sessão sem uma sincronização automática entre as cópias.', 'Antes de escrever, o Linker faz backup da pasta de índices de destino.'],
    compare: ['Outra continuação disponível', '56', 'mensagens de exemplo', 'A cópia de destino pode ter seguido outro caminho.', 'Compare as cópias antes de escolher.', 'A comparação usa as informações locais disponíveis. Mais mensagens ou atividade recente não garantem que essa seja a versão que você quer. As duas cópias continuam distintas; não há fusão automática.', 'A comparação ajuda a analisar. Ela não escolhe uma versão por você.'],
    remove: ['Vínculo removido desta conta', '—', 'sem índice na conta B', 'A sessão na conta de origem permanece disponível.', 'Em Code, sai o índice da conta escolhida.', 'A remoção apaga o índice daquela conta. Ela não apaga automaticamente o transcript nem remove a sessão das demais contas.', 'Antes de remover, o Linker faz backup da pasta de índices que será alterada.']
  },
  cowork: {
    link: ['Conversa copiada para o destino', '42', 'mensagens de exemplo', 'O destino recebe o índice e a pasta local da conversa.', 'Índice e pasta acompanham o novo vínculo.', 'Em Cowork, o Linker copia os dados locais da conversa para o workspace de destino. Essa cópia não é uma sincronização entre computadores nem uma fusão com outra conversa.', 'O backup cobre o workspace de destino antes da alteração.'],
    compare: ['Uma cópia com outro histórico', '56', 'mensagens de exemplo', 'As informações dependem dos arquivos locais disponíveis.', 'Veja o que cada cópia tem a oferecer.', 'Confira as mensagens e a atividade que a ferramenta consegue ler dos arquivos locais. As cópias podem ter divergido; a comparação não une os históricos automaticamente.', 'Uma quantidade maior de mensagens não define, sozinha, qual cópia você deve usar.'],
    remove: ['Conversa removida desta conta', '—', 'sem índice e pasta na conta B', 'A remoção é específica à conta selecionada.', 'Em Cowork, a remoção também inclui a pasta.', 'O Linker remove o índice e a pasta local correspondente da conta escolhida. Confira o destino e o backup antes de confirmar no aplicativo.', 'O workspace que será alterado recebe um backup prévio.']
  }
};

function renderScenario() {
  const [title, count, label, detail, heading, description, backup] = examples[state.kind][state.action];
  const subtitle = document.createElement('small');
  subtitle.textContent = label;
  byId('target-title').textContent = title;
  byId('target-state').replaceChildren(document.createTextNode(count + ' '), subtitle);
  byId('target-detail').textContent = detail;
  byId('scenario-title').textContent = heading;
  byId('scenario-description').textContent = description;
  byId('backup-note').textContent = backup;
  byId('scenario-arrow').textContent = state.action === 'compare' ? '↔' : state.action === 'remove' ? '−' : '→';
  byId('scenario-badge').textContent = `${state.kind.toUpperCase()} / ${ { link: 'VINCULAR', compare: 'COMPARAR', remove: 'REMOVER' }[state.action] }`;
  byId('scenario').setAttribute('aria-labelledby', `kind-${state.kind}`);
  byId('operation').setAttribute('aria-labelledby', `action-${state.action}`);
}

function tabs(selector, key) {
  const buttons = [...document.querySelectorAll(selector)];
  function select(button) {
    for (const item of buttons) {
      item.setAttribute('aria-selected', String(item === button));
      item.tabIndex = item === button ? 0 : -1;
    }
    state[key] = button.dataset[key];
    renderScenario();
  }
  buttons.forEach((button, index) => {
    button.addEventListener('click', () => select(button));
    button.addEventListener('keydown', (event) => {
      const directions = { ArrowRight: (index + 1) % buttons.length, ArrowLeft: (index - 1 + buttons.length) % buttons.length, Home: 0, End: buttons.length - 1 };
      if (!(event.key in directions)) return;
      event.preventDefault();
      const next = buttons[directions[event.key]];
      select(next);
      next.focus();
    });
  });
}
tabs('[data-kind]', 'kind');
tabs('[data-action]', 'action');

let toastTimer;
byId('copy-prompt').disabled = false;
byId('copy-prompt').addEventListener('click', async () => {
  const prompt = byId('agent-prompt').textContent.trim();
  try {
    await navigator.clipboard.writeText(prompt);
    byId('status').textContent = 'Prompt copiado. Cole no seu agente para preparar a instalação.';
    byId('status').classList.add('visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => byId('status').classList.remove('visible'), 4000);
  } catch {
    byId('copy-fallback').value = prompt;
    byId('copy-dialog').showModal();
    byId('copy-fallback').focus();
    byId('copy-fallback').select();
  }
});

const menu = document.querySelector('.menu-toggle');
function closeMenu() {
  menu.setAttribute('aria-expanded', 'false');
  menu.setAttribute('aria-label', 'Abrir navegação');
  byId('nav').classList.remove('open');
}
menu.addEventListener('click', () => {
  const open = menu.getAttribute('aria-expanded') !== 'true';
  menu.setAttribute('aria-expanded', String(open));
  menu.setAttribute('aria-label', open ? 'Fechar navegação' : 'Abrir navegação');
  byId('nav').classList.toggle('open', open);
});
byId('nav').querySelectorAll('a').forEach((link) => link.addEventListener('click', closeMenu));
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && menu.getAttribute('aria-expanded') === 'true') {
    closeMenu();
    menu.focus();
  }
});
