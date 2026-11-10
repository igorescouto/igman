# Núcleo Viv · TV vertical: projeto para o DaVinci Resolve

Formato: 9:16, 2160x3840, 30 fps, sem áudio, loop perfeito.

## Criar o projeto no Resolve

1. Baixe esta pasta `resolve_vertical/` inteira para o Mac. Pode ficar no `IGMAN_SSD1`.
2. Abra o DaVinci Resolve. Vá em **Workspace > Console** e clique na aba **Py3**.
3. Cole as duas linhas, trocando só o caminho da primeira:
   ```python
   PASTA_PROJETO = r"/Volumes/IGMAN_SSD1/.../resolve_vertical"
   exec(open(PASTA_PROJETO + "/criar_projeto_resolve.py", encoding="utf-8").read())
   ```
4. Uma janela pede a **pasta dos takes** (os `IGOR20261107_*.MP4`). Escolha a pasta e pronto.

O script cria o projeto **NucleoViv_TV_Vertical** com os bins GRAFICA, TEXTOS, TAKES e REFERENCIA, as 4 timelines montadas, marcadores por cena e a fila de render (MP4 H.264, sem áudio, saída em `resolve_vertical/render/`).

Os takes são só referenciados: nada é movido, alterado ou apagado.

## As 4 timelines

| Timeline | Tipo | Duração | Ideia |
|---|---|---|---|
| **M1_LINHA_DA_JORNADA** | 100% motion | 29,5 s | Uma linha desce a tela e acende Fase 1, Fase 2 e Fase Perene. Cada ponto revela o nome e uma definição curta. |
| **M2_TRES_FASES** | 100% motion | 27,4 s | Abre com "Não é uma clínica. É um processo." Depois sobem três cartões (1, 2, ∞); o do meio é creme, para quebrar o ritmo. |
| **T1_A_JORNADA** | takes em câmera lenta | 29,8 s | A logo monta e sobe. Seguem três capítulos, cada um com 2 takes, o nome da fase e uma frase. Fecha com logo e assinatura. |
| **T2_O_ESPACO** | takes em câmera lenta | 30,0 s | Seis takes contemplativos de 4,2 s, com legenda discreta embaixo (ambiente + o que acontece). A logo só aparece no fim. |

Todas terminam em "Bem-estar em cada detalhe" e voltam ao fundo vazio, que é igual ao primeiro frame. **Não corte as pontas**, senão o loop quebra.

## Como T1 e T2 estão montadas

- **V1 · BASE:** fundo com pattern e as logos animadas (abertura e fechamento).
- **V2 · TAKES:** 12 takes diferentes, espalhados ao longo da gravação, usando o miolo de cada clipe.
  - Takes em 60p ou 120p são conformados para 30 fps, o que dá câmera lenta real.
  - Take horizontal preenche o quadro vertical com corte central. Reenquadre no Inspector.
- **V3 · ESCURECIMENTO:** degradê verde que garante a leitura do texto sobre a imagem.
- **V4/V5 · TEXTOS:** cada bloco é um PNG com alfa, solto na timeline, para você mover, esticar e animar.

No bin REFERENCIA ficam os `*_PREVIEW_com_slots.mp4`, que mostram a versão animada completa (fades e tempos dos textos) como guia.

## O que lapidar

1. **Takes:** a escolha automática é cega, porque eu não consegui assistir aos brutos. Troque os que não servirem arrastando do bin TAKES. Para fixar um take antes de rodar, preencha `ESCOLHA_DE_TAKES` no topo do script.
2. **Legendas da T2:** foram escritas sem ver as imagens. As atuais são Recepção, Sala de espera, Sala de avaliação, Consultório, Sala de procedimentos e Núcleo Viv. Ajuste ao que cada take mostra.
   - Para mudar um texto, edite `T2_SLOTS` ou `FASES` em `src/viv_vertical.py` e rode `python3 src/viv_vertical.py --only T2`.
   - Ou refaça o texto com Text+ no Resolve.
3. **Dissolves:** selecione os cortes da V2 e use Cmd+T (0,5 s). Nos textos, use fade de 0,3 s.
4. **Cor:** se os takes forem S-Log, aplique a LUT e a correção na página Color.
5. **Câmera lenta em take de 24/30p:** o script avisa no console. Use Retime 50% com Optical Flow.

## Regras de TV sem som já aplicadas

- Uma ideia por tela.
- No máximo 7 palavras por bloco.
- Cada texto fica parado por 3 s ou mais.
- Títulos com cerca de 5% da altura da tela.
- Off-white sobre verde #13352B, com contraste de aproximadamente 11:1.
- Margens seguras.

## Limites desta entrega

- O script **não foi executado num Resolve real**; a sessão que o criou não tinha acesso ao computador. A lógica foi testada contra um Resolve simulado (`src/teste_script_resolve.py`): trilhas sem buracos, 12 takes distintos, 4 renders na fila. Se alguma chamada falhar, o console mostra a linha com o prefixo `[Viv]`.
- **Fonte:** Inter, porque as fontes da marca não estavam acessíveis.
- **Logo animada:** recriada a partir do símbolo vetorial; a oficial não foi encontrada.
