# Local Short Studio

Gere imagens e narração localmente e monte Shorts com movimentos de câmera simulados, transições suaves e legendas opcionais.

O arquivo ZIP contém o projeto completo, com código, configuração Docker/CUDA, exemplo de roteiro, testes e documentação de instalação.

## Documentação

- [Arquitetura e fluxo do projeto](PROJECT_PLAN.md)
- [Baixar o projeto completo](local-short-studio.zip)

Depois de extrair o ZIP, siga o README.md e o docs/USER_GUIDE.md incluídos na pasta do projeto.

## Inicialmente

A primeira versão exporta Shorts verticais 9:16. Um perfil horizontal 16:9 está previsto na configuração para uma etapa futura. A GPU gera imagens e narração localmente; a montagem aplica zoom, panorâmica e crossfades sobre as imagens.

Para a RTX 2060, o projeto requer Docker Desktop com WSL 2, driver NVIDIA compatível com CUDA 13.0 e um checkpoint Stable Diffusion 1.5 colocado na pasta indicada no guia.

A renderização de teste passou com e sem legendas. A inferência CUDA precisa ser validada na máquina de destino.
