# CASE 4 - Cashback e Incremental Profit

## 1. Contexto do desafio

Uma instituição financeira digital deseja avaliar uma campanha de cashback destinada a aumentar engajamento e volume transacional.

O experimento possui três braços:

- Control
- Cashback de 5%
- Cashback de 10%

A pergunta principal não é:

> O cashback aumentou compras?

A pergunta de negócio é:

> O valor incremental criado supera o custo do incentivo?

Uma estratégia pode aumentar conversão e gasto bruto e, ainda assim, destruir valor econômico se o custo do incentivo superar a margem incremental produzida.

## 2. Objetivo analítico

Estimar causalmente o efeito das ofertas de cashback sobre:

- probabilidade de compra;
- frequência transacional;
- spend;
- margem bruta;
- margem líquida;
- guardrails operacionais e de risco.

A recomendação final deve considerar valor econômico incremental, não apenas uplift de conversão.

## 3. Unidade de análise

`customer_id`

Cada cliente aparece uma única vez no experimento.

O tratamento é atribuído antes da janela de outcome.

## 4. Desenho experimental

A base representa um Randomized Controlled Trial com três braços.

`treatment_arm` contém:

- `control`
- `cashback_5`
- `cashback_10`

A randomização ocorre dentro de cada `campaign_wave`.

A análise causal principal deve respeitar a atribuição original do tratamento.

## 5. Ajustes metodológicos importantes

### 5.1 ITT deve ser o estimando primário

O tratamento principal é `treatment_arm`.

`message_delivered` e `offer_activated` acontecem depois da randomização.

Uma análise restrita aos clientes que receberam ou ativaram a oferta pode quebrar a comparabilidade criada pelo experimento.

Por isso, a análise principal deve ser Intention-to-Treat, ITT.

Análises por delivery ou activation podem ser exploratórias, mas devem discutir seleção e non-compliance.

### 5.2 O KPI primário deve ser econômico

A campanha deve ser avaliada por incremento em margem líquida.

A base contém:

- `gross_margin_30d`
- `cashback_cost`
- `campaign_contact_cost`
- `net_margin_30d`

Definição operacional:

`net_margin_30d = gross_margin_30d - cashback_cost - campaign_contact_cost`

O principal contraste econômico é:

`Incremental Profit = E[net_margin | treatment] - E[net_margin | control]`

### 5.3 Cashback não é simplesmente percentual vezes spend total

O custo efetivo depende de:

- ativação da oferta;
- spend elegível;
- percentual do braço;
- teto de cashback.

Isso está refletido em `cashback_cost`.

### 5.4 Comparações múltiplas

Existem três comparações relevantes:

- cashback 5% versus control;
- cashback 10% versus control;
- cashback 10% versus cashback 5%.

A solução deve definir contrasts antes da interpretação e discutir controle de erro por múltiplas comparações.

Métodos aceitáveis:

- Holm;
- Bonferroni;
- FDR, quando metodologicamente justificado.

Para este case, Holm é uma escolha recomendada para os três contrasts principais.

## 6. Base fornecida

Arquivo único:

`data/raw/case_04_cashback_experiment_raw.csv`

Características:

- 350.000 clientes únicos;
- 7 ondas mensais de campanha;
- aproximadamente 50 mil clientes por onda;
- randomização em três braços;
- features pré-treatment;
- variáveis de assignment;
- non-compliance operacional;
- outcomes de negócio;
- guardrails;
- problemas deliberados de qualidade de dados;
- nenhuma divisão temporal fornecida pronta.

## 7. Ground truth privado

Existe arquivo privado apenas para auditoria do DGP:

`private_do_not_use_in_modeling/case_04_ground_truth_private.csv`

Ele contém probabilidades potenciais de compra sob:

- controle;
- cashback 5%;
- cashback 10%.

Esse arquivo NÃO pode ser utilizado durante desenvolvimento, ajuste ou avaliação.

Ele serve somente para auditoria posterior da geração sintética.

## 8. Principais famílias de variáveis

### Identificação e tempo

- `customer_id`
- `reference_date`
- `campaign_wave`
- `customer_tenure_months`

### Segmentação

- `customer_segment`
- `region`
- `merchant_flag`
- `merchant_segment`
- `income_band`
- `relationship_tier`

### RFM e comportamento pré-treatment

- `days_since_last_transaction`
- `txn_count_30d_pre`
- `txn_count_90d_pre`
- `spend_30d_pre`
- `spend_90d_pre`
- `avg_ticket_30d_pre`
- `avg_ticket_90d_pre`

### Pix, saldo, cartão e produtos

A base inclui sinais de comportamento pré-treatment em Pix, saldo, utilização de cartão, limite e portfólio de produtos.

### Digital e CRM

A base inclui atividade no app, abertura de push/e-mail, histórico de campanhas e aceitação de ofertas.

### Fricção pré-treatment

Inclui suporte, reclamações, refunds e chargebacks históricos.

### Assignment

- `treatment_arm`
- `cashback_pct`

### Pós-assignment

- `message_delivered`
- `offer_activated`

### Outcomes

- `purchased_30d`
- `txn_count_30d_post`
- `spend_30d_post`
- `gross_margin_30d`
- `cashback_cost`
- `campaign_contact_cost`
- `net_margin_30d`

### Guardrails

- `complaint_30d`
- `refund_flag_30d`
- `refund_value_30d`
- `chargeback_flag_30d`
- `chargeback_value_30d`
- `churn_60d`

### Variáveis pós-treatment que exigem cautela

- `post_campaign_app_sessions_7d`
- `cashback_balance_viewed_7d`

O dicionário completo está em `case_04_data_dictionary.csv`.

## 9. Problemas deliberadamente presentes

A base contém:

- missing crescente em variáveis digitais;
- missing potencialmente informativo;
- código sentinela;
- zeros legítimos;
- distribuições financeiras com cauda longa;
- outliers;
- features pré-treatment fortemente correlacionadas;
- mudança moderada de composição entre ondas;
- non-compliance entre assignment, delivery e activation;
- variáveis pós-treatment;
- heterogeneidade real de tratamento;
- guardrails que pioram de forma distinta entre braços;
- diferenças entre ganho de conversão e ganho econômico.

O DGP foi desenhado para que o braço de 10% possa apresentar maior conversão e spend bruto, enquanto o braço de 5% pode produzir maior valor econômico líquido.

## 10. Sanity checks antes de analisar efeito

Verificar:

1. sample ratio por braço;
2. tratamento por campaign_wave;
3. balance das covariáveis pré-treatment;
4. Standardized Mean Differences;
5. missing por braço;
6. overlap das distribuições;
7. taxas de delivery e activation;
8. integridade dos outcomes;
9. presença de outliers.

Não usar p-values de balance como único diagnóstico de randomização.

## 11. Sample size, power e MDE

A solução deve calcular ou estimar:

- baseline conversion rate;
- sample size por braço;
- power;
- MDE para conversão;
- MDE para o KPI econômico principal quando possível.

Importante:

Power e MDE deveriam idealmente ser definidos antes do experimento.

Neste case, como análise retrospectiva, devem ser apresentados como diagnóstico e não como justificativa pós-hoc para significância.

## 12. Estimandos e contrasts

Definir explicitamente:

### Conversão

`ATE_5 = E[Y | cashback_5] - E[Y | control]`

`ATE_10 = E[Y | cashback_10] - E[Y | control]`

### Comparação de intensidades

`ATE_10_vs_5 = E[Y | cashback_10] - E[Y | cashback_5]`

Repetir a lógica para:

- transaction count;
- spend;
- gross margin;
- net margin;
- guardrails.

## 13. Estatística inferencial

Para outcomes binários:

- difference in proportions;
- confidence intervals;
- risk difference;
- relative lift;
- testes apropriados.

Para outcomes contínuos:

- difference in means;
- confidence intervals;
- bootstrap quando apropriado;
- análise robusta em presença de heavy tails.

Não depender exclusivamente de normalidade assintótica para spend e margin sem investigar distribuições.

## 14. CUPED

Usar covariáveis pré-treatment correlacionadas com o outcome.

Principais candidatas:

- `spend_30d_pre`
- `txn_count_30d_pre`
- `gross_margin_30d_pre`

CUPED deve ser aplicado somente com variáveis observadas antes do tratamento.

Comparar:

- variância do estimador sem CUPED;
- variância após CUPED;
- redução percentual de variância.

Não aplicar CUPED a variáveis pós-treatment.

## 15. KPI principal

A recomendação final deve se basear prioritariamente em `net_margin_30d`.

Para cada braço calcular:

- margem líquida média por cliente;
- diferença versus control;
- intervalo de confiança;
- lucro incremental total;
- custo total da campanha;
- ROI.

Uma forma de ROI:

`ROI = Incremental Net Profit / Campaign Cost`

A definição exata deve ser documentada.

## 16. Guardrails

Avaliar:

- complaint rate;
- refund rate e valor;
- chargeback rate e valor;
- churn_60d.

Uma estratégia não deve ser recomendada apenas porque maximiza margem se houver degradação material de segurança, risco ou experiência do cliente.

## 17. Heterogeneous Treatment Effects

Investigar efeitos heterogêneos em dimensões pré-treatment:

- customer_segment;
- merchant versus non-merchant;
- income_band;
- engagement;
- baseline spend;
- price sensitivity proxies;
- historical campaign engagement.

Inicialmente usar análises segmentadas pré-especificadas.

Modelagem causal heterogênea avançada pode ser extensão, mas não deve diluir a análise experimental principal.

## 18. Segmentação de efeitos

Evitar procurar dezenas de subgrupos até encontrar significância.

Definir poucos segmentos com racional de negócio.

Se houver muitas análises exploratórias, rotular como hypothesis generation.

## 19. Análise temporal

O experimento possui sete ondas.

A solução deve analisar estabilidade do efeito por `campaign_wave`.

Uma estratégia recomendada:

- ondas 1 a 5 para exploração e estimativa principal;
- onda 6 para validação temporal;
- onda 7 como holdout temporal/OOT da recomendação final.

Essa divisão não é obrigatória para estimar o ATE global do RCT, mas é útil para avaliar estabilidade e generalização temporal da decisão.

Não escolher a política final olhando repetidamente a onda 7.

## 20. Post-treatment bias

Não ajustar causalmente por:

- `message_delivered`;
- `offer_activated`;
- `post_campaign_app_sessions_7d`;
- `cashback_balance_viewed_7d`;
- `cashback_cost`;
- qualquer outro mediador pós-treatment,

como se fossem covariáveis pré-treatment.

`cashback_cost` e `campaign_contact_cost` são outcomes/custos necessários para a análise econômica, não confundidores.

## 21. Cannibalization

Investigar se o cashback subsidia comportamento que já ocorreria.

A comparação com controle já captura o efeito incremental médio.

Na interpretação, separar:

- gross purchases;
- incremental purchases;
- gross spend;
- incremental spend;
- cashback paid;
- incremental net margin.

Maior spend bruto não implica maior valor incremental.

## 22. Recomendação final

Responder:

1. 5% aumenta conversão?
2. 10% aumenta conversão?
3. 10% aumenta mais que 5%?
4. Qual braço maximiza spend incremental?
5. Qual braço maximiza net margin incremental?
6. Qual braço apresenta melhor ROI?
7. Existem guardrails deteriorados?
8. Os efeitos são estáveis por onda?
9. Existem segmentos com resposta econômica distinta?
10. Qual política deve ser testada/lançada?

## 23. Monitoramento

Após rollout, monitorar:

- assignment;
- delivery;
- activation;
- conversion;
- spend;
- gross margin;
- cashback cost;
- net margin;
- ROI;
- complaints;
- refunds;
- chargebacks;
- churn;
- estabilidade por segmento e coorte.

## 24. Conclusão obrigatória

Finalizar explicitamente com:

> A maior taxa de conversão não implica a melhor decisão econômica. O braço recomendado deve maximizar valor incremental líquido dentro dos guardrails definidos.

---

# INSTRUÇÕES DE IMPLEMENTAÇÃO - CASE 4

Você atuará como Senior Data Scientist responsável por implementar um case técnico completo de experimentação causal aplicado a Growth em Financial Services.

O projeto deve ser desenvolvido como se fosse uma entrega de desafio técnico para uma posição Senior Data Scientist.

## PRINCÍPIO CENTRAL

A solução deve priorizar:

1. desenho experimental;
2. integridade da randomização;
3. causalidade;
4. métricas de negócio;
5. rigor estatístico;
6. variância e poder;
7. impacto econômico;
8. guardrails;
9. heterogeneidade;
10. comunicação executiva.

Evite overengineering.

A primeira versão deve ser integralmente compreensível em UM notebook Jupyter executável de ponta a ponta.

## REPOSITÓRIO

Criar:

`financial-growth-case-04-cashback-experiment`

Estrutura mínima:

```text
README.md
requirements.txt

data/
    raw/

notebooks/
    01_end_to_end_case.ipynb

outputs/
    figures/
    tables/
    metrics/

presentation/

src/
    somente funções reutilizáveis que aumentem a clareza
```

## ARQUIVO DE ENTRADA

Utilizar exclusivamente:

`data/raw/case_04_cashback_experiment_raw.csv`

Não utilizar nenhum arquivo de `private_do_not_use_in_modeling`.

## TRATAMENTOS

`treatment_arm`:

- control
- cashback_5
- cashback_10

A análise principal é Intention-to-Treat.

Não substituir treatment assignment por delivery ou activation.

## ESTRUTURA DO NOTEBOOK

1. Contexto e problema de negócio
2. Hipóteses do experimento
3. Primary KPI e guardrails
4. Unidade de análise
5. Treatment arms
6. Randomization design
7. Outcome window
8. Importação de bibliotecas
9. Seeds
10. Carga da base raw
11. Data Quality Report
12. Tipagem
13. Missing
14. Cardinalidade
15. Outliers
16. Distribuições pré-treatment
17. Sample ratio check
18. Randomization por wave
19. Covariate balance
20. Standardized Mean Differences
21. Non-compliance
22. Post-treatment review
23. Baseline conversion
24. Sample size
25. Power
26. MDE
27. Primary contrasts
28. Multiple testing plan
29. Conversion ATE 5 vs control
30. Conversion ATE 10 vs control
31. Conversion 10 vs 5
32. Transaction frequency effects
33. Spend effects
34. Gross margin effects
35. Cashback cost
36. Net margin effects
37. Confidence intervals
38. Effect sizes
39. Bootstrap para métricas financeiras quando pertinente
40. CUPED em spend
41. CUPED em transaction count
42. CUPED em margin
43. Variance reduction
44. Guardrails
45. Effects by campaign_wave
46. Heterogeneous effects
47. Incremental conversions
48. Incremental spend
49. Incremental gross margin
50. Incremental net margin
51. Total campaign cost
52. ROI
53. Cannibalization interpretation
54. Temporal validation / holdout
55. Recommendation
56. Limitations
57. Monitoring
58. Next steps
59. Executive conclusion

## SANITY CHECKS

Antes de analisar outcomes:

- verificar proporções por braço;
- verificar braços por campaign_wave;
- comparar features pré-treatment;
- calcular SMD;
- verificar missing por braço;
- revisar outliers;
- validar que não existe uso acidental de variáveis pós-treatment.

## PRIMARY KPI

Primary KPI recomendado:

`net_margin_30d`

Métricas secundárias:

- purchased_30d;
- txn_count_30d_post;
- spend_30d_post;
- gross_margin_30d.

Guardrails:

- complaint_30d;
- refund_flag_30d;
- refund_value_30d;
- chargeback_flag_30d;
- chargeback_value_30d;
- churn_60d.

## PRIMARY CONTRASTS

Pré-definir:

1. cashback_5 versus control;
2. cashback_10 versus control;
3. cashback_10 versus cashback_5.

Para cada contrast reportar:

- absolute difference;
- relative difference quando fizer sentido;
- confidence interval;
- p-value;
- effect size.

Aplicar Holm correction aos três contrasts principais quando reportar inferência simultânea.

## POWER E MDE

Calcular:

- baseline conversion;
- n por braço;
- MDE da conversão;
- power para efeitos observados;
- MDE aproximado do KPI econômico quando viável.

Deixar explícito que power pós-hoc não substitui planejamento pré-experimento.

## CUPED

Testar CUPED usando:

- spend_30d_pre para spend_30d_post;
- txn_count_30d_pre para txn_count_30d_post;
- gross_margin_30d_pre para gross_margin_30d ou net_margin_30d.

Calcular theta usando dados pré-treatment de forma consistente.

Mostrar redução de variância.

Não utilizar variável pós-treatment em CUPED.

## ESTATÍSTICA

Para binários:
- difference in proportions;
- confidence intervals.

Para contínuos:
- difference in means;
- robust standard errors ou bootstrap quando necessário.

Investigar heavy tails antes de assumir aproximações inadequadas.

## MULTIPLE TESTING

Distinguir:

- primary KPI;
- secondary metrics;
- guardrails;
- exploratory heterogeneity.

Evitar concluir com base em dezenas de p-values não corrigidos.

## TEMPORAL STABILITY

Analisar efeitos por campaign_wave.

Para robustez temporal, utilizar:

- ondas 1-5 para análise principal;
- onda 6 para validação;
- onda 7 como holdout temporal final.

Não redefinir a política com base no holdout final.

## POST-TREATMENT BIAS

Não usar como covariáveis causais pré-treatment:

- message_delivered;
- offer_activated;
- cashback_cost;
- campaign_contact_cost;
- post_campaign_app_sessions_7d;
- cashback_balance_viewed_7d.

Usar custos pós-treatment apenas na mensuração econômica.

## HETEROGENEITY

Analisar poucos segmentos com justificativa de negócio.

Priorizar:

- customer_segment;
- merchant_flag;
- baseline spend quantiles;
- historical campaign engagement;
- relationship tier.

Rotular análises não pré-especificadas como exploratórias.

## BUSINESS METRICS

Calcular por braço:

- customers assigned;
- purchases;
- conversion rate;
- transactions;
- spend;
- gross margin;
- cashback cost;
- contact cost;
- net margin.

Calcular incremental versus control:

- incremental conversions;
- incremental spend;
- incremental gross margin;
- incremental net margin;
- incremental profit total.

## ROI

Definir explicitamente uma fórmula de ROI.

Uma opção:

`ROI = Incremental Net Profit / Total Campaign Cost`

onde Campaign Cost inclui cashback e custo de comunicação.

Explicar limites dessa definição.

## RECOMMENDATION

A recomendação não deve escolher automaticamente o braço com maior conversion rate.

Priorizar:

1. incremental net margin;
2. ROI;
3. significância e incerteza;
4. guardrails;
5. estabilidade temporal;
6. heterogeneidade relevante.

## APRESENTAÇÃO

Estruturar no máximo cinco slides:

1. Business Problem & Experiment Design
2. Randomization, Power & Data Quality
3. Causal Results & CUPED
4. Incremental Profit, ROI & Guardrails
5. Recommendation, Risks & Next Steps

## CONCLUSÃO OBRIGATÓRIA

Finalizar explicitamente:

"Maior conversão não implica maior valor econômico. A decisão deve ser baseada em lucro incremental líquido, incerteza estatística, guardrails e estabilidade do efeito."
