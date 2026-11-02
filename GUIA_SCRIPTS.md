# Guia de scripts e programas do TAES

Este guia reúne os scripts e CLIs do projeto, com a finalidade de facilitar a execução individual e a compreensão dos parâmetros aceitos por cada etapa da pipeline.

## Visão geral da pipeline

A sequência principal do projeto é:

1. `python FiltroSubmissions.py`
2. `python atCoder_downloader.py`
3. `python taes_pipeline.py problems`
4. `python atcoder_loop.py ...`
5. `python qodana_atcoder.py ...`

Os arquivos mais importantes são:

- `FiltroSubmissions.py` — filtra o dataset bruto do AtCoder Problems
- `atCoder_downloader.py` — baixa as submissões em código-fonte do AtCoder
- `atcoder_loop.py` e `atcoder_loop/cli.py` — executam o loop de geração/validação/submissão
- `qodana_atcoder.py` — compara qualidade de código humano vs. IA com Qodana
- `taes_pipeline.py` — orquestra a pipeline completa em etapas

---

## 1) `FiltroSubmissions.py`

### Descrição

Filtra o dataset bruto de submissões do AtCoder Problems e gera um CSV mais enxuto para uso nas próximas etapas.

### Sintaxe

```bash
python FiltroSubmissions.py \
  --csv submissions.csv \
  --out outputs/01_filter/01_filter_filtered_submissions.csv \
  --contests abc300 abc301 \
  --linguagens Python PyPy \
  --resultados AC \
  --max-por-problema 10 \
  --max-por-contest 100
```

### Parâmetros

- `--csv`: caminho do dataset bruto (padrão: `submissions.csv`)
- `--out`: caminho do CSV filtrado (padrão: `outputs/01_filter/01_filter_filtered_submissions.csv`)
- `--contests`: lista de contests exatos para manter, por exemplo: `abc300 abc301 abc302`
- `--prefixos-contest`: prefixos de contest, por exemplo: `abc arc`
- `--linguagens`: prefixos de linguagem para filtrar, por exemplo: `Python PyPy`
- `--linguagens-exatas`: nomes exatos de linguagem, por exemplo: `"C++ 20 (gcc 12.2)"`
- `--resultados`: resultados a manter, por exemplo: `AC WA RE`
- `--all-results`: ignora filtragem por resultado e mantém todas as submissões
- `--corte`: mantém apenas contests iniciados a partir da data informada, no formato `YYYY-MM-DD`
- `--envio-de`: início da janela de envio, no formato `YYYY-MM-DD` ou `YYYY-MM-DD HH:MM`
- `--envio-ate`: fim da janela de envio, no formato `YYYY-MM-DD` ou `YYYY-MM-DD HH:MM`
- `--max-por-problema`: máximo de submissões por `contest_id + problem_id`
- `--max-por-contest`: máximo de submissões por contest

### Observações

- Se `--all-results` for usado, o valor de `--resultados` é ignorado.
- O script também aceita entrada direta de um arquivo CSV já local, sem precisar baixar o dataset automaticamente.
- A opção `--prefixos-contest` é útil para manter muitos contests de uma família, como `abc`, `arc`, `agc`, etc.

### Exemplos

#### Filtrar somente AC de um intervalo de datas

```bash
python FiltroSubmissions.py \
  --csv submissions.csv \
  --out outputs/01_filter/01_filter_filtered_submissions.csv \
  --prefixos-contest abc arc \
  --linguagens Python PyPy \
  --envio-de 2025-03-01 \
  --envio-ate 2025-03-31 \
  --max-por-problema 10 \
  --max-por-contest 100
```

#### Filtrar apenas alguns contests e todos os resultados

```bash
python FiltroSubmissions.py \
  --csv submissions.csv \
  --contests abc300 abc301 abc302 \
  --linguagens Python PyPy \
  --all-results \
  --max-por-problema 10 \
  --max-por-contest 100
```

---

## 2) `atCoder_downloader.py`

### Descrição

Baixa o código-fonte das submissões do AtCoder e salva em uma árvore de diretórios organizada por contest/problem.

### Sintaxe

```bash
python atCoder_downloader.py \
  --csv outputs/01_filter/01_filter_filtered_submissions.csv \
  --out outputs/02_download/02_download_atcoder_submissions \
  --all
```

### Parâmetros

- `--csv`: CSV com as submissões de entrada. A coluna esperada inclui `id`, `contest_id`, `problem_id`, `language`, `result`
- `--out`: pasta de saída para a árvore de submissões, padrão: `outputs/02_download/02_download_atcoder_submissions`
- `--all`: baixa também submissões com resultado diferente de `AC` (quando não informado, somente AC são baixadas)
- `--contest`: filtra um único contest por ID ou parte do nome, por exemplo `abc300` ou `Beginner Contest 300`
- `--list-contests`: lista os contests presentes no CSV e encerra a execução

### Saída gerada

O script cria:

- uma pasta por contest
- uma pasta por problema
- arquivos do tipo `sub_id_verdict.ext`
- um CSV de metadados, por exemplo:
  - `02_download_atcoder_submissions_metadata.csv`
  - `02_download_atcoder_submissions_problems.csv`

### Exemplos

#### Baixar somente AC

```bash
python atCoder_downloader.py \
  --csv outputs/01_filter/01_filter_filtered_submissions.csv \
  --out outputs/02_download/02_download_atcoder_submissions
```

#### Baixar tudo, inclusive WA/TLE/RE

```bash
python atCoder_downloader.py \
  --csv outputs/01_filter/01_filter_filtered_submissions.csv \
  --out outputs/02_download/02_download_atcoder_submissions \
  --all
```

#### Listar contests disponíveis no CSV

```bash
python atCoder_downloader.py \
  --csv outputs/01_filter/01_filter_filtered_submissions.csv \
  --list-contests
```

---

## 3) `atcoder_loop.py` / `atcoder_loop/cli.py`

### Descrição

Lê um CSV com `problem_id`, usa um LLM para gerar soluções, tenta submetê-las no AtCoder e salva resultados em CSV + arquivos de solução.

### Sintaxe

```bash
python atcoder_loop.py outputs/03_loop/03_loop_problems.csv \
  --out outputs/03_loop/03_loop_resultados.csv \
  --out-dir outputs/03_loop/03_loop_solucoes \
  --provider google \
  --model gemini-3.8-flash
```

### Parâmetros

Posicional:

- `csv`: arquivo com uma coluna `problem_id` (ex.: `abc300_a`)

Opcionais:

- `--out`: CSV de saída com os resultados do loop, padrão: `outputs/03_loop/03_loop_resultados.csv`
- `--out-dir`: diretório para salvar as soluções geradas, padrão: `outputs/03_loop/03_loop_solucoes`
- `--provider`: provedor do modelo: `openai` ou `google` (padrão: `google`)
- `--model`: nome do modelo, por exemplo: `gemini-3.8-flash` ou `gpt-4o`
- `--temperature`: temperatura usada pelo LLM (padrão: `1.0`)
- `--max-tokens`: limite de tokens da resposta (padrão: `4096`)
- `--atcoder-session-cookie`: cookie de sessão autenticada do AtCoder para submissão real
- `--no-resume`: ignora o sistema de retomada e reprocessa problemas já resolvidos
- `-v`, `--verbose`: habilita logs detalhados

### Variáveis de ambiente esperadas

O script usa credenciais do modelo em `.env` ou no ambiente:

```env
GOOGLE_API_KEY=sua_chave_google
# ou
OPENAI_API_KEY=sua_chave_openai
```

Para autenticar no AtCoder:

```env
ATCODER_SESSION_COOKIE=REVEL_SESSION=SEU_VALOR_DO_COOKIE
```

### Exemplos

#### Com Google Gemini

```bash
python atcoder_loop.py outputs/03_loop/03_loop_problems.csv \
  --out outputs/03_loop/03_loop_resultados.csv \
  --out-dir outputs/03_loop/03_loop_solucoes \
  --provider google \
  --model gemini-3.8-flash \
  --atcoder-session-cookie "REVEL_SESSION=SEU_VALOR_DO_COOKIE"
```

#### Com OpenAI

```bash
python atcoder_loop.py outputs/03_loop/03_loop_problems.csv \
  --out outputs/03_loop/03_loop_resultados.csv \
  --out-dir outputs/03_loop/03_loop_solucoes \
  --provider openai \
  --model gpt-4o \
  --temperature 0.7 \
  --max-tokens 8192
```

### Observações

- O CSV de entrada precisa conter uma coluna chamada `problem_id`.
- O contest é inferido a partir do prefixo antes do último `_` do ID; por exemplo, `abc300_a` vira contest `abc300`.
- O fluxo pode reaproveitar resultados anteriores por padrão (modo resume), a menos que `--no-resume` seja usado.

---

## 4) `qodana_atcoder.py`

### Descrição

Compara padrões de código entre submissões humanas e submissões geradas por IA usando Qodana (Python/C++), agregando métricas por problema, origem e linguagem.

### Sintaxe

```bash
python qodana_atcoder.py \
  outputs/02_download/02_download_atcoder_submissions \
  --rules-python rules_py.txt \
  --rules-cpp rules_cpp.txt \
  --linter-python jetbrains/qodana-python-community:2026.2 \
  --linter-cpp jetbrains/qodana-clang:2026.2 \
  --out outputs/04_qodana/04_qodana_relatorio
```

### Parâmetros

Posicional:

- `root`: pasta raiz contendo as pastas de origem, como `AtCoder` e `IA`

Opcionais:

- `--sources`: mapeamento `pasta=label`, separado por vírgula. Padrão: `AtCoder=humano,IA=IA`
- `--rules-python`: arquivo com as regras de inspeção para Python, um ID por linha
- `--rules-cpp`: arquivo com as regras de inspeção para C/C++, um ID por linha
- `--linter-python`: imagem do linter Python do Qodana
- `--linter-cpp`: imagem do linter C/C++ do Qodana
- `--c-std`: padrão para C, exemplo: `c17`
- `--cpp-std`: padrão para C++, exemplo: `c++20`
- `--cpp-flags`: flags extras do compilador, por exemplo: `-I/path/to/ac-library`
- `--container-root`: caminho da pasta do projeto dentro do container Docker
- `--layout`: estrutura de pastas acima do arquivo, padrão: `contest,problem`
- `--scope`: `contest` ou `all` (padrão: `contest`)
- `--out`: prefixo dos CSVs de saída
- `--results-root`: diretório onde as saídas temporárias do Qodana serão armazenadas

### Arquivos gerados

O script produz:

- `<out>_submissoes.csv`
- `<out>_resumo.csv`
- `<out>_comparacao.csv`

### Exemplos

#### Comparação padrão entre humano e IA

```bash
python qodana_atcoder.py \
  outputs/02_download/02_download_atcoder_submissions \
  --sources AtCoder=humano,IA=IA \
  --rules-python rules_py.txt \
  --rules-cpp rules_cpp.txt \
  --linter-python jetbrains/qodana-python-community:2026.2 \
  --linter-cpp jetbrains/qodana-clang:2026.2 \
  --out outputs/04_qodana/04_qodana_relatorio
```

#### Rodar o Qodana com uma estrutura de pastas diferente

```bash
python qodana_atcoder.py \
  ./dados \
  --sources meu_dataset=humano,IA=IA \
  --rules-python rules_py.txt \
  --layout contest,problem \
  --scope contest \
  --out outputs/04_qodana/relatorio
```

### Observações

- O Qodana exige que o diretório fornecido seja um projeto válido e que o repositório tenha um `git` inicializado em alguns cenários.
- O script usa um profile vazio do Qodana para rodar apenas as regras listadas em `rules_py.txt` e `rules_cpp.txt`.
- A pasta `rules_py.txt` e `rules_cpp.txt` deve conter um ID de inspeção por linha; linhas em branco e comentários com `#` são ignorados.

---

## 5) `taes_pipeline.py`

### Descrição

Orquestra a pipeline completa em subcomandos. É o entrypoint mais simples para rodar fases do fluxo inteiro, em vez de executar cada script separadamente.

### Subcomandos

#### `filter`

```bash
python taes_pipeline.py filter \
  --csv submissions.csv \
  --out outputs/01_filter/01_filter_filtered_submissions.csv \
  --contests abc300 abc301 \
  --linguagens Python PyPy \
  --resultados AC
```

Parâmetros:

- `--csv`, `--out`, `--contests`, `--prefixos-contest`, `--linguagens`, `--linguagens-exatas`, `--resultados`, `--all-results`, `--corte`, `--envio-de`, `--envio-ate`

#### `download`

```bash
python taes_pipeline.py download \
  --input outputs/01_filter/01_filter_filtered_submissions.csv \
  --out outputs/02_download/02_download_atcoder_submissions \
  --all-results
```

Parâmetros:

- `--input`
- `--out`
- `--all-results`

#### `problems`

```bash
python taes_pipeline.py problems \
  --input outputs/01_filter/01_filter_filtered_submissions.csv \
  --out outputs/03_loop/03_loop_problems.csv
```

Parâmetros:

- `--input`
- `--out`

#### `loop`

```bash
python taes_pipeline.py loop \
  --input outputs/03_loop/03_loop_problems.csv \
  --out outputs/03_loop/03_loop_resultados.csv \
  --out-dir outputs/03_loop/03_loop_solucoes \
  --provider google \
  --model gemini-3.8-flash
```

Parâmetros:

- `--input`
- `--out`
- `--out-dir`
- `--provider` (`openai` ou `google`)
- `--model`
- `--temperature`
- `--max-tokens`
- `--no-resume`

#### `qodana`

```bash
python taes_pipeline.py qodana \
  outputs/02_download/02_download_atcoder_submissions \
  --rules-python rules_py.txt \
  --rules-cpp rules_cpp.txt \
  --linter-python jetbrains/qodana-python-community:2026.2 \
  --linter-cpp jetbrains/qodana-clang:2026.2 \
  --out outputs/04_qodana/04_qodana_relatorio
```

Parâmetros:

- `--root`
- `--sources`
- `--rules-python`
- `--rules-cpp`
- `--linter-python`
- `--linter-cpp`
- `--out`

#### `all`

Executa a pipeline inteira em sequência:

```bash
python taes_pipeline.py all \
  --raw-csv submissions.csv \
  --out-dir outputs/00_pipeline \
  --contests abc300 abc301 \
  --linguagens Python PyPy \
  --resultados AC \
  --loop-provider google \
  --loop-model gemini-3.8-flash \
  --with-qodana \
  --rules-python rules_py.txt \
  --rules-cpp rules_cpp.txt
```

Parâmetros importantes:

- `--raw-csv`
- `--out-dir`
- `--contests`, `--prefixos-contest`, `--linguagens`, `--linguagens-exatas`
- `--resultados`, `--all-results`
- `--corte`, `--envio-de`, `--envio-ate`
- `--loop-provider`, `--loop-model`, `--loop-temperature`, `--loop-max-tokens`, `--no-loop-resume`
- `--with-qodana`, `--rules-python`, `--rules-cpp`, `--linter-python`, `--linter-cpp`

---

## 6) Exemplos de uso com a pipeline completa

### Fluxo manual recommended

```bash
python FiltroSubmissions.py \
  --csv submissions.csv \
  --out outputs/01_filter/01_filter_filtered_submissions.csv \
  --prefixos-contest abc arc \
  --linguagens Python PyPy \
  --envio-de 2025-03-01 \
  --envio-ate 2025-03-31 \
  --max-por-problema 10 \
  --max-por-contest 100

python atCoder_downloader.py \
  --csv outputs/01_filter/01_filter_filtered_submissions.csv \
  --out outputs/02_download/02_download_atcoder_submissions \
  --all

python taes_pipeline.py problems \
  --input outputs/01_filter/01_filter_filtered_submissions.csv \
  --out outputs/03_loop/03_loop_problems.csv

python atcoder_loop.py outputs/03_loop/03_loop_problems.csv \
  --out outputs/03_loop/03_loop_resultados.csv \
  --out-dir outputs/03_loop/03_loop_solucoes \
  --provider google \
  --model gemini-3.8-flash

python qodana_atcoder.py \
  outputs/02_download/02_download_atcoder_submissions \
  --rules-python rules_py.txt \
  --rules-cpp rules_cpp.txt \
  --linter-python jetbrains/qodana-python-community:2026.2 \
  --linter-cpp jetbrains/qodana-clang:2026.2 \
  --out outputs/04_qodana/04_qodana_relatorio
```

### Fluxo via `taes_pipeline.py all`

```bash
python taes_pipeline.py all \
  --raw-csv submissions.csv \
  --out-dir outputs/00_pipeline \
  --prefixos-contest abc arc \
  --linguagens Python PyPy \
  --resultados AC \
  --loop-provider google \
  --loop-model gemini-3.8-flash \
  --with-qodana \
  --rules-python rules_py.txt \
  --rules-cpp rules_cpp.txt
```
---

## Dicas úteis

- Mantenha o arquivo `.env` na raiz do projeto com as chaves essenciais, como `GOOGLE_API_KEY`, `OPENAI_API_KEY` e `ATCODER_SESSION_COOKIE`.
- A pasta de saída precisa existir ou será criada automaticamente pelo script.
- Se a execução do AtCoder Loop falhar por autenticação, verifique se a sessão do AtCoder ainda está válida e se `--atcoder-session-cookie` foi informado corretamente.
- Para começar do zero, remova os arquivos de saída antigos e rode novamente a pipeline.

---

## Arquivos de referência do projeto

- `.env.example` — exemplo de variáveis de ambiente
- `rules_py.txt` — regras de inspeção do Qodana para Python
- `rules_cpp.txt` — regras de inspeção do Qodana para C++
- `submissions.csv` — dataset bruto do AtCoder Problems

Se você quiser, posso transformar este guia em uma versão mais curta, com uma tabela centralizada de parâmetros por script, ou em um README mais visual e profissional.
