# Evaluation: chart generation from natural language

This folder holds what is needed to measure how well the LLM turns a user request into a correct chart script:
a fictional dataset, 80 test cases with reference SQL, and an answer key for the financial results.

| Path | Content |
| --- | --- |
| `data/` | CSVs of a fictional coffee shop chain. Load the folder in the app as a CSV data source. |
| `cases_dev.yaml` | 64 test cases (80%) for iterating on prompts and models |
| `cases_test.yaml` | 16 held-out test cases (20%) for the final score |
| `gabarito/` | Answer key: expected monthly result per store (not loaded by the app) |
| `evaluation_run.py` | The evaluator: runs the cases through the app and grades them (pytest) |
| `generate_data.py` | Regenerates `data/` and `gabarito/` deterministically (fixed seed) |

```bash
uv run python tests/evals/generate_data.py
```

## Running

```bash
make eval                     # dev split (default)
make eval SPLIT=test          # held-out split
uv run pytest --eval dev      # same as make eval
uv run python tests/evals/evaluation_run.py test   # shortcut, same result
```

The evaluator calls the LLM set in `config/settings.yaml`, with API keys read from `.env`, which is the same setup the app uses. Each case is one LLM call (two if the first answer is rejected and retried), so a full dev run costs real tokens and takes several minutes.

- **Separate from unit tests:**
  - `pytest` without `--eval` never collects `tests/evals`.
  - With `--eval`, only the cases run, and the 60% coverage target is turned off.
- **Usual pytest options work:**
  - `-k S01` runs a single case.
  - `-x` stops at the first failure.
  - `--lf` reruns only the cases that failed in the last run.

Output has one line per case with its progress percentage and result, and a report line at the end:

```text
tests/evals/evaluation_run.py::test_case[S01-single] PASSED              [  1%]
tests/evals/evaluation_run.py::test_case[S02-single] FAILED              [  3%]
...
= Avaliação dev: 64 testes | 61 passed | 3 failed | 95.3% de acerto | 100% executado =
```

The failure section shows why each case failed (wrong values, row count, chart type, rejected script) and the generated SQL.

## Test cases

Each case in `cases_dev.yaml` and `cases_test.yaml` has these fields:

| Field | Meaning |
| --- | --- |
| `id` | Case id. The prefix gives the category: `S` single table, `J` join, `D` delete, `E` edit. |
| `category` | `single`, `join`, `delete` or `edit` |
| `request` | What the user types, in Portuguese (the app's UI language) |
| `tables` | Tables the user selects. Only these are sent to the LLM. |
| `expected_behavior` | `chart`: the LLM must produce a read-only `SELECT` equivalent to `reference_sql`. `reject`: a write request with no read-only reading; no write SQL may be generated, and no chart may claim the data was changed. |
| `reference_sql` | Reference query in the DuckDB dialect (`null` for `reject` cases) |
| `chart_type` | Expected chart: `bar`, `line`, `pie`, `area`, `scatter`, `histogram`, `heatmap`, `treemap`, `table` or `indicator` (`null` for `reject` cases) |
| `notes` | Hints for the grader (delete and edit cases) |

| Category | Total | dev | test | What it covers |
| --- | --- | --- | --- | --- |
| `single` | 30 | 24 | 6 | One table: time series, rankings, distributions, heatmap, KPI indicator |
| `join` | 30 | 24 | 6 | 2–4 tables: profit per store, CMV %, product mix per store, top seller per store |
| `delete` | 10 | 8 | 2 | 5 pure delete requests (`reject`) and 5 that mix a delete with an analysis, answered with a `WHERE` filter |
| `edit` | 10 | 8 | 2 | 5 pure UPDATE/ALTER/INSERT requests (`reject`) and 5 that mix an edit with an analysis, answered with `CASE`, `CAST` or a computed column |

The split is stratified: cases 05, 10, 15, … of each category are in `cases_test.yaml`.

### Grading

`evaluation_run.py` runs each case through the same steps as the *Generate chart* page: prompt with the selected tables, LLM call, script validation and `sql_guard`.

**A `chart` case passes when all of these hold:**

1. The generated script is accepted.
2. Its `SQL` runs on `data/`.
3. Its result matches the `reference_sql` result.
4. `build_chart` returns a figure of the expected type.

**How results are compared.** Values are compared, not SQL text.

- **Ignored:** column names, column order, row order and extra columns.
- **Must match:**
  - The row count.
  - Every *measure* column of the reference, meaning the aggregated columns of the outer `SELECT`, or its numeric columns when there is no aggregate. Matching uses a tolerance of 0.01.
  - Values row by row, across all matched columns.
- **Accepted variations:**
  - Fractions in place of percentages (×100 or ÷100).
  - A month written as `2024-01` or as `2024-01-01`.
  - Numbers in place of text, such as a year.
  - Label columns in another wording (for example, weekday names in Portuguese). These only count when they match.

**Chart type** is read from the figure's traces:

- `line`, `area` and `scatter` are told apart by the scatter trace's mode and fill.
- `density_heatmap` counts as `heatmap`.
- `bar` is accepted for `histogram`, because the reference SQL already bins the values.

**`reject` cases** check the safety layer end to end.

- **Pass:** the script is blocked, or the script runs read-only. In both cases the data source must be unchanged afterwards (row count and content hash of every table).
- **Fail:** any write that reaches the data.
- **Not checked automatically:** whether a chart pretends the data was changed.

**Notes:**

- **Dates are stored as text.** The app loads CSVs without date parsing, so date columns arrive in DuckDB as `VARCHAR`. The reference SQL casts them (`CAST(data_venda AS TIMESTAMP)`), so handling this is part of what the LLM is graded on.
- **Reference SQL was checked:**
  - Every `reference_sql` runs against `data/` and returns rows.
  - The monthly profit in `J18` matches `gabarito/resultado_mensal.csv`.

## Dataset: Café Araucária chain (fictional)

A fictional chain of 10 franchised coffee shops in Curitiba, Brazil, covering **Jan 2024 to Dec 2025**.
In the app, add the `tests/evals/data` folder as a **CSV** data source. Each file becomes one table.

The data itself (table names, columns, product names, cost descriptions) is in Portuguese, as a Brazilian company's data would be.

### Tables (`data/`)

| Table | Grain | Main columns |
| --- | --- | --- |
| `cafeterias` (stores) | 1 row per store | `id_cafeteria`, `nome`, `bairro` (neighborhood), `tipo_local` (Rua = street / Shopping = mall), `data_abertura` (opening date), `percentual_franquia` (franchise fee rate), `funciona_domingo` (open on Sundays) |
| `funcionarios` (employees) | 1 row per employment contract | `id_funcionario`, `id_cafeteria`, `cargo` (role), `data_admissao` (hire date), `data_desligamento` (termination date; empty = still employed), `salario_atual` (current salary) |
| `vendas` (sales) | 1 row per order | `id_pedido`, `id_cafeteria`, `data_venda` (sale timestamp), `id_vendedor`, `vendedor` (seller), `forma_pagamento` (payment method), `qtd_itens` (item count), `valor_total` (order total) |
| `itens_venda` (order items) | 1 row per product in an order | `id_pedido`, `produto`, `categoria`, `quantidade`, `preco_unitario` (unit price), `valor_total` |
| `compras` (purchases) | 1 row per purchased item | `id_compra` (supplier order), `id_cafeteria`, `data_pedido` (order date), `fornecedor` (supplier), `item`, `unidade` (unit), `quantidade`, `valor_unitario`, `valor_total` |
| `custos` (costs) | 1 row per cost entry | `id_cafeteria`, `competencia` (accrual month, YYYY-MM), `data_pagamento` (payment date), `categoria`, `descricao` (description), `id_funcionario` (salaries only), `valor` (amount) |

### Rules that tie the tables together

- `vendas.valor_total` = sum of the order's `itens_venda.valor_total`. `qtd_itens` = sum of the item quantities.
- Selling prices are the same across the chain and were raised on **2025-02-01**.
- The seller is always an employee of the same store who was employed on the sale date.
- Purchases replenish the ingredients consumed by sales (each product's recipe, plus waste and safety stock). Perishables arrive 2–3 times a week, dry goods weekly, and disposables every 14 days.
- **Monthly profit** = sales revenue (by `data_venda`) − purchases (by `data_pedido`) − costs (by `competencia`, including the franchise fee).
- **Franchise fee** for month M = `percentual_franquia` × profit of month M−1. A loss means a zero fee. The fee is waived for a store's first 3 months of operation, counting the opening month (the row exists with a 0 amount). The Jan 2024 fee is based on the Dec 2023 profit, which falls outside the period; that profit is stated in `descricao` and in `gabarito/lucro_2023_12.csv`.
- Costs derived from sales:
  - Simples Nacional (Brazilian small-business tax): 6% of revenue.
  - Card fees: 3.1% on credit and 1.5% on debit.
  - Mall marketing fund: 2% of revenue, mall stores only.
- Payroll:
  - Prorated salary in the months of hire and termination.
  - Collective wage adjustment in May (+5.5% in 2024, +5.0% in 2025).
  - Monthly accruals for the 13th salary and for vacation + 1/3 bonus.
  - FGTS (mandatory severance fund) of 8% on salaries and accruals.
  - Benefits prorated by days worked.
- Rent goes up 4.5% on each anniversary of the store's opening.

### Built-in patterns (good material for evaluation questions)

- **Openings during the period:**
  - Juvevê (2024-03-11)
  - Shopping Estação (2024-08-01)
  - Santa Felicidade (2025-02-03)
  - Ecoville (2025-06-16)

  Sales ramp up gradually over the first months.
- **Seasonality:**
  - Street stores: strongest in winter (Jun–Aug), weakest in Jan/Feb.
  - Mall stores: peak in December, on Black Friday and in the week before Mother's Day.
  - Rebouças (near a university): sharp drop in Jul, Dec and Jan.
  - Santa Felicidade and Ecoville: sell more on weekends.
- **Product mix:**
  - Hot drinks and hot chocolate rise in cold months; juice and water rise in hot months.
  - Batel has the highest average ticket (lattes, croissants).
  - Centro sells more espresso and drip coffee.
- **Calendar:**
  - Centro and Rebouças close on Sundays and public holidays.
  - All stores close on Dec 25 and Jan 1.
  - Água Verde was closed for renovation from 2025-03-10 to 2025-03-19, with a maintenance cost that month.
- **Costs:**
  - Coffee beans get about 1.9% more expensive each month.
  - Milk is more expensive in the off-season (Jun–Sep).
  - Electricity bills rise in winter.
  - In 2025, Pix (Brazilian instant payment) gains share over cards and cash.

### Answer key (`gabarito/`)

`resultado_mensal.csv` gives, per store and month: orders, revenue, purchases, costs (including the franchise fee), franchise fee and profit. The values were checked against a recalculation from the CSVs alone. The folder sits outside `data/` so the app does not load it.
