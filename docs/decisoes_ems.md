# Decisões de dados da Energisa MS (EMS)

Este documento foi escrito e commitado **antes** de qualquer resultado de MS: índice, nota de saúde, capacidade firme,
déficit N-1, ranking, valor em R$ ou validação. Cada decisão sai de um diagnóstico dos dados abertos de MS (BDGD e
interrupções da ANEEL) e não de um resultado. Os diagnósticos são reproduzíveis com `scripts/00_cache_bdgd.py` e
`scripts/diagnostico_ems.py`, e as saídas ficam em [`reports/ems/diagnostico/`](../reports/ems/diagnostico/). Cada
tabela abaixo cita o arquivo de onde sai. Execução de 07/11/2026.

O pipeline foi escrito e validado com a Energisa MT (EMT). Aqui cada suposição herdada de MT foi medida em MS antes de
ser mantida ou trocada. As decisões, os caminhos e os resultados de MT **não mudam** ([`metodologia.md`](metodologia.md)
segue valendo para MT).

> Projeto independente, sem vínculo com a Energisa ou com a ANEEL. Só dados abertos (ANEEL e IBGE).

## Resumo das decisões

| # | Tema | O que os dados de MS mostram | Decisão |
|---|---|---|---|
| 1 | Fonte | 8 snapshots de 31/12 (2018 a 2025) já baixados no cache compartilhado, com SHA-256 | Lê os zips direto (GDAL `/vsizip/`), só 6 camadas, de 2021 a 2025, para `data/ems/bdgd-cache` (fora do git); nada é baixado nem alterado |
| 2 | Linhas repetidas | 0 linhas repetidas nas 30 tabelas da BDGD lidas; interrupções repetem 0,28% das linhas em 2018, 0,24% em 2019 e 0,05% em 2020, e nada depois | Lidas como publicadas, como em MT; este repositório não lê os arquivos de continuidade nem de compensações |
| 3 | Trafos de SE | 2018 a 2020 são do modelo M10 (`UNTRS`, sem `UNTRAT`/`EQTRAT`) | Painéis de 2021 a 2025, como em MT |
| 4 | Tensões | Secundário dos trafos de SE: 49 e 72 (MT) e 82 (5 trafos que suprem outras SEs). O código 38 de MT não existe em MS | `tensoes_secundario_mt: ["49", "72"]` |
| 5 | Potência | Mediana de 25 MVA em todos os anos; sem a anomalia de unidade de 2021 que MT tem | `normalizar_potencia` mantida (não dispara em MS) |
| 6 | SE do circuito | A `subestacao` gravada nas interrupções de 2026 é igual a `CTMT.SUB` em 99,6% ou mais; é igual à SE do trafo apontado em só 74% a 88%, e onde as duas divergem acompanha `CTMT.SUB` em 100% | SE do circuito = `CTMT.SUB` (`se_do_alimentador: ctmt`) |
| 7 | Vínculo coerente | Pela regra de MT (tensão do trafo apontado), só 67% a 89% dos circuitos são coerentes | Coerente = a SE do circuito tem trafo de MT na tensão do circuito (84% a 91% dos circuitos) |
| 8 | Capacidade de emergência | Em 2025, `POT_F01` e `POT_F02` são 1,25x e 1,5x da nominal em 100% dos trafos; em 2021 a 2024, 24% a 33% dos trafos não têm estágio e as razões variam | Capacidade = potência nominal (`capacidade_emergencia: nominal`); estágios cadastrados entram só como sensibilidade |
| 9 | Idade | A data de conexão do mesmo trafo muda em 35% (2022→2023) e 42% (2024→2025) dos casos | **Fora da nota de saúde** (porta (a)); `idade_anos` não é publicada |
| 10 | Perdas no ferro | 100% de cobertura; 4% e 9% dos trafos mudam de valor entre cadastros | Mantida (passa os critérios) |
| 11 | Transferência | Os dois pontos de 71% a 88% das chaves NA caem em segmentos de MT, nos 5 snapshots | Topologia nos 5 snapshots (em MT, só 2024 e 2025), então o índice de 2023 também tem a rota de transferência |
| 12 | Interrupções | De 2022 a 2025, 99,8% ou mais ligam a circuito e SE; em 2026, 84,2%; março de 2026 não tem nenhum registro | Janelas de MT mantidas; 2026 só como resultado parcial |
| 13 | Eventos de SE | 333 eventos com 3+ circuitos em 45 SEs em 2024-2025; 48 das 62 SEs de 2023 têm 3+ circuitos | Definição de MT (3+ circuitos no mesmo minuto) mantida |
| 14 | Validação com eventos | Das 57 SEs do universo de 2023, 44 têm evento de SE em 2024-2025 e 18 têm abertura por disjuntor em 2026 | **Porta (b) por resultado**, avaliada pelo script sobre o índice real |
| 15 | Escalas dos indicadores | As entradas de consumidores e de energia ficam abaixo do limiar "ruim" em todas as SEs | Limiares de MT mantidos (escala absoluta) |
| 16 | R$ por CHI | `valor.json` de MS do `automation-impact`: R$ 5,56 (social) e R$ 2,15 (compensação), `origem_efeito = "transportado de MT"` | Lidos desse arquivo; o rótulo é repetido em toda saída de R$; os R$ 5,94 e R$ 1,93 de MT nunca entram |
| 17 | Energia mensal dos circuitos | A ordem das SEs por energia se mantém entre snapshots (Spearman de 0,95 a 0,97), mas o nível oscila: a energia total cai de 6,3 TWh (2023) para 4,9 TWh (2025) com mais UCs, e 51% dos circuitos caem mais de 10% em 2025 | Carregamento lido como ordem entre SEs dentro de cada snapshot; o crescimento de energia não é publicado em MS; sem comparar níveis de carregamento entre snapshots |

## 1. Fonte, cache e linhas repetidas

A BDGD vem do ArcGIS Hub da ANEEL, um File Geodatabase por ano em 31/12. Os 8 itens e seus títulos foram conferidos
pelo agente que baixou os zips (`MANIFESTO.json` e `DOWNLOAD_DONE.txt` do cache compartilhado, com tamanho e SHA-256).
Este repositório só **lê** esse cache:

| Ano | Item | Título |
|---|---|---|
| 2018 | `5382c59d7cc7494a9a1f8cd865187457` | Energisa_MS_404_2018-12-31_M10_20191023-2327 |
| 2019 | `b83ad867a35b43189f41b68988f7f0b6` | Energisa_MS_404_2019-12-31_M10_20200323-1921 |
| 2020 | `fe56dce0714f4b6795d3b23130f5898a` | Energisa_MS_404_2020-12-31_M10_20210628-1527 |
| 2021 | `933af69c57dd41ea8f6048118b8d07e7` | Energisa_MS_404_2021-12-31_V10_20230315-1800 |
| 2022 | `ff5242147c86428e88971941a35c7cd1` | Energisa_MS_404_2022-12-31_V11_20240422-2036 |
| 2023 | `975f18dfdb0c479cb237893c5b296ca9` | Energisa_MS_404_2023-12-31_V11_20250923-1616 |
| 2024 | `b7fad4cd388845a08a01643599ec747b` | Energisa_MS_404_2024-12-31_V11_20250730-1637 |
| 2025 | `9a1ce360865f4358b31e9fb2d016aac9` | Energisa_MS_404_2025-12-31_V11_20260830-0339 |

Ficam de fora o item avulso `c3585ae516f340b596617827d60da5ef` (`EMS_404_2022-10-31_V10`) e a versão de 17/12/2024 do
snapshot de 2023 (`b8c585ae35224ac8aa0648587ec61bcb`), substituída pela de 23/09/2025. Em MT a política é a mesma
(versão mais recente de cada ano).

`scripts/00_cache_bdgd.py --config configs/premissas_ems.yaml --zips <pasta dos zips>` lê cada zip pelo GDAL
(`/vsizip/`), abre só as camadas `UNSEMT`, `UNTRAT`, `EQTRAT`, `SUB` e `CTMT` (mais `SSDMT` com 9 colunas, para a
topologia) e grava um Parquet por camada e ano em `data/ems/bdgd-cache/<ano>/` (fora do git). O zip não é alterado,
nada é extraído, a gravação é atômica e um ano já convertido é pulado. Só os snapshots V10/V11 (2021 a 2025) têm as
camadas de trafos de SE `UNTRAT`/`EQTRAT`; os de 2018 a 2020 (M10) têm `UNTRS`/`EQTRS` e, no circuito, `NOM` e
`UNI_TR_S` no lugar de `NOME` e `UNI_TR_AT`, então não entram. Para MT o script segue baixando do ArcGIS, e a
gravação de cada camada é a mesma: conferi, nas camadas de 2025, que o Parquet da função nova é idêntico byte a byte ao
da função antiga.

**`count(*)` contra `count(distinct *)` em todo arquivo da ANEEL que este repositório lê**
([`duplicatas.csv`](../reports/ems/diagnostico/duplicatas.csv)):

| Arquivo | Linhas | Distintas | Repetidas | % repetidas |
|---|---|---|---|---|
| interrupções 2018 | 137.841 | 137.460 | 381 | 0,28% |
| interrupções 2019 | 146.020 | 145.668 | 352 | 0,24% |
| interrupções 2020 | 140.072 | 140.006 | 66 | 0,05% |
| interrupções 2021 | 132.173 | 132.173 | 0 | 0,00% |
| interrupções 2022 | 159.748 | 159.748 | 0 | 0,00% |
| interrupções 2023 | 194.214 | 194.214 | 0 | 0,00% |
| interrupções 2024 | 190.557 | 190.557 | 0 | 0,00% |
| interrupções 2025 | 248.367 | 248.367 | 0 | 0,00% |
| interrupções 2026 | 117.890 | 117.890 | 0 | 0,00% |

* Nas camadas da BDGD (5 snapshots x 6 camadas = 30 tabelas) há 0 linhas repetidas, e o
  `COD_ID` é único em 30 tabelas (`SSDMT` foi lida só em 9 colunas).
* **Interrupções:** as linhas repetidas existem só em 2018 a 2020 e pesam menos de 0,03% do CHI de cada ano (medido no
  `distribution-asset-risk`, `docs/decisoes_ems.md`, seção 3.1). Elas só entram nos painéis de 2021 e 2022 (históricos de 2019 a 2021
  e de 2020 a 2022). **Decisão:** ler as interrupções como publicadas, o mesmo tratamento de MT.
* **Continuidade e compensações** (indicadores coletivos, compensações pagas): este repositório **não lê** esses
  arquivos. O R$ por CHI vem do `valor.json` do `automation-impact`, que os lê sem as linhas repetidas (nesses arquivos,
  50% das linhas se repetem).

## 2. Portas de qualidade pré-registradas

Fixadas aqui, antes de qualquer resultado. Os limiares de (b) foram dados pelo pedido do projeto; os demais são
critérios gerais, aplicados do mesmo jeito a todo campo.

### 2.1 Critérios para um campo do cadastro entrar num indicador

Um campo do cadastro de trafos de MT só alimenta um indicador se passa nos três critérios, medidos nos snapshots que
sustentam os dois índices publicados (2023, de validação, e 2025, de decisão):

1. **Cobertura:** pelo menos 90% dos trafos de MT com valor válido (positivo; datas entre 1950 e o ano do cadastro);
2. **Estabilidade:** nas transições 2022→2023 e 2024→2025, no máximo 10% dos equipamentos presentes nos dois cadastros
   (mesmo `COD_ID`) trocam de valor. Um trafo não muda de data de conexão nem de perda no ferro de um ano para o
   outro: valor trocado é mudança de cadastro, não de equipamento;
3. **Não ser uniforme:** nenhum valor único (ou razão única) em 100% dos equipamentos de um snapshot.

Resultado ([`cobertura_campos.csv`](../reports/ems/diagnostico/cobertura_campos.csv) e
[`estabilidade_campos.csv`](../reports/ems/diagnostico/estabilidade_campos.csv)):

| Campo do cadastro de trafos de MT | Válidos 2023 | Válidos 2025 | Mudou 2022→2023 | Mudou 2024→2025 | Passa |
|---|---|---|---|---|---|
| `DAT_CON` (idade) | 100% | 100% | 35% (36 de 103) | 42% (44 de 105) | **não** |
| `POT_NOM` (potência nominal) | 100% | 100% | 0% (0 de 103) | 0% (0 de 105) | sim |
| `POT_F01` (1º estágio de ventilação) | 71% | 100% | 2% (2 de 103) | 89% (93 de 105) | **não** |
| `POT_F02` (2º estágio) | 71% | 100% | 2% (2 de 103) | 96% (101 de 105) | **não** |
| `PER_FER` (perda no ferro) | 100% | 100% | 4% (4 de 103) | 9% (9 de 105) | sim |

### 2.2 Porta (a): a nota de saúde não depende de idade inferida do cadastro de MS

A nota de saúde só entra no índice se não depender de **idade de equipamento inferida do cadastro de MS**. A data de
conexão não passa na estabilidade (a mesma peça de equipamento troca de data em 35% e 42% dos casos), o que repete o
achado do `switchgear-survival` para MS (contagem por safra que sobe e desce, datas trocadas entre cadastros).
**Consequências:**

* `idade_anos` sai de `pesos.saude`, e `scores` não tem mais o limiar de idade. Os outros pesos da saúde ficam na mesma
  proporção de MT (dividem-se por 0,80): utilização 0,375, déficit N-1 0,375, perdas 0,0625 e eventos 0,1875.
* A idade não é publicada em nenhum arquivo de MS e não entra como baseline da validação.
* O código recusa a configuração que contrarie isso: `qualidade.idade_trafo_confiavel: false` com peso de idade na
  saúde faz `config.carregar` e `indice.calcular` levantarem erro (`qualidade.verificar_pesos`, com teste).
* Os componentes que ficam foram verificados acima (potência nominal e perda no ferro) ou nas seções 4 a 7
  (carregamento, vínculo, transferência, eventos).

### 2.3 Porta (b): validação com eventos de subestação

A afirmação de validação ("o índice de saúde × criticidade antecipa os eventos de subestação") só é publicada, **para
cada resultado**, se, entre as SEs do índice de validação (snapshot de 2023, SEs com trafo de MT e carregamento, e que
existem também no snapshot de 2025, onde os eventos são medidos; seção 9):

1. pelo menos **30 SEs** tiveram pelo menos 1 evento do resultado na janela de validação, e
2. houve pelo menos **200 eventos** do resultado no total, nessas SEs.

O limiar conta, entre as SEs do índice, as **ocorrências de cada resultado de validação** (não as interrupções em geral).
A matéria-prima dos dois resultados é a interrupção de média tensão, interna e não programada (o filtro de
`eventos.eventos_mt`). Os resultados da validação de MT são avaliados separadamente:

* **(A) Eventos de SE em 2024-2025:** cada grupo de interrupções que começam no mesmo minuto em 3 ou mais circuitos da
  mesma SE conta como 1 evento;
* **(B) Aberturas por disjuntor de janeiro a julho de 2026:** cada interrupção com o elemento `DISJUNTOR`, ligada à SE
  pela `subestacao` do layout novo, conta como 1 evento. Março de 2026 não tem registro em MS (seção 7).

Se um resultado não passa, **nenhuma correlação, captura do topo ou comparação com baseline desse resultado é
publicada**: sai só a contagem e o motivo, em `reports/ems/validacao_portas.json`, e o README diz por quê. O índice sai
de qualquer forma. Quem avalia é o `scripts/03_validacao.py`, sobre o índice real (`qualidade.porta_validacao`, com
teste). A tabela abaixo é só a contagem prévia, sem índice
([`eventos_disponiveis.csv`](../reports/ems/diagnostico/eventos_disponiveis.csv)); o universo é o conjunto de SEs de 2023
com trafo de MT e circuitos (57 SEs), um pouco maior que o índice:

| Resultado (janela de validação) | Eventos | SEs com pelo menos 1 evento | Dessas, SEs do universo de 2023 |
|---|---|---|---|
| Eventos de SE com 3+ circuitos no mesmo minuto, 2024-2025 (o do índice) | 333 | 45 | 44 |
| Eventos de SE com 2+ circuitos (só informação) | 3.455 | 56 | 55 |
| Eventos de SE com 4+ circuitos (só informação) | 84 | 25 | 24 |
| Aberturas por disjuntor, jan-jul/2026 (sem março) | 577 | 31 | 18 |

### 2.4 Porta (c): as decisões reais de ampliação

A comparação "SEs sinalizadas sem folga N-1 foram mais ampliadas até 2025 que as demais" (a validação não baseada em
eventos de MT) só é publicada, para cada ano de diagnóstico (2021, 2022, 2023), se houver pelo menos **10 SEs
sinalizadas e 10 não sinalizadas** (com 2 ou mais trafos e carregamento confiável) e se **80% ou mais** das SEs do
diagnóstico forem pareadas por coordenada (a menos de 1 km) com uma SE de 2025. A potência nominal do mesmo `COD_ID`
mudou em 23% dos trafos entre 2021 e 2022 (cresce em alguns e cai em outros, o que não é ampliação), então o diagnóstico
de 2021 é o mais frágil dos três.

### 2.5 Análises secundárias declaradas de antemão

Sensibilidade ao fator de carga (0,62 e 0,82, como em MT); capacidade de emergência pelos estágios cadastrados, em
lugar da nominal; vínculo pela regra de MT, em lugar da de MS (o que muda no ranking). São publicadas ao lado do
resultado principal e nunca o substituem: a configuração principal é a deste documento.

## 3. Subestações, trafos e tensões

Contagens por snapshot ([`snapshots_se_trafos.csv`](../reports/ems/diagnostico/snapshots_se_trafos.csv)). "Com
secundário de MT" são os trafos de SE cujo `TEN_SEC` é 49 ou 72:

| Ano | Modelo | Subestações (`SUB`) | Circuitos (`CTMT`) | Trafos de SE | Com secundário de MT | SEs com trafo de MT | SEs com 1 trafo | SEs com 2+ trafos | Potência nominal de MT (MVA) |
|---|---|---|---|---|---|---|---|---|---|
| 2018 | M10 (UNTRS) | 118 | 315 | 92 | - | - | - | - | - |
| 2019 | M10 (UNTRS) | 119 | 423 | 91 | - | - | - | - | - |
| 2020 | M10 (UNTRS) | 126 | 318 | 95 | - | - | - | - | - |
| 2021 | V10/V11 (UNTRAT) | 131 | 320 | 105 | 99 | 55 | 23 | 32 | 2.537 |
| 2022 | V10/V11 (UNTRAT) | 113 | 349 | 117 | 113 | 61 | 26 | 35 | 2.944 |
| 2023 | V10/V11 (UNTRAT) | 108 | 354 | 111 | 106 | 57 | 24 | 33 | 2.661 |
| 2024 | V10/V11 (UNTRAT) | 111 | 359 | 113 | 108 | 59 | 25 | 34 | 2.716 |
| 2025 | V10/V11 (UNTRAT) | 106 | 362 | 115 | 110 | 60 | 27 | 33 | 2.776 |

* A camada `SUB` tem de 106 a 131 subestações por snapshot, mas só de 55 a 61 têm trafo de SE com secundário de MT no
  cadastro. O índice usa só essas, quando também têm circuitos.
* Os códigos de SE (`SUB.COD_ID`) são estáveis: de 2022 em diante, 94% a 100% se mantêm de um snapshot para o seguinte
  ([`estabilidade_se.csv`](../reports/ems/diagnostico/estabilidade_se.csv)). O pareamento por coordenada, usado nas
  comparações entre snapshots, dá a mesma contagem.

| Snapshots | Códigos de SE mantidos | SEs pareadas por coordenada (< 1 km) |
|---|---|---|
| 2021 → 2022 | 107 de 131 (81,7%) | 108 (82,4%) |
| 2022 → 2023 | 106 de 113 (93,8%) | 106 (93,8%) |
| 2023 → 2024 | 108 de 108 (100,0%) | 108 (100,0%) |
| 2024 → 2025 | 104 de 111 (93,7%) | 104 (93,7%) |

Códigos de tensão ([`tensoes.csv`](../reports/ems/diagnostico/tensoes.csv); o `.gdb` não traz a tabela de domínio, então a
leitura em kV é indireta):

| Campo | 2021 | 2023 | 2025 |
|---|---|---|---|
| EQTRAT.TEN_PRI | 94 (84), 82 (21) | 94 (87), 82 (24) | 94 (89), 82 (26) |
| EQTRAT.TEN_SEC | 49 (74), 72 (25), 82 (6) | 49 (74), 72 (32), 82 (5) | 49 (75), 72 (35), 82 (5) |
| CTMT.TEN_NOM | 49 (232), 72 (88) | 49 (245), 72 (108), 61 (1) | 49 (246), 72 (116) |

* Os códigos que aparecem como secundário de trafo de SE são **49, 72 e 82**. O 49 e o 72 são os de MT (13,8 e 34,5 kV na
  leitura de MT) e suprem todos os circuitos de MS (`CTMT.TEN_NOM` 49 e 72, mais 1 circuito de código 61 em 2022 a 2024,
  sem trafo correspondente). O 82 aparece só como secundário de 5 trafos grandes (mediana de 30 MVA, primário 94) e como
  primário de trafos pequenos (mediana de 5 MVA): são trafos de transmissão (provavelmente 138/69 kV) que suprem outras
  SEs, como em MT, e ficam fora da capacidade de MT.
* O **código 38 da lista de MT não existe em MS** (nem como secundário de trafo, nem como tensão de circuito).
  **Decisão:** `tensoes_secundario_mt: ["49", "72"]`.
* **Unidade da potência.** A heurística de MT (`normalizar_potencia`: se a mediana é menor que 1, multiplica por 1.000)
  existe porque o snapshot de 2021 de MT grava `POT_NOM` em outra escala. Em MS a mediana de `POT_NOM` é 25 em todos os
  anos (mínimo 2, máximo 50), então a heurística não dispara. **Decisão:** mantida, sem efeito.

## 4. Vínculo circuito → trafo → SE

O vínculo de MT usa `CTMT.UNI_TR_AT` para achar o trafo de origem e dele tira a SE (`UNTRAT.SUB`) e a tensão do
secundário. Em MS esse ponteiro é pior que em MT
([`vinculo_alimentador_trafo.csv`](../reports/ems/diagnostico/vinculo_alimentador_trafo.csv)):

|  | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| Circuitos | 320 | 349 | 354 | 359 | 362 |
| `UNI_TR_AT` vazio | 0 | 10 | 0 | 56 | 6 |
| `UNI_TR_AT` que não existe em `UNTRAT` | 8 | 0 | 51 | 0 | 0 |
| `CTMT.SUB` diferente da SE do trafo apontado | 2 | 17 | 35 | 34 | 36 |
| **Regra de MT** (trafo apontado): circuitos coerentes | 88,8% | 79,9% | 68,4% | 66,6% | 77,3% |
| Regra de MT: energia nos circuitos coerentes | 91,3% | 82,8% | 70,9% | 71,5% | 82,4% |
| Regra de MT: SEs com cobertura abaixo de 0,8 | 7 de 50 | 15 de 51 | 18 de 49 | 21 de 50 | 15 de 51 |
| **Regra de MS** (SE do circuito): circuitos coerentes | 90,6% | 84,2% | 88,1% | 87,5% | 89,8% |
| Regra de MS: energia nos circuitos coerentes | 93,5% | 87,1% | 90,7% | 90,6% | 92,3% |
| Regra de MS: SEs com cobertura abaixo de 0,8 | 6 de 50 | 11 de 56 | 11 de 57 | 13 de 58 | 12 de 60 |

* O ponteiro `UNI_TR_AT` fica vazio ou aponta para um trafo que não existe no snapshot em 6 a 56 circuitos por ano, e a
  SE do trafo apontado difere de `CTMT.SUB` em 2 a 36 circuitos.
* **Quem tem razão sobre a SE do circuito?** As interrupções do layout novo (2026) trazem `subestacao`, gravada pela
  operação e independente do cadastro de trafos. Ela existe em `SUB.COD_ID` de 2023 a 2025 em 99,6% a 99,7% dos eventos
  ([`vinculo_se_registrada.csv`](../reports/ems/diagnostico/vinculo_se_registrada.csv)):

| Cadastro usado | 2023 | 2024 | 2025 |
|---|---|---|---|
| Interrupções de 2026 (qualquer tensão) com `COD_ID` de circuito | 117.890 | 117.890 | 117.890 |
| Casados a um circuito pelo crosswalk | 84,0% | 85,2% | 84,3% |
| `subestacao` do evento existe em `SUB.COD_ID` | 99,6% | 99,7% | 99,7% |
| `subestacao` = `CTMT.SUB` do circuito | 99,6% | 99,7% | 99,7% |
| `subestacao` = SE do trafo apontado | 75,7% | 74,0% | 87,8% |
| Eventos em que as duas regras divergem | 11.101 | 10.531 | 11.706 |
| Onde divergem: `subestacao` = `CTMT.SUB` | 100,0% | 100,0% | 100,0% |
| Onde divergem: `subestacao` = SE do trafo | 0,0% | 0,0% | 0,0% |

  `CTMT.SUB` acompanha a SE registrada em 99,6% ou mais dos eventos; a SE do trafo apontado, em só
  74% a 88%. Nos eventos em que as duas divergem (mais de 10 mil por snapshot), `CTMT.SUB` acerta
  em 100% e o trafo apontado em 0%. O prefixo de três letras do nome do circuito (`CGM01` é da SE `CGM`) também tem
  uma SE só: em todos os snapshots, de 56 a 68 prefixos por snapshot e nenhum com mais de uma `CTMT.SUB`. **Decisão:** a SE do circuito é `CTMT.SUB`
  (`eletrico.se_do_alimentador: ctmt`). Em MT segue a SE do trafo.
* **Vínculo coerente.** Em MT, o circuito só entra no carregamento se a tensão dele é a do secundário do trafo apontado.
  Como o ponteiro não é confiável em MS, a regra passa a ser a da SE: o circuito é coerente se a SE dele (`CTMT.SUB`)
  tem algum trafo de MT com secundário na tensão do circuito (`eletrico.vinculo_alimentador: se`). A energia dos
  circuitos incoerentes continua fora do carregamento, e a SE com menos de 80% da energia em circuitos coerentes fica
  com `carregamento_incerto`, como em MT. Pela regra de MS, 84% a 91% dos circuitos são coerentes
  (contra 67% a 89% pela regra de MT) e há 6 a 13 SEs com cobertura abaixo de 0,8 por snapshot.
  A regra de MT fica como sensibilidade.

## 5. Capacidade, perdas, idade e energia dos circuitos

Em MT, a capacidade de cada trafo no N-1 é o maior estágio de ventilação forçada cadastrado (`POT_F01`, `POT_F02`)
vezes `sobrecarga_emergencia` (1,0). Em MS esses estágios não são confiáveis
([`cobertura_campos.csv`](../reports/ems/diagnostico/cobertura_campos.csv)):

|  | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| Trafos de MT com 1º estágio cadastrado | 76% | 67% | 71% | 70% | 100% |
| Valores distintos de `POT_F01`/`POT_NOM` | 9 | 13 | 14 | 14 | 1 |
| Valores distintos de `POT_F02`/`POT_NOM` | 9 | 13 | 14 | 14 | 1 |
| Parcela do valor mais comum de `POT_F02`/`POT_NOM` | 23% | 29% | 28% | 28% | 100% |

* De 2021 a 2024, de 24% a 33% dos trafos de MT não têm estágio cadastrado, e as razões estágio/nominal são variadas
  (1,0; 1,2; 1,25; 1,33...). Em **2025**, todos os 110 trafos têm `POT_F01` = 1,25 x `POT_NOM` e `POT_F02` = 1,5 x
  `POT_NOM`, inclusive os de 5 MVA: um valor único em todos os equipamentos é padrão de preenchimento, não medida de
  trafo. Entre 2024 e 2025, 89% e 96% dos trafos trocam de valor (`estabilidade_campos.csv`).
* **Decisão:** a capacidade de cada trafo é a **potência nominal** (`eletrico.capacidade_emergencia: nominal`), nos dois
  índices. A potência nominal passa nos três critérios. Capacidade firme = soma das nominais menos a do maior trafo. A
  capacidade pelos estágios cadastrados (regra de MT) é calculada só como sensibilidade, com o aviso de que em 2025 ela é
  1,5 x a nominal em todo trafo, e portanto otimista.
* **Perda no ferro (`PER_FER`):** passa nos critérios (100% de cobertura; 4% e 9% dos trafos trocam de valor nas
  transições que importam). Tem poucos valores distintos (21 a 26 em cerca de 110 trafos), então o z-score por porte é
  grosseiro. **Decisão:** mantida, com o peso proporcional de 0,0625.
* **Idade:** reprova (seção 2.2). As datas de conexão dos trafos de SE são plausíveis em cada cadastro (100% entre 1950 e o ano
  do cadastro, com 57 a 72 datas distintas), e mesmo assim a data troca entre cadastros. Não há como saber qual cadastro
  está certo.

### 5.1 Energia mensal dos circuitos (`CTMT.ENE_xx`)

O carregamento estimado de cada SE (utilização e déficit N-1, 75% do peso da saúde) vem da energia mensal dos
circuitos. A energia de cada trafo (`UNTRAT.ENES_xx`) é o mesmo número: a soma por SE é idêntica à dos circuitos, então
não é uma checagem independente. Por snapshot
([`energia_circuitos.csv`](../reports/ems/diagnostico/energia_circuitos.csv)):

|  | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| Energia dos circuitos (GWh) | 5.567 | 5.581 | 6.324 | 5.739 | 4.926 |
| Consumidores (UCs) | 1.250.117 | 1.339.896 | 1.386.394 | 1.458.167 | 1.404.395 |
| kWh por UC | 4.453 | 4.166 | 4.561 | 3.936 | 3.508 |
| Circuitos com energia anual positiva | 91,6% | 98,3% | 96,3% | 96,1% | 95,3% |
| Meses com energia negativa (circuitos) | 85 (8) | 0 (0) | 0 (0) | 0 (0) | 85 (20) |
| Meses com energia zero | 246 | 226 | 203 | 246 | 186 |

E entre snapshots seguidos ([`energia_estabilidade.csv`](../reports/ems/diagnostico/energia_estabilidade.csv)):

| Snapshots | Razão mediana por circuito (P10 a P90) | Circuitos com queda > 10% | Razão mediana por SE | SEs com queda > 20% | Spearman da energia por SE |
|---|---|---|---|---|---|
| 2021 → 2022 | 0,92 (0,69 a 1,18) | 44% | 0,90 | 18% | 0,97 |
| 2022 → 2023 | 1,06 (0,78 a 1,78) | 17% | 1,08 | 9% | 0,95 |
| 2023 → 2024 | 1,01 (0,59 a 1,24) | 24% | 0,98 | 16% | 0,97 |
| 2024 → 2025 | 0,89 (0,38 a 1,28) | 51% | 0,89 | 32% | 0,97 |

Energia é fluxo medido, não atributo do equipamento, então o critério de estabilidade de 2.1 não se aplica ao nível.
Valem dois critérios próprios, também fixados antes dos resultados: **(i)** pelo menos 90% dos circuitos com energia
positiva; **(ii)** a ordem das SEs por energia se mantém entre snapshots seguidos (Spearman de pelo menos 0,9).

* **Passa:** de 91,6% a 98,3% dos circuitos têm energia positiva, e o Spearman por SE fica entre 0,95 e 0,97.
* **Não passa, e fica registrado:** o **nível** e o **crescimento**. A energia total cai de 6,3 TWh (2023) para 4,9 TWh
  (2025), com 1,386 milhão para 1,404 milhão de UCs (de 4.561 para 3.508 kWh por UC). Em 2025, 51% dos circuitos caem mais
  de 10% e 32% das SEs caem mais de 20%. Aparecem 85 meses de energia negativa em 2021 (8 circuitos) e de novo em 2025
  (20 circuitos). A energia é líquida da geração distribuída, e o arquivo não permite separar crescimento da GD de mudança
  de definição entre cadastros.
* **Decisões:** (1) o carregamento é lido como **ordem das SEs dentro de cada snapshot** e como fração da capacidade, não
  como nível comparável entre snapshots; o pico continua sendo uma estimativa por fator de carga, com a sensibilidade de
  MT. (2) `crescimento_aa` (peso zero em MT) **não é publicado** em MS: mediria sobretudo essa instabilidade. (3) As
  contagens de SEs sem folga N-1 de anos diferentes (2021, 2022, 2023, 2025) não são lidas como tendência. (4) A
  comparação com as ampliações usa o carregamento de cada ano de diagnóstico; as contagens de sinalizadas variam de um
  ano para o outro em parte por essa instabilidade e não são comparáveis entre si.

## 6. Transferência pelas chaves normalmente abertas

A chave NA liga dois pontos (`PAC_1`, `PAC_2`), e os segmentos de MT (`SSDMT`) que tocam cada ponto dizem a que circuito
pertence cada lado. O casamento é por igualdade do texto do PAC, não por coordenada (`topologia.py`), então a questão
dos fusos UTM 21S e 22S de MS não se aplica aqui
([`transferencia_na.csv`](../reports/ems/diagnostico/transferencia_na.csv)):

|  | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| Chaves (`UNSEMT`) | 116.909 | 121.063 | 125.633 | 137.493 | 161.148 |
| Normalmente abertas (NA) | 3.858 (3,3%) | 3.983 (3,3%) | 4.181 (3,3%) | 4.243 (3,1%) | 4.688 (2,9%) |
| NA com os dois pontos (`PAC_1`, `PAC_2`) em segmentos de MT | 71,2% | 82,3% | 82,9% | 84,7% | 87,5% |
| Pares de circuitos ligados por NA | 1.028 | 1.291 | 1.379 | 1.438 | 1.558 |
| Pares entre SEs diferentes | 220 | 312 | 320 | 327 | 378 |
| Circuitos com rota para outra SE | 157 de 320 | 194 de 349 | 193 de 354 | 196 de 359 | 200 de 362 |
| UCs em circuitos sem rota para outra SE | 50,1% | 47,9% | 46,9% | 46,2% | 45,6% |

* Os dois pontos de uma chave NA caem em segmentos de MT em 71% (2021) a 88% (2025) dos casos; em 2023 são 83%.
  Os pontos que não casam não geram par, então a rota de transferência é um **limite inferior**.
* Nos 5 snapshots a SE de cada circuito é `CTMT.SUB` (seção 4).
* **Decisão:** a topologia entra em 2021 a 2025 (`bdgd.topologia.anos`). Em MT o cache só tinha 2024 e 2025, e o índice
  de validação (2023) ficava sem a rota de transferência na criticidade; em MS ele a tem. Isso é uma diferença
  deliberada entre as duas validações.

## 7. Interrupções: vínculo, 2026 e março

O arquivo `interrupcoes_ems.parquet` é o do `distribution-asset-risk` (esquema em `docs/saidas_ems.md` de lá). O
evento de MT é o interno e não programado de média tensão. Fração que liga a um circuito (pelo `crosswalk` do snapshot
mais recente até o ano) e a uma SE
([`vinculo_interrupcoes.csv`](../reports/ems/diagnostico/vinculo_interrupcoes.csv)):

| Snapshot de vínculo | Ano dos eventos | Eventos de MT (internos, não programados) | Com circuito | Com SE | CHI com SE |
|---|---|---|---|---|---|
| 2021 | 2019 | 89.363 | 99,1% | 99,1% | 99,5% |
| 2021 | 2020 | 84.309 | 99,3% | 99,3% | 99,7% |
| 2021 | 2021 | 73.872 | 99,3% | 99,3% | 99,6% |
| 2023 | 2021 | 73.872 | 99,2% | 99,2% | 99,6% |
| 2023 | 2022 | 93.247 | 100,0% | 100,0% | 100,0% |
| 2023 | 2023 | 95.745 | 100,0% | 100,0% | 100,0% |
| 2025 | 2023 | 95.745 | 99,9% | 99,9% | 100,0% |
| 2025 | 2024 | 111.946 | 100,0% | 100,0% | 100,0% |
| 2025 | 2025 | 118.385 | 100,0% | 100,0% | 100,0% |
| 2025 | 2026 | 103.373 | 84,2% | 84,2% | 82,4% |

* De 2019 a 2025 o vínculo é de 99,1% ou mais; a SE é a do circuito (`CTMT.SUB`), então circuito e SE casam juntos.
* **2026:** só 84,2% dos eventos ligam a um circuito de algum snapshot publicado; o resto usa `COD_ID` de um
  cadastro ainda não publicado. O campo `subestacao` de 2026, porém, existe em `SUB.COD_ID` em 99,6% a 99,7%
  dos eventos com circuito (seção 4), e é por ele que as aberturas por disjuntor são ligadas à SE.
* **Março de 2026 não tem nenhum registro** no arquivo de interrupções de MS (em MT tem 27 mil). Os números de 2026 de
  MS são parciais e sem março. Nada foi inventado.
* O layout legado (2018 a 2025) grava em `subestacao` o prefixo de 3 letras do circuito (`CGM`), e o novo (2026), o
  código numérico da SE. Por isso as interrupções de 2018 a 2025 são ligadas à SE pelo circuito, e as de 2026 pelo
  campo `subestacao`.

## 8. Escalas, eventos de SE e janelas

* **Escalas.** Os limiares "bom" e "ruim" de cada indicador (`scores`) são absolutos. A distribuição das entradas em MS
  ([`escalas_entradas.csv`](../reports/ems/diagnostico/escalas_entradas.csv)) frente a esses limiares:

| Entrada (SEs com trafo de MT e circuitos) | Ano | SEs | P10 | Mediana | P90 | Limiar bom | Limiar ruim | SEs no bom ou melhor | SEs no ruim ou pior |
|---|---|---|---|---|---|---|---|---|---|
| Consumidores atendidos pela SE | 2023 | 57 | 2.902,8 | 18.934,0 | 48.414,0 | 5.000 | 100.000 | 18% | 0% |
| Energia anual da SE (GWh) | 2023 | 57 | 13,8 | 80,1 | 211,6 | 20 | 500 | 19% | 0% |
| Eventos de SE por ano por 100 mil UCs (histórico de 3 anos) | 2023 | 57 | 0,0 | 5,6 | 30,4 | 0 | 20 | 28% | 18% |
| Consumidores atendidos pela SE | 2025 | 60 | 2.806,8 | 19.224,0 | 49.322,3 | 5.000 | 100.000 | 18% | 0% |
| Energia anual da SE (GWh) | 2025 | 60 | 5,9 | 51,6 | 176,0 | 20 | 500 | 30% | 0% |
| Eventos de SE por ano por 100 mil UCs (histórico de 3 anos) | 2025 | 59 | 0,0 | 8,3 | 23,8 | 0 | 20 | 22% | 15% |

  O porte das SEs de MS é menor que o de MT (nenhuma SE chega a 100 mil UCs nem a 500 GWh), então a criticidade de MS
  fica mais baixa que a de MT no mesmo critério. **Decisão:** manter os limiares (a escala é a mesma), sem recalibrar para
  distribuir as notas. As comparações com MT são descritivas.
* **Eventos de SE.** Mantida a definição de MT: 3 ou mais circuitos da mesma SE com início no mesmo minuto
  (`eventos.min_alimentadores_evento_se: 3`). 48 das 62 SEs de 2023 têm 3 ou mais circuitos.
  Com 2 circuitos a contagem passa de 300 para mais de 3 mil eventos, o que mistura coincidências com falha da SE.
* **Janelas.** Iguais às de MT: decisão no snapshot de 2025, validação com o de 2023, resultados em 2024-2025 e as
  aberturas por disjuntor em 2026 (jan-jul, sem março), histórico de 3 anos no painel de cada snapshot, diagnósticos de
  ampliação de 2021, 2022 e 2023. Todos os snapshots e anos de interrupção existem, o vínculo é de 99,1% ou mais nas
  janelas de 2023 e 2024-2025, e as janelas não contradizem nenhum dado de MS.

## 9. Parâmetros: o que fica igual a MT e o que vem de MS

**Iguais aos de MT** (premissas ilustrativas, sem recalibrar): fator de potência 0,92; fator de carga 0,72 (e a
sensibilidade em 0,62 e 0,82), já que MS também só tem energia mensal; `cobertura_minima_vinculo` 0,8; os pesos da
criticidade (0,45; 0,20; 0,20; 0,15) e os limiares de todos os `scores`; os cortes da matriz (50 e 50); `taxa_falha_trafo_ano`
1%, `horas_reposicao` 72, `custo_ampliacao_rs_mva` R$ 200 mil, vida útil de 35 anos, taxa de desconto de 8% e custo da
energia não suprida de R$ 7.000/MWh; a sensibilidade de pesos (Dirichlet, 1.000 sorteios, concentração 20, semente 0);
o limiar de ampliação (10% de potência ou mais um trafo) e o pareamento de SEs por coordenada (1 km).

**Rederivados de MS** (diagnósticos acima): lista de tensões de MT (`["49", "72"]`); SE do circuito (`CTMT.SUB`); vínculo
coerente pela SE; capacidade pela potência nominal; saúde sem idade (pesos proporcionais); topologia em 2021 a 2025;
**R$ por CHI e rótulo de origem do efeito**, lidos de `../automation-impact/reports/ems/valor.json` (R$ 5,56 social e
R$ 2,15 de compensação, ponderados pelo CHI dos eventos de religador do `automation-impact`; os valores de MT, R$ 5,94 e
R$ 1,93, nunca são lidos fora de MT); as portas (a), (b) e (c); a exigência de que a SE do índice exista no snapshot de
medição do resultado (uma SE de 2023 cujo código não existe em 2025 não tem como receber eventos de 2024-2025, e
contá-la como "zero evento" distorceria a correlação).

**`origem_efeito`.** O `valor.json` de MS traz `origem_efeito = "transportado de MT"`: o efeito do religador de MS não
foi medido, é o de MT. Este repositório usa só o R$ por CHI (não usa o efeito do religador), mas o campo vem do mesmo
arquivo, então **toda saída de R$ de MS repete o rótulo** (coluna `origem_efeito` em `indice_2025.csv` e campo no
`resumo_2025.json`; teste em `tests/test_ems.py`).

**Como as comparações MT x MS serão feitas.** Só descritivas e normalizadas por consumidor e por km de rede, sem afirmar
causas. Os indicadores de destaque do README de MS são os de MT: SEs de um trafo só; UCs sem rota para outra SE; SEs
com 2+ trafos sem folga N-1 (capacidade nominal; a sensibilidade com os estágios cadastrados ao lado); SEs com pico
estimado acima de 80% da potência; ampliações (se passar a porta (c)); correlação do índice de 2023 com os eventos (se
passar a porta (b)); eventos de SE por ano e fração do CHI.

## 10. Suposições de MT encontradas e como foram tratadas

Busca ampla em `src/`, `scripts/`, `configs/`, `tests/`, `README.md` e `docs/` por nome da distribuidora, UF, código
ANEEL, anos fixos, tensões, caminhos fixos e parâmetros ajustados à rede de MT:

| Onde | Suposição de MT | Tratamento |
|---|---|---|
| `scripts/01_paineis.py` | arquivo `interrupcoes_emt.parquet` fixo | `config.arquivo_interrupcoes`: `interrupcoes_<sigla em minúsculas>.parquet` (o de MT segue `interrupcoes_emt.parquet`) |
| `scripts/00_cache_bdgd.py` | snapshots lidos de `emt.yaml` do projeto irmão; download do ArcGIS; camadas e anos de topologia fixos (2024, 2025) | `bdgd.*` na configuração; zips locais lidos pelo GDAL; o caminho de MT continua o mesmo |
| `scripts/01` a `04` | `data/processed` e `reports/` fixos | `paths.reports`, `paths.processed`; a configuração de outra distribuidora é recusada se apontar para as pastas de MT |
| `scripts/01_paineis.py`, `02_indice_decisao.py` | anos 2021 a 2025 e 2018 a 2026, fatores de carga 0,62 e 0,82 | `dados.anos_paineis`, `dados.anos_interrupcoes`, `eletrico.fator_carga_sensibilidade` (padrão = MT) |
| `scripts/03_validacao.py` | 2026, `DISJUNTOR`, diagnósticos de 2021 a 2023, baseline "idade" | bloco `validacao` da configuração; sem idade quando ela não é confiável; portas (b) e (c) |
| `scripts/04_figuras.py` | `ref/mt_ibge.geojson`, "Energisa MT" no título, "2024-25" e "2026" nos rótulos, nomes de SE com "138 KV" e "69 KV" | `paths.malha_ibge` (`ref/ms_ibge.geojson`, IBGE UF 50), nome da distribuidora e anos da configuração |
| `configs/premissas.yaml` | tensões `["38", "49", "72"]`; `rs_por_chi_*` de MT escritos no arquivo; sigla `EMT` | MS: `["49", "72"]` e R$ por CHI lidos do `valor.json` de MS (obrigatório fora de MT) |
| `dados.alimentadores` | SE do trafo apontado; vínculo pela tensão do trafo apontado | opções `se_do_alimentador` e `vinculo_alimentador` (padrão = MT) |
| `dados.trafos_se` | capacidade pelos estágios de ventilação; idade pela data de conexão | opção `capacidade_emergencia` (padrão = MT); idade fora da nota |
| `dados.normalizar_potencia` | anomalia de unidade do snapshot de 2021 de MT | conferida: não dispara em MS |
| `topologia.py`, `painel.transferencia` | PAC como texto; topologia só em 2024 e 2025 | PAC por texto não depende de fuso UTM; topologia em 2021 a 2025 na configuração de MS |
| `eventos.eventos_se` | 3 ou mais circuitos no mesmo minuto | conferida (seção 8); mantida |
| `validacao.casar_por_proximidade` | códigos de SE mudam entre 2022 e 2023; 1 km | em MS os códigos são estáveis (94% a 100%); mantido |
| `README.md`, `docs/metodologia.md` | "Energisa MT", "Mato Grosso", números de MT | o texto de MT não foi reescrito; MS tem seção própria no README e `docs/resultados_ems.md` |
| `.gitignore` | já ignora `data/` | tudo de MS grava em `data/ems/` |
| clima (INMET) | UF "MT" | não existe neste repositório |

## 11. O que não foi feito

* **Painéis de 2018 a 2020 (M10):** as camadas de trafos de SE se chamam `UNTRS`/`EQTRS` e o circuito usa `NOM` e
  `UNI_TR_S`. Não foram mapeadas.
* **Idade dos trafos de SE:** não publicada (porta (a)). Vale para quem tiver o cadastro patrimonial da empresa.
* **Condição física, medição de pico e DGA:** não existem em dados abertos; ver Limitações no README.
* **Regra de decisão de religador:** fora do escopo (`automation-impact`).
* **Seletor MT/MS no painel Streamlit:** este repositório não tem painel.

## 12. Reproduzir

```bash
python scripts/00_cache_bdgd.py --config configs/premissas_ems.yaml --zips <pasta dos zips>   # ou SEHEALTH_BDGD_ZIPS
python scripts/diagnostico_ems.py --config configs/premissas_ems.yaml --zips <pasta dos zips>
```

A configuração também pode vir da variável `SEHEALTH_CONFIG=configs/premissas_ems.yaml`. Precisam estar clonados ao
lado: `distribution-asset-risk` (dados de MS em `data/ems/interim`) e `automation-impact` (`reports/ems/valor.json`).
