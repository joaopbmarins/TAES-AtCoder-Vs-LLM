# TAES-AtCoder-Vs-LLM

Projeto organizado em scripts independentes, executados manualmente em sequência.

## Fluxo oficial

1. `python FiltroSubmissions.py`
2. `python atCoder_downloader.py`
3. `python taes_pipeline.py problems`
4. `python atcoder_loop.py ...`
5. `python taes_pipeline.py ai-layout` (copia as soluções AC da IA para `outputs/02_download/IA/`)
6. `python qodana_atcoder.py outputs/02_download ...` (a raiz precisa conter `AtCoder/` e `IA/`)

> O helper `taes_pipeline.py all` continua disponível como utilitário opcional, mas o fluxo principal é a execução manual etapa por etapa.

## Estrutura de saída

Todos os artefatos ficam em `outputs/`:

```text
outputs/
├── 00_pipeline/
├── 01_filter/
│   └── 01_filter_filtered_submissions.csv
├── 02_download/
│   └── AtCoder/
├── 03_loop/
│   ├── 03_loop_problems.csv
│   ├── 03_loop_resultados.csv
│   └── 03_loop_solucoes/
└── 04_qodana/
    ├── 04_qodana_relatorio_*.csv
    └── 04_qodana_results/
```

Cada script cria sua pasta de saída quando executado; não há bootstrap obrigatório.

## Execução

```bash
# 1) filtrar o dataset bruto
python FiltroSubmissions.py \
  --csv submissions.csv \
  --out outputs/01_filter/01_filter_filtered_submissions.csv \
  --prefixos-contest abc arc \
  --linguagens Python PyPy \
  --envio-de 2025-03-01 \
  --envio-ate 2025-03-31 \
  --max-por-problema 10 \
  --max-por-contest 100

# OU

python FiltroSubmissions.py \
  --csv submissions.csv \
  --contests abc300 abc301 abc302 \
  --linguagens Python PyPy \
  --resultados AC \
  --max-por-problema 10 \
  --max-por-contest 100

# Se um contest tiver 10 problemas, o limite de 10 por problema resulta em ~100 submissões por contest.

# 2) baixar as submissões
python atCoder_downloader.py \
  --csv outputs/01_filter/01_filter_filtered_submissions.csv \
  --out outputs/02_download/AtCoder \
  --all
# gera também outputs/02_download/AtCoder/02_download_atcoder_submissions_problems.csv
# com as colunas: contest, problem, problem_id, url, submissions_count

# 3) exportar problem_id
python taes_pipeline.py problems \
  --input outputs/01_filter/01_filter_filtered_submissions.csv \
  --out outputs/03_loop/03_loop_problems.csv

# 4) executar o loop
# sem passar arquivo, o atcoder_loop usa automaticamente o CSV da etapa 2
python atcoder_loop.py \
  --out outputs/03_loop/03_loop_resultados.csv \
  --out-dir outputs/03_loop/03_loop_solucoes \
  --provider google \
  --model gemini-3.8-flash

# exemplo usando NVIDIA NIM / API de modelos
python atcoder_loop.py outputs/03_loop/03_loop_problems.csv \
  --out outputs/03_loop/03_loop_resultados.csv \
  --out-dir outputs/03_loop/03_loop_solucoes \
  --provider nvidia \
  --model meta/llama-3.1-70b-instruct

# ou explícito:
python atcoder_loop.py outputs/03_loop/03_loop_problems.csv \
  --out outputs/03_loop/03_loop_resultados.csv \
  --out-dir outputs/03_loop/03_loop_solucoes \
  --provider google \
  --model gemini-3.8-flash

# 5) organizar as soluções da IA no layout esperado pelo Qodana
python taes_pipeline.py ai-layout

# 6) comparar humano x IA com Qodana
python qodana_atcoder.py \
  outputs/02_download \
  --rules-python rules_py.txt \
  --rules-cpp rules_cpp.txt \
  --linter-python jetbrains/qodana-python-community:2026.2 \
  --linter-cpp jetbrains/qodana-clang:2026.2 \
  --out outputs/04_qodana/04_qodana_relatorio
```

## Notas de metodologia

- **Checagem local:** antes de cada submissão, o código é validado (sintaxe) e executado nos exemplos do enunciado (`LOCAL_PRECHECK` em `config.py`). Falhas locais viram feedback de reparo (traceback, saída esperada x obtida) e **não** gastam submissão no AtCoder; o `verdict` desse caso vem de execução local (campo `source` no log da tentativa).
- **Feedback do AtCoder:** só o veredito (e tempo/memória); o caso de teste não é revelado.
- **Linguagem:** a submissão usa CPython por padrão; fixe outra com `ATCODER_LANGUAGE` (substring do rótulo, ex.: `CPython 3.11`). Filtre os humanos com a mesma versão (`--linguagens-exatas`) para comparar tempo/memória.
- **Amostragem humana:** os caps do filtro são aleatórios e reprodutíveis (`--seed`).
- **Qodana:** por padrão só arquivos humanos AC entram (`--include-non-ac` desfaz). Linhas = código sem brancos/comentários.
- **Grafos:** `--graph default|dummy` no CLI (o `dummy` grava veredito `DUMMY`, nunca `AC`). `RECURSION_LIMIT` em `config.py` controla o limite de passos do LangGraph.

## Seleção do grafo

Os grafos disponíveis ficam em `atcoder_loop/config.py` via a variável `GRAPH_NAME`.

```python
GRAPH_NAME = "default"  # opções: default, dummy
```

- `default`: mantém o grafo atual do projeto.
- `dummy`: exemplo mínimo para mostrar como incluir um novo grafo sem mexer no fluxo principal.

Para adicionar outro grafo, crie um módulo em `atcoder_loop/graphs/` (por exemplo, `default.py` ou `dummy.py`), defina ali a função `build_<nome>_graph()` e os prompts específicos, e registre a chave correspondente em `build_graph()` em `atcoder_loop/graph.py`.

## Credenciais do AtCoder

A autenticação do projeto usa o cookie de sessão do navegador do AtCoder. O fluxo recomendado é:

1. abrir o AtCoder no navegador já autenticado;
2. copiar o valor do cookie `REVEL_SESSION` ou o bloco completo de cookies do domínio `atcoder.jp`;
3. guardar em `.env` na raiz do projeto:

```env
ATCODER_SESSION_COOKIE=REVEL_SESSION=SEU_VALOR_DO_COOKIE
# ou, alternativamente:
# ATCODER_COOKIES=REVEL_SESSION=SEU_VALOR_DO_COOKIE; outros_cookies=valor
```

Também é possível passar diretamente no comando:

```bash
python -m atcoder_loop.cli problems.csv --atcoder-session-cookie "REVEL_SESSION=SEU_VALOR_DO_COOKIE"
```

Essa é a forma oficial e mais confiável de autenticar a submissão real no AtCoder.

## Arquivos de exemplo

- `submissions.csv` — dataset bruto do AtCoder Problems (baixado automaticamente se não existir)

