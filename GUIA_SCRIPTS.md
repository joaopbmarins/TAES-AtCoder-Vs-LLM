# Guia rápido de scripts

Este guia mostra como reproduzir o experimento principal com 17 problemas.
Execute os comandos na raiz do repositório, com o ambiente virtual ativado.

## Preparação no Windows

No PowerShell:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\Activate.ps1
```

## Preparação no Linux

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Configure `GOOGLE_API_KEY` e a autenticação do AtCoder no `.env`. O dataset
bruto é baixado automaticamente na primeira etapa.

## Pipeline no Windows

### Filtrar submissões

```powershell
.\.venv\Scripts\taes-pipeline.exe filter `
  --linguagens Python PyPy `
  --resultados AC `
  --contests abc399 arc195 agc071 `
  --max-por-problema 5 `
  --max-por-contest 50
```

Resultado: 17 problemas selecionados a partir de 73 submissões humanas.

### Baixar os códigos humanos e criar a lista de problemas

```powershell
.\.venv\Scripts\taes-pipeline.exe download
.\.venv\Scripts\taes-pipeline.exe problems
```

### Executar o loop de geração

```powershell
.\.venv\Scripts\taes-loop.exe `
  --provider google `
  --model gemini-3.8-flash `
  --out outputs/03_loop/03_loop_resultados.csv `
  --out-dir outputs/03_loop/03_loop_solucoes
```

## Pipeline no Linux

```bash
taes-pipeline filter \
  --linguagens Python PyPy \
  --resultados AC \
  --contests abc399 arc195 agc071 \
  --max-por-problema 5 \
  --max-por-contest 50

taes-pipeline download
taes-pipeline problems

taes-loop \
  --provider google \
  --model gemini-3.8-flash \
  --out outputs/03_loop/03_loop_resultados.csv \
  --out-dir outputs/03_loop/03_loop_solucoes
```

O loop padrão é:

```text
enunciado → geração pelo LLM → exemplos locais → submissão →
veredicto do AtCoder → correção, se necessário
```

Cada problema pode ter até três submissões ao AtCoder. O loop registra
tentativas, feedback, uso de tokens e soluções aceitas.

## Diretórios de saída

```text
outputs/
├── 01_filter/       CSV filtrado
├── 02_download/     códigos e metadados humanos
├── 03_loop/         problemas, tentativas, soluções e resultados da IA
└── 04_qodana/       relatórios opcionais de análise estática
```

Resultados selecionados para publicação ficam em `results/`; os artefatos
completos de execução permanecem em `outputs/`, que não é versionado.

## Análise Qodana (opcional)

Windows (PowerShell):

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

## Retomar ou recomeçar

- Execute novamente `download` sem apagar os arquivos: o metadata evita
  downloads duplicados.
- Execute novamente o loop: problemas já `AC` são ignorados.
- Use `--no-resume` no loop para processar tudo novamente.
- Para refazer o filtro, remova o CSV de saída e execute o comando de filtro.

## Desenvolvimento

Windows (PowerShell):

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check taes tests
.\.venv\Scripts\python.exe -m compileall -q taes
```

Linux:

```bash
python -m pytest
ruff check taes tests
python -m compileall -q taes
```
