# Metodologia

Este documento descreve dados, decisões de tratamento, fórmulas, validação e como interpretar cada resultado do
índice de saúde e criticidade de subestações. Todas as premissas numéricas estão em
[`configs/premissas.yaml`](../configs/premissas.yaml).

## 1. Perguntas

1. **Condição:** quais SEs estão carregadas, sem capacidade firme, antigas ou com eventos frequentes?
2. **Consequência:** quais SEs, se perdidas, deixam mais clientes sem energia e sem alternativa?
3. **Decisão:** onde agir primeiro, com que tipo de ação, e quanto isso vale?
4. **Validade:** o diagnóstico feito com dados de um ano aponta o que aconteceu depois?

## 2. Dados

| Fonte | Camadas / campos | Uso |
|---|---|---|
| BDGD (ANEEL, PRODIST Módulo 10), Energisa MT, snapshots de 31/12 de 2018 a 2025 | `UNTRAT`/`EQTRAT` (trafos de SE: potência nominal e com ventilação forçada `POT_F01`/`POT_F02`, tensões, data de conexão e de imobilização, perdas), `SUB` (nome e coordenada), `CTMT` (alimentadores: SE, trafo de origem `UNI_TR_AT`, tensão, energia mensal `ENE_01..12`), `UNSEMT` (chaves, posição normal `P_N_OPE`), `SSDMT` (segmentos de MT com pontos de conexão `PAC_1`/`PAC_2`, só 2024 e 2025) | carregamento, capacidade, idade, perdas, topologia |
| Interrupções nas redes de distribuição (ANEEL), 2018 a jul/2026 | início, duração, CHI, UCs afetadas, alimentador, causa; em 2026 também `CodSubestacao` e `DscTipoElementoInterrompido` | eventos de SE, CHI por SE, abertura por disjuntor em 2026 |
| `distribution-asset-risk` (projeto irmão) | interrupções harmonizadas entre os dois layouts da ANEEL, crosswalk código → alimentador canônico por snapshot, consumidores e km de rede por alimentador | ligação evento → alimentador → SE |
| `automation-impact` (projeto irmão) | R$ por consumidor-hora interrompido (média da frota) | valor do risco |

`UNTRAT` e `EQTRAT` não existem no modelo antigo da BDGD (snapshots de 2018 a 2020); por isso os painéis vão de 2021
a 2025.

### Decisões de dados

* **Unidade da potência em 2021:** o snapshot de 2021 grava `POT_NOM` em outra escala (0,03 para 30 MVA). Quando a
  mediana é menor que 1, a potência é multiplicada por 1.000 (`dados.normalizar_potencia`).
* **Trafos de MT:** só entram na capacidade os trafos com secundário de média tensão (`TEN_SEC` 13,8 kV ou
  34,5 kV; os códigos foram conferidos com os nomes das SEs). Trafos 138/69 kV suprem outras SEs e ficam fora.
* **SE de cada alimentador:** a SE do trafo de origem (`CTMT.UNI_TR_AT → UNTRAT.SUB`); se o alimentador não aponta
  para trafo cadastrado, `CTMT.SUB`.
* **Vínculo coerente:** 15% (2025) a 18% (2023) dos alimentadores têm tensão diferente do secundário do trafo apontado (ex.:
  alimentador de 34,5 kV ligado a um trafo 138/13,8 kV). A energia deles não entra no carregamento. Se menos de
  80% da energia da SE vem de alimentadores com vínculo coerente (`cobertura_minima_vinculo`), o carregamento e o
  déficit N-1 da SE ficam sem nota (`carregamento_incerto`).
* **Fluxo reverso:** a energia mensal da BDGD é líquida da geração distribuída e de usinas conectadas na MT. Meses
  com energia negativa indicam exportação para a alta tensão; o carregamento usa o módulo do fluxo.
* **Crescimento fora do índice:** como a energia é líquida da GD, ela cai em muitas SEs mesmo com consumo
  crescente. O crescimento de dois anos é calculado e reportado, mas tem peso zero.
* **Idade:** ano da data de conexão (`DAT_CON`); datas fora de 1950 até o ano do snapshot caem para a data de
  imobilização (`DAT_IMO`). Usa-se o trafo mais antigo da SE.
* **Códigos de SE entre snapshots:** os códigos mudaram entre 2022 e 2023. Para comparar snapshots (validação de
  ampliações), cada SE é pareada com a SE mais próxima a menos de 1 km (`validacao.casar_por_proximidade`). Parearam
  65 de 77 SEs de 2021 e 59 de 67 de 2022; em todos os pares, exceto um por ano, o nome também coincide.

## 3. Pipeline

| Script | O que faz | Saída |
|---|---|---|
| `00_cache_bdgd.py` | baixa cada snapshot da BDGD, grava as camadas usadas em Parquet e apaga o GDB | `data/bdgd-cache/<ano>/` |
| `01_paineis.py` | para cada snapshot de 2021 a 2025, monta a tabela por SE (`painel.montar`) com histórico de 3 anos até o snapshot | `data/processed/painel_<ano>.parquet` |
| `02_indice_decisao.py` | índice no snapshot de decisão (2025), sensibilidade de pesos e fator de carga, R$ e ampliações | `reports/indice_2025.csv`, `reports/resumo_2025.json` |
| `03_validacao.py` | índice de 2023 contra resultados de 2024-2026 e ampliações entre snapshots | `reports/validacao_*.csv/json` |
| `04_figuras.py` | figuras do README | `reports/figures/` |

## 4. Fórmulas

### Carregamento e N-1 (`carregamento.py`)

* MW médio do mês m na SE: `P_m = Σ energia_m dos alimentadores com vínculo coerente (kWh) / horas do mês / 1000`.
* Pico estimado: `S_pico = max_m |P_m| / FC / fp`, com `FC = 0,72` (razão média/pico dentro do mês de maior carga;
  sensibilidade em 0,62 e 0,82) e `fp = 0,92`.
* Utilização: `S_pico / Σ POT_NOM` dos trafos de MT.
* Capacidade de emergência de cada trafo: `max(POT_NOM, POT_F01, POT_F02) × sobrecarga_emergencia` (1,0).
* Capacidade firme: `Σ emergência − maior emergência`. SE de um trafo só tem capacidade firme zero.
* Déficit N-1: `max(0, S_pico − firme) / S_pico`. SE de um trafo só tem déficit 1.
* Perdas: resíduo de `log(PER_FER)` contra `log(POT_NOM)` na frota, em desvios-padrão; usa-se o pior trafo da SE.

### Eventos de SE (`eventos.py`)

Interrupções não programadas, internas, de média tensão, ligadas ao alimentador canônico pelo crosswalk do snapshot
e à SE pelo vínculo acima. Um **evento de SE** é um grupo de interrupções que começam no mesmo minuto em 3 ou mais
alimentadores da mesma SE. É o rastro de falhas de barramento, trafo de potência, proteção da SE ou suprimento em
alta tensão, mas também pode vir de clima severo atingindo vários alimentadores ao mesmo tempo. Indicadores: eventos
por ano, CHI dos eventos e eventos por 100 mil UCs.

### Transferência (`topologia.py`)

Para cada chave normalmente aberta (`P_N_OPE = 'A'`), os segmentos de MT que tocam cada ponto (`PAC_1`, `PAC_2`)
dizem a que alimentador pertence cada lado. Se os dois lados são de SEs diferentes, os dois alimentadores têm rota
de transferência entre SEs. Indicador: fração das UCs da SE em alimentadores sem essa rota. A chave existir não
garante folga no alimentador vizinho; é condição necessária, não suficiente.

### Notas e índice (`indice.py`)

* Nota de cada indicador: `100 × (x − bom) / (ruim − bom)`, saturada entre 0 e 100 (escala log10 para UCs e
  energia). Os limiares estão em `scores` no YAML.
* Saúde e criticidade: média ponderada das notas (`pesos`); se um indicador não existe para a SE (ex.: carregamento
  incerto), seu peso é redistribuído entre os demais.
* Risco: `saúde × criticidade / 100`.
* Quadrantes (corte 50/50): **agir** (condição ruim e alta consequência), **planejar** (condição ruim, baixa
  consequência), **monitorar** (condição boa, alta consequência), **manter**.
* Fatores: os dois indicadores com maior contribuição ponderada para a nota de saúde.
* Sensibilidade: 1.000 sorteios de pesos de uma Dirichlet centrada nos pesos definidos (concentração 20); mede-se o
  Spearman com o ranking base e a frequência de cada SE no top 10.

### Valor (`valor.py`)

* Risco por eventos de SE: `CHI anual dos eventos × R$/CHI` (social: 5,94; compensação: 1,93, do `automation-impact`).
* Energia não suprida N-1 esperada: para cada trafo i da SE,
  `corte_i = max(0, S_média − (Σ emergência − emergência_i))`;
  `ENS = Σ_i taxa_falha × horas_reposição × corte_i × fp` (1%/ano e 72 h, ilustrativos), valorada a R$ 7.000/MWh.
* Ampliação candidata (SEs sem folga N-1 e com carregamento confiável): MVA = déficit no pico; capex = MVA × R$ 200
  mil/MVA (ilustrativo), anualizado com fator de recuperação de capital (8% a.a., 35 anos).
* Benefício/custo = R$ de ENS evitada / capex anualizado. Ponto de empate em horas:
  `horas_reposição / (benefício/custo)`.

## 5. Validação

### 5.1 Ampliações reais

Para os diagnósticos de 2021, 2022 e 2023 (SEs com carregamento confiável), compara-se a fração de SEs ampliadas até
2025 entre sinalizadas e não sinalizadas. Ampliação: mais trafos ou pelo menos 10% a mais de potência instalada de MT.
Três critérios: sem folga N-1 (todas), sem folga N-1 com 2+ trafos e utilização acima de 80%.

### 5.2 Previsão de eventos

O índice é montado com o snapshot de 2023 e as interrupções de 2021 a 2023. Os resultados, medidos só depois do corte:

* CHI e número de eventos de SE em 2024-2025, ligados com o snapshot mais recente (medição do resultado, não feature);
* as mesmas grandezas por UC, para separar o efeito do porte;
* CHI e número de interrupções abertas por disjuntor de janeiro a julho de 2026, pelo campo `CodSubestacao` do layout
  novo (4.219 das 6.237 caem em SEs do índice).

Métricas: Spearman e captura do top 10% e 20% (fração do resultado nas SEs de maior previsão). Baselines: porte (UCs),
CHI de eventos de SE nos 3 anos anteriores, idade, taxa passada por UC. Variante "cadastral" da saúde sem o
histórico de eventos.

## 6. Como interpretar

* **Saúde alta** quer dizer condição que pede atenção (carga, falta de capacidade firme, idade, eventos), não
  probabilidade de falha calibrada.
* **Criticidade alta** quer dizer que perder a SE atinge muitos clientes sem alternativa de transferência.
* **Risco** ordena onde olhar primeiro. As 4 SEs estáveis na sensibilidade são as decisões mais seguras; as demais do
  top 10 dependem dos pesos.
* **Déficit N-1** é a base para expansão; a validação mostra que acompanha decisões reais de ampliação.
* **R$** compara alternativas (ampliar contra repor rápido ou transferir), sob premissas explícitas.
* **A validação de eventos** mostra o limite do dado público: para antecipar falhas, a nota de saúde precisa de dados
  de condição física e da telemetria da SE.
