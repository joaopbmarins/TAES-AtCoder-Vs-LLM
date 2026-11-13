# TAES AtCoder vs LLM

Pipeline para comparar soluções humanas do AtCoder com soluções geradas por
LLM. O fluxo filtra submissões do AtCoder, baixa os códigos humanos, gera uma
solução para cada problema e registra o veredicto obtido no AtCoder.

Este projeto foi desenvolvido com base no artigo “The transformative potential
of AI in software engineering: a case study on LeetCode and ChatGPT” como
trabalho da disciplina Tópicos Avançados em Engenharia de Software, no período
2026.2, ministrada pelo professor Augusto Cezar Alves Sampaio.

Para executar as configurações do experimento, consulte
[EXECUCAO_EXPERIMENTO.md](./EXECUCAO_EXPERIMENTO.md). O roteiro está em
PowerShell e também explica como adaptar os comandos para Bash. Para conhecer
as opções de cada etapa, consulte o [guia de parâmetros](./GUIA_SCRIPTS.md).

## Experimento principal

O experimento usado como referência neste projeto foi executado em duas
partes: seleção dos dados e geração/submissão das soluções.

### Objetivo e protocolo

O objetivo é observar como diferentes estratégias de uso de LLM resolvem
problemas reais de programação competitiva. O conjunto contém 17 problemas
dos contests `abc399`, `arc195` e `agc071`. Para caracterizar os problemas e
preparar uma referência humana, foram selecionadas submissões aceitas em
Python ou PyPy: no máximo cinco por problema e 50 por contest, totalizando
73 códigos humanos.

Para cada problema, o sistema obtém o enunciado e os exemplos, pede ao modelo
que gere uma solução e valida o código localmente com esses exemplos antes
da submissão ao AtCoder. Se a validação ou a submissão indicar uma falha, o
modelo pode receber o feedback e tentar corrigir a solução. O limite é de
três submissões por problema; uma solução `AC` encerra o processo daquele
problema.

Os resultados em `results/` comparam o grafo padrão, que concentra geração e
reparo em um fluxo único, com o grafo `multiagent`, que distribui planejamento,
codificação, teste e validação entre agentes. As duas execuções GPT-6 Luna
usam o mesmo conjunto de problemas. Essa comparação descreve o desempenho
observado neste recorte de 17 problemas; não deve ser interpretada como uma
medida universal de desempenho dos modelos.

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

## Resultados da experimentação

A pasta [`results/`](./results/) contém os resultados consolidados das
execuções, organizados por modelo e grafo. Cada subpasta inclui um README com
a configuração e o resumo, além do CSV com uma linha por problema e dados
como veredicto, número de tentativas, tempo, memória e uso de tokens.

| Execução | Grafo | AC | WA | TLE | CSV |
|---|---|---:|---:|---:|---|
| `gpt-6-luna-default` | Padrão | 9 | 6 | 2 | [resultados.csv](./results/gpt-6-luna-default/resultados.csv) |
| `gpt-6-luna-multiagent` | Multiagente | 12 | 4 | 1 | [resultados.csv](./results/gpt-6-luna-multiagent/resultados.csv) |

### Significado dos veredictos

Os códigos abaixo são os veredictos usados pelo AtCoder e registrados pelo
pipeline:

| Código | Nome em inglês | Significado |
|---|---|---|
| `AC` | Accepted | Solução aceita: passou em todos os testes. |
| `WA` | Wrong Answer | Resposta incorreta: a saída não corresponde à esperada em algum teste. |
| `TLE` | Time Limit Exceeded | Limite de tempo excedido. |
| `RE` | Runtime Error | Erro durante a execução do programa. |
| `CE` | Compilation Error | Erro de compilação. |
| `MLE` | Memory Limit Exceeded | Limite de memória excedido. |
| `OLE` | Output Limit Exceeded | Limite de saída excedido. |
| `PE` | Presentation Error | Erro no formato/apresentação da saída. |
| `QLE` | Query Limit Exceeded | Limite de consultas excedido. |
| `SE` | System Error | Erro do sistema durante a avaliação. |
| `IE` | Judge Error | Erro interno do avaliador. |
| `WJ` | Waiting for Judging | A avaliação ainda está em andamento ou não foi concluída. |

`ERROR: ...` nas saídas do loop indica uma falha da execução da pipeline
(por exemplo, ao obter o enunciado ou chamar o modelo), não um veredicto do
AtCoder.

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
o loop. O dataset, as credenciais e os artefatos intermediários gerados em
`outputs/` são locais e não devem ser versionados; os resultados consolidados
do experimento estão em `results/`.
