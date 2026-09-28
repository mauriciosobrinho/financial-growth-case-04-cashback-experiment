# Financial Growth — Case 4: Cashback e lucro incremental

Case técnico end-to-end para avaliar causalmente uma campanha de cashback com três braços e transformar resultados experimentais em uma decisão econômica.

End-to-end causal experimentation case for evaluating a three-arm cashback campaign and translating experimental results into an economic decision.

## Problema de negócio

O experimento compara `control`, `cashback_5` e `cashback_10` para responder se o valor incremental criado supera o custo do incentivo. A unidade de análise é o cliente e cada pessoa aparece uma única vez.

A base contém 350.000 clientes distribuídos em sete ondas. O estimando principal é Intention-to-Treat: `treatment_arm` define assignment, enquanto delivery e activation permanecem variáveis pós-randomização.

## KPI e protocolo de decisão

O KPI primário é `net_margin_30d`:

```text
net margin = gross margin - cashback cost - campaign contact cost
```

Os três contrasts foram definidos antes da interpretação:

- Cashback 5% versus controle;
- Cashback 10% versus controle;
- Cashback 10% versus Cashback 5%.

O pipeline aplica correção de Holm dentro de cada família de outcome. Outcomes binários usam diferença de proporções; métricas contínuas usam diferença de médias com erro padrão de Welch. A margem líquida também recebe intervalo por Bayesian bootstrap.

## Protocolo temporal

| Etapa | Ondas | Uso |
|---|---:|---|
| Desenvolvimento | 1–5 | Inferência principal, CUPED e escolha da política |
| Validação temporal | 6 | Verificação de estabilidade |
| Holdout final | 7 | Teste único após congelamento |

A política é registrada em `policy_freeze_record.json` antes da consulta ao holdout.

## Integridade experimental

- Sample ratio check: p = 1,000;
- maior Standardized Mean Difference: 0,013;
- nenhuma covariável numérica com `|SMD| > 0,10`;
- maior diferença de composição categórica: 0,51 p.p.;
- três braços praticamente balanceados em todas as ondas;
- zero duplicidade de cliente.

A base também contém missing temporal em sinais digitais, sentinela `9999`, caudas longas e non-compliance de delivery/activation. Nenhum mediador pós-tratamento entra como covariável causal.

## Power, MDE e CUPED

Nas ondas 1–5, o diagnóstico retrospectivo indica:

- MDE de conversão próximo de 0,61 p.p. com 80% de poder;
- MDE de margem líquida entre R$ 2,91 e R$ 3,13 por cliente;
- redução de 25,9% da variância de `net_margin_30d` com CUPED.

Theta é estimado no braço controle das ondas 1–5. CUPED utiliza apenas covariáveis pré-tratamento.

## Resultados econômicos nas sete ondas

| Métrica | Control | Cashback 5% | Cashback 10% |
|---|---:|---:|---:|
| Conversion rate | 27,35% | 33,32% | 37,88% |
| Net margin média | R$ 80,19 | R$ 92,65 | R$ 102,28 |
| Lucro incremental total | — | R$ 1,45 mi | R$ 2,58 mi |
| ROI sobre cashback + contato | — | 1,22x | 0,99x |

O braço de 10% maximiza lucro incremental absoluto. O braço de 5% apresenta maior eficiência econômica e menor deterioração dos guardrails.

## Política congelada

O case adota limites ilustrativos para rollout amplo:

- complaints: deterioração máxima de 1,5 p.p.;
- refunds: máximo de 1,0 p.p.;
- chargebacks: máximo de 0,5 p.p.;
- churn: máximo de 0,5 p.p.

Cashback 5% permanece dentro dos limites nas ondas 1–5. Cashback 10% ultrapassa os limites de complaints, refunds e chargebacks. Esses limites são premissas explícitas do case e exigiriam aprovação formal de Produto e Risco em uma aplicação real.

## Holdout final

A política congelada de Cashback 5% confirmou na onda 7:

- incremento de conversão: **+7,22 p.p.**;
- intervalo de 95% da conversão: **+6,21 a +8,23 p.p.**;
- incremento de margem líquida: **+R$ 17,03 por cliente**;
- intervalo de 95% da margem líquida: **R$ 11,58 a R$ 22,48**.

## Recomendação

Avançar com Cashback 5% como política de rollout amplo, condicionado à aprovação dos limites de risco e ao monitoramento por onda. Manter Cashback 10% em piloto restrito ou futuro targeting segmentado, com orçamento e guardrails próprios.

As análises de heterogeneidade servem para geração de hipóteses e não justificam rollout segmentado sem nova validação.

## Estrutura do projeto

```text
data/raw/                         base pública única e dicionário
notebooks/01_end_to_end_case.ipynb
outputs/figures/                 gráficos analíticos
outputs/metrics/                 inferência e registro de congelamento
outputs/tables/                  auditoria, economia e heterogeneidade
presentation/                    apresentação executiva de cinco slides
src/                             pipeline e funções estatísticas
tests/                           testes unitários
```

O ground truth privado permanece fora do projeto e não participa de nenhuma etapa da análise.

## Execução

No Git Bash para Windows:

```bash
py -m venv .venv
source .venv/Scripts/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

python -m unittest -v tests.test_experiment_utils
python -m src.run_case
jupyter nbconvert --to notebook --execute notebooks/01_end_to_end_case.ipynb \
  --output 01_end_to_end_case.ipynb --output-dir notebooks \
  --ExecutePreprocessor.timeout=-1

deactivate
```

## Conclusão metodológica

> Maior conversão não implica maior valor econômico. A decisão deve ser baseada em lucro incremental líquido, incerteza estatística, guardrails e estabilidade do efeito.
