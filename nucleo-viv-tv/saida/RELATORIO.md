# Núcleo Viv · Vídeos de TV em loop (sem som): relatório da madrugada

Produção: Igman · Cliente: Núcleo Viv (Dr. Lucas Gabriel, Porto Alegre)

## 1. Resumo: o que está pronto e o que falta

| Variação | Duração | Estado | Arquivo |
|---|---|---|---|
| **V3 · Motion puro** | 29,5 s | **Pronto para TV** | `NucleoViv_TV_V3_MOTION_PURO_FINAL_3840x2160_30p_loop.mp4` (+ 1920x1080) |
| **V1 · A Jornada** | 29,8 s | Gráfica 100% pronta. **Faltam os takes reais** (6 slots) | `..._V1_A_JORNADA_PREVIEW_com_slots_...mp4` mostra o corte inteiro |
| **V2 · Bastidor silencioso** | 30,0 s | Gráfica 100% pronta. **Faltam os takes reais** (6 slots) | `..._V2_BASTIDOR_SILENCIOSO_PREVIEW_com_slots_...mp4` |

**Por que V1 e V2 não saíram finalizados:** esta sessão rodou num container na nuvem, sem acesso ao seu computador.
1. Os caminhos do briefing chegaram como placeholders (`[CAMINHO DA PASTA DE BRUTOS NO EXTREME SSD]` etc.). Também não havia nenhuma pasta do computador conectada à sessão, então **não tive acesso a nenhum bruto**.
2. O DaVinci Resolve não está instalado no container.
3. O briefing chegou cortado no meio de "Texto grande, legível a 4 metros, alto cont…". Segui o que dava para inferir (alto contraste, margens seguras). Se havia mais regras depois disso, elas não foram aplicadas.

**Decisão tomada:** em vez de parar, entreguei tudo que não depende dos brutos já finalizado, e o encaixe dos takes ficou automatizado. Fechar V1 e V2 deve levar cerca de 20 minutos de manhã (veja a seção 5).

## 2. Identidade visual usada

- A IDV veio do Google Drive (pasta compartilhada **NUCLEO VIV**: LOGO/PNG, PATTERN, MANUAL DE MARCA). Baixei **cópias** para `nucleo-viv-tv/idv/`. Nada foi alterado na origem: a pasta é somente leitura para esta conta e só usei leitura.
- **Paleta**, medida nos próprios PNGs:
  - verde institucional **#13352B** (fundo)
  - creme **#CEC9BF** (pattern, rótulos)
  - texto principal off-white **#F2EFE9**, com contraste ≈ 11:1 sobre o verde
- **Logo:** usei o símbolo (03.png), separado nas duas peças (asa e crescente) para a animação de montagem, o lettering "V Í V" (09.png) e a linha "NÚCLEO DE MEDICINA INTEGRATIVA" que acompanha a logo horizontal.
- **Pattern:** 02.png (creme) a 7,5% de opacidade, com deriva lenta. A deriva é senoidal e tem período igual à duração do vídeo, então o loop fecha sem salto.
- ⚠️ **Logo animada da IDV:** não encontrei o arquivo no Drive acessível. Recriei a animação seguindo o briefing: o símbolo monta no centro, sobe e depois entram os textos. Se a animação oficial existir, dá para trocar a abertura do V1 por ela no Resolve (trilha V1, de 0 a 5,8 s).
- ⚠️ **Fontes da marca:** não estavam acessíveis (o manual em PDF tem 130 MB e as fontes não estavam no Drive). Usei **Inter / Inter Display**: sem serifa, com desenho próximo ao da linha "NÚCLEO DE MEDICINA INTEGRATIVA" da logo e muito legível a distância. Se a marca tiver fonte própria, a troca é em uma linha (`F_TITLE`, `F_BODY`, `F_LABEL` em `src/viv_render.py`), e é só renderizar de novo. As fontes Inter (licença OFL) estão em `fonts/`, então o renderizador roda em qualquer máquina com Python 3, Pillow, numpy e ffmpeg.

## 3. Roteiros finais (texto na tela)

Regras aplicadas: uma ideia por tela, no máximo 7 palavras por bloco, cada texto parado (100% visível) por **3 s ou mais**. Os títulos têm ~9% da altura da tela e os textos de apoio ~5,5%, com margens dentro da área segura de TV.

### V1 · A Jornada (29,8 s)
| Tempo | Tela |
|---|---|
| 0,0–5,8 | Logo animada: símbolo monta no centro, sobe, entram "V Í V" e "NÚCLEO DE MEDICINA INTEGRATIVA" |
| 5,8–12,2 | Takes 1A/1B · **FASE 1** · "Emagrecimento com método" · "Músculo preservado desde o início." |
| 12,2–18,6 | Takes 2A/2B · **FASE 2** · "Estrutura e contorno corporal" · "Primeiro gordura, depois músculo, depois pele." |
| 18,6–25,0 | Takes PA/PB · **FASE PERENE** · "Manutenção" · "Manter também é tratamento." |
| 25,0–29,8 | Logo + **"Bem-estar em cada detalhe"**, depois volta ao fundo vazio (= frame 1) |

Um indicador de 3 pontos mostra em que fase da jornada o paciente está.

### V2 · Bastidor silencioso (30,0 s)
Seis takes de 4,2 s com dissolve de 0,5 s e legenda discreta no canto inferior esquerdo (ambiente + o que acontece):
B1 RECEPÇÃO · Acolhimento desde a chegada → B2 SALA DE AVALIAÇÃO · Avaliação de composição corporal → B3 SALA DE AVALIAÇÃO · Medida de circunferência → B4 SALA DE AVALIAÇÃO · Teste de força muscular → B5 CONSULTÓRIO · Consulta individualizada → B6 SALA DE ESPERA · Cuidado em cada detalhe → logo + "Bem-estar em cada detalhe" só no fim.
⚠️ As legendas foram escritas para os takes que *imagino* existir. Se os brutos mostrarem outra coisa, mude `descricao`/`ambiente` em `roteiro/v2_bastidor_silencioso.json`, ajuste o texto em `make_v2()` e renderize de novo a base e o overlay.

### V3 · Motion puro (29,5 s)
Símbolo + "A jornada do paciente" → uma linha creme atravessa a tela e acende três pontos. Em cada ponto aparecem o nome da fase e uma definição curta, uma fase por vez:
- FASE 1 · "Emagrecimento com método" · "Composição, circunferência e força avaliadas."
- FASE 2 · "Estrutura e contorno corporal" · "Gordura, músculo e pele, nessa ordem."
- FASE PERENE · "Manutenção" · "Manter o resultado também é tratamento."

Fecha com logo + "Bem-estar em cada detalhe" e volta ao fundo vazio.

**Como as três se diferenciam:** V1 tem capítulos sobre takes, com logo no começo e no fim. V2 é quase só imagem, com legenda pequena e logo só no fim. V3 é 100% gráfico, com a linha da jornada.

## 4. Especificações técnicas (conferidas com ffprobe)
- H.264 High, 3840x2160 e cópia em 1920x1080, 30 fps constantes, yuv420p, BT.709, **sem trilha de áudio**, GOP de 1 s, faststart.
- **Loop:** o primeiro e o último frame de cada vídeo são o mesmo fundo vazio, e o pattern está na mesma posição nos dois (deriva periódica). Detalhes na seção 6.
- Mantive 4K: renderizar não pesou. A cópia em 1080p é para TVs ou players USB que não tocam 4K.

## 5. Como fechar V1 e V2 de manhã (≈20 min)
1. Abra os previews `*_PREVIEW_com_slots_*.mp4`. Cada slot cinza listrado diz que take entra ali e quanto tempo dura.
2. Em `roteiro/v1_a_jornada.json` e `roteiro/v2_bastidor_silencioso.json`, preencha para cada slot:
   - `arquivo`: o nome do bruto, relativo à pasta de brutos
   - `entrada_s`: o ponto de entrada em segundos
   - `velocidade`: 1.0 = normal. Use 0.5 para câmera lenta de bruto 60p, o que ajuda o ritmo contemplativo do V2.
3. Escolha um dos caminhos:
   - **Pelo DaVinci Resolve (o briefing pede este):** preencha `src/config_caminhos.json` e rode `src/resolve_montar_timelines.py` no Console do Resolve (Py3). O script cria o projeto "NucleoViv_TV_Loop" com as 3 timelines (V1 base · V2 takes · V3 textos) e as fila no Deliver como MP4 H.264 4K 30p sem áudio. Pela API não dá para criar dissolves: selecione os cortes da trilha V2 e use Ctrl/Cmd+T. **Se os brutos forem LOG, faça a cor no Resolve.**
   - **Sem Resolve (só ffmpeg):** `python3 src/montar_com_brutos.py --var v1 --brutos "<pasta>"`. Esse caminho já faz os dissolves e gera o final em 4K e 1080p. Com `--auto`, preenche sozinho os slots vazios com os clipes em ordem alfabética, pegando o meio de cada clipe. Serve só para rascunho.
4. Os brutos são apenas lidos nos dois caminhos: nada é movido, alterado ou apagado.

## 6. Verificação feita
| Arquivo | Frames | Áudio | Emenda último→primeiro (PSNR) |
|---|---|---|---|
| V1 preview / base | 894 (29,8 s) | nenhum | 44,8 dB |
| V2 preview / base | 900 (30,0 s) | nenhum | 44,7 dB |
| V3 final 4K (e 1080p) | 885 (29,5 s) | nenhum | 44,8 dB |

O PSNR de ~45 dB na emenda é igual ao de dois frames vizinhos quaisquer, ou seja, não há salto. O loop também vale para as versões finais montadas, porque o primeiro e o último frame vêm da camada base, sem take.

- **Montador ffmpeg testado** com 6 clipes sintéticos (1080p): o V1 final saiu com 894 frames, os takes entraram nos slots com dissolve e os textos ficaram por cima. Os frames de checagem foram conferidos visualmente.
- **Script do Resolve não testado** (não há Resolve no container). Ele segue a API oficial (`ImportMedia`, `AppendToTimeline` com `recordFrame`, `SetRenderSettings`). Se algo falhar, o caminho ffmpeg entrega o mesmo resultado.
- **Folhas de contato:** `CONTATO_V1.jpg`, `CONTATO_V2.jpg` e `CONTATO_V3.jpg`, nesta pasta.
- **Overlays (`*_OVERLAY_3840x2160/`):** sequências PNG com alfa, 894/900 frames, ~320 MB no total. Mantive PNG sem perda porque a compressão em paleta criava faixas no degradê de escurecimento.

## 7. Decisões tomadas sem poder perguntar
1. Como faltavam os brutos, entreguei V3 final e V1/V2 como gráfica final + preview com slots + montagem automatizada, em vez de parar.
2. Recriei a logo animada (a oficial não estava acessível).
3. Usei Inter no lugar das fontes da marca (não estavam acessíveis).
4. Usei o off-white #F2EFE9 nos textos em vez do creme puro, para ganhar contraste na TV. O creme ficou nos rótulos e no pattern.
5. Os nomes das fases ficaram como no briefing. Nas frases, segui a jornada sem prometer resultado (cuidado com a publicidade médica: nada de antes/depois nem números de perda de peso).
6. Pasta de saída: como o caminho veio em placeholder, tudo está em `nucleo-viv-tv/saida/` no repositório `igman`, branch `claude/nice-darwin-p05qmm`.
7. A plataforma Igman não tem job do Núcleo Viv para TV. Não gravei nada nela.

## 8. Arquivos
```
nucleo-viv-tv/
  saida/      RELATORIO.md, CONTATO_V*.jpg, MP4s (V3 FINAL; V1/V2 PREVIEW e BASE), *_OVERLAY_3840x2160/ (PNG com alfa)
  roteiro/    v1_a_jornada.json, v2_bastidor_silencioso.json  ← preencher "arquivo" de cada slot
  src/        viv_render.py (gera toda a gráfica) · montar_com_brutos.py (ffmpeg) · resolve_montar_timelines.py + config_caminhos.json
  idv/        cópias da logo e do pattern (originais intocados no Drive)
  fonts/      Inter + JetBrains Mono (OFL)
```
Para mudar um texto: edite `make_v1/make_v2/make_v3` em `src/viv_render.py` e rode
`python3 src/viv_render.py --var v1 --mode preview base overlay` (≈5 min por variação em 4K).
