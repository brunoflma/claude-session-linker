let timer;
for (const button of document.querySelectorAll('[data-copy]')) {
  const source = document.getElementById(button.dataset.copy);
  if (!source) continue;
  button.disabled = false;
  button.addEventListener('click', async () => {
    const text = source.textContent.trim();
    try {
      await navigator.clipboard.writeText(text);
      const status = document.getElementById('status');
      status.textContent = 'Comando copiado. Execute na pasta extraída do projeto quando chegar a esta etapa.';
      status.classList.add('visible');
      clearTimeout(timer);
      timer = setTimeout(() => status.classList.remove('visible'), 4000);
    } catch {
      const input = document.getElementById('copy-fallback');
      input.value = text;
      document.getElementById('copy-dialog').showModal();
      input.focus();
      input.select();
    }
  });
}
