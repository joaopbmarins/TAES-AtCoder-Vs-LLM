# TAES AtCoder vs LLM

Pipeline para comparar soluções humanas do AtCoder com soluções geradas por
LLM. O fluxo filtra submissões do AtCoder, baixa os códigos humanos, gera uma
solução para cada problema e registra o veredicto obtido no AtCoder.

## Experimento principal

O experimento usado como referência neste projeto foi executado em duas
partes: seleção dos dados e geração/submissão das soluções.

### 1. Selecionar os 17 problemas

No Windows (PowerShell):

```powershell
.\.venv\Scripts\taes-pipeline.exe filter `
  --linguagens Python PyPy `
  --resultados AC `
  --contests abc399 arc195 agc071 `
  --max-por-problema 5 `
  --max-por-contest 50
```

O comando baixa `submissions.csv.gz` automaticamente se o dataset ainda não
existir. Para usar um arquivo local, acrescente `--csv caminho\submissions.csv`.

No Linux:

```bash
taes-pipeline filter \
  --linguagens Python PyPy \
  --resultados AC \
  --contests abc399 arc195 agc071 \
  --max-por-problema 5 \
  --max-por-contest 50
```

Para usar um arquivo local, acrescente `--csv caminho/submissions.csv`.

Essa configuração produziu 73 submissões humanas e 17 problemas únicos. Os
arquivos principais dessa etapa são:

```text
outputs/01_filter/01_filter_filtered_submissions.csv
outputs/02_download/AtCoder/02_download_atcoder_submissions_metadata.csv
outputs/02_download/AtCoder/02_download_atcoder_submissions_problems.csv
```

### 2. Baixar, gerar e avaliar

Windows (PowerShell):

```powershell
.\.venv\Scripts\taes-pipeline.exe download
.\.venv\Scripts\taes-pipeline.exe problems

.\.venv\Scripts\taes-loop.exe `
  --provider google `
  --model gemini-3.8-flash `
  --out outputs/03_loop/03_loop_resultados.csv `
  --out-dir outputs/03_loop/03_loop_solucoes
```

Linux:

```bash
taes-pipeline download
taes-pipeline problems

taes-loop \
  --provider google \
  --model gemini-3.8-flash \
  --out outputs/03_loop/03_loop_resultados.csv \
  --out-dir outputs/03_loop/03_loop_solucoes
```

O loop usa o grafo `default` por padrão. Ele coleta o enunciado no AtCoder,
gera o código, executa uma pré-validação local com os exemplos e submete o
código. Em caso de falha, pode gerar uma correção até o limite configurado.
É necessário definir `GOOGLE_API_KEY` no `.env` e ter uma sessão autenticada
do AtCoder para submissões reais.

Os resultados ficam em:

```text
outputs/03_loop/03_loop_resultados.csv
outputs/03_loop/03_loop_resultados_erros.csv
outputs/03_loop/03_loop_solucoes/
```

No estado registrado no repositório, os 17 problemas resultaram em 9 `AC`,
6 `WA` e 2 `TLE`.

### Análise opcional com Qodana

Depois de preparar o layout humano/IA:

```powershell
.\.venv\Scripts\taes-pipeline.exe ai-layout
.\.venv\Scripts\taes-qodana.exe outputs/02_download `
  --rules-python rules_py.txt `
  --rules-cpp rules_cpp.txt
```

Linux:

```bash
taes-pipeline ai-layout
taes-qodana outputs/02_download \
  --rules-python rules_py.txt \
  --rules-cpp rules_cpp.txt
```

Essa etapa compara os diagnósticos estáticos dos códigos humanos e gerados.
Ela requer o ambiente do Qodana/Docker configurado na máquina.

## Instalação e execução por sistema

Use Python 3.10–3.14. Python 3.15 ainda pode não ter wheels compatíveis para
dependências nativas usadas pelas integrações.

Windows (PowerShell):

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\Activate.ps1
```

Linux:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Copie [`.env.example`](./.env.example) para `.env` e preencha as credenciais
do provider escolhido:

```text
GOOGLE_API_KEY=...
OPENAI_API_KEY=...
NVIDIA_API_KEY=...
```

## Arquitetura

```text
taes/
├── pipeline/       Filtragem do dataset e preparação dos dados
├── atcoder/        Download de submissões, metadados e problemas
├── loop/
│   ├── engine/     Grafos LangGraph e execução por problema
│   ├── integrations/
│   │   ├── llm.py      Providers e contagem de uso
│   │   ├── scraper.py  Enunciados e exemplos do AtCoder
│   │   └── judge.py    Validação e submissão
│   └── validation/ Checagem local dos exemplos
├── analysis/       Relatórios e comparação com Qodana
├── storage/        Leitura e escrita dos CSVs e tentativas
├── cli/            Orquestração dos comandos da pipeline
└── core/           Configuração, modelos e caminhos padrão
```

O fluxo de dados é:

```text
submissions.csv.gz
        │
        ▼
01_filter/filtered_submissions.csv
        │
        ├──► 02_download/AtCoder/   códigos e metadados humanos
        │
        └──► 03_loop/problems.csv
                    │
                    ▼
              scraping → LLM → pré-validação → AtCoder
                    │
                    ▼
              03_loop/resultados.csv e soluções aceitas
```

O grafo `default` é o fluxo principal. O projeto também possui o grafo
`multiagent`, com Planner, Coder, Test Agent e Validator, e o grafo `dummy`
para testes. Para selecionar outro grafo:

```powershell
.\.venv\Scripts\taes-loop.exe `
  --graph multiagent `
  --provider google `
  --model gemini-3.8-flash
```

## Comandos úteis

Windows (PowerShell):

```powershell
.\.venv\Scripts\taes-pipeline.exe --help
.\.venv\Scripts\taes-pipeline.exe filter --help
.\.venv\Scripts\taes-loop.exe --help
python -m pytest
ruff check taes tests
python -m compileall -q taes
```

Linux:

```bash
taes-pipeline --help
taes-pipeline filter --help
taes-loop --help
pytest
ruff check taes tests
python -m compileall -q taes
```

As etapas são retomáveis: downloads consultam o metadata existente e o loop
ignora problemas já registrados como `AC`. Use `--no-resume` para reprocessar
o loop. Dataset, credenciais e resultados gerados são locais e não devem ser
versionados.
