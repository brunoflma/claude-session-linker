# Validação e publicação

O CircleCI executa a apresentação, três combinações Windows Server 2025/Python
(3.11, 3.14 e 3.15) e duas combinações macOS 15 ARM/Python (3.14 e 3.15).
Cada ambiente instala a distribuição Python/Tk oficial fixada por hash e verifica
sua assinatura. Os testes usam perfis sintéticos; o pacote extraído precisa abrir
a interface gráfica. Os recibos registram a revisão e os IDs reais do CircleCI.

O GitHub Actions executa somente macOS 15 Intel/Python 3.14. O gate híbrido exige
essa prova no mesmo SHA, confere o workflow fixado, a tentativa mais recente e a
conclusão das etapas obrigatórias. Na release, também exige o push da tag exata.
Uma alteração intencional no workflow Intel exige atualizar seu hash no gate.

Pushes e pull requests executam a validação. Tags estáveis anotadas `vX.Y.Z`
seguem para publicação somente após as seis provas e a conferência da main e da
tag remota. O contexto `csl-release` restringe o publisher a este projeto, às
referências autorizadas e a jobs sem SSH. A credencial efêmera do checkout fica
em memória; não existe token GitHub permanente copiado para o CircleCI.

O publisher original mantém a construção reproduzível, o rascunho, os hashes,
a publicação e a conferência dos downloads. A entrega é serializada e falha
de forma fechada se fonte, prova, autoridade ou estado remoto divergirem.

`release-authority-probe=true` e `run-supported-native-validation=false`, em
uma execução manual da main, verificam a autoridade de escrita e a transferência
de um arquivo sintético em rascunho temporário. A prova remove o rascunho e
qualquer referência temporária criada, sem publicar uma versão do aplicativo.
