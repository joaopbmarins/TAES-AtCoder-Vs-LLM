# Guia de comandos

O projeto usa os comandos instalados pelo `pyproject.toml`. A implementação
está exclusivamente em `taes/`, organizada por responsabilidade.

## Pipeline

```bash
taes-pipeline filter --help
taes-pipeline download --help
taes-pipeline problems --help
taes-pipeline loop --help
taes-pipeline ai-layout --help
taes-pipeline qodana --help
taes-pipeline all --help
```

## Loop de geração

```bash
taes-loop problems.csv \
  --out outputs/03_loop/03_loop_resultados.csv \
  --out-dir outputs/03_loop/03_loop_solucoes \
  --provider google \
  --model gemini-3.8-flash
```

Também é possível usar o módulo diretamente:

```bash
python -m taes.loop problems.csv
python -m taes.cli.pipeline problems
python -m taes.analysis.qodana --help
```

## Testes

```bash
pytest
pytest tests/test_storage.py
ruff check taes tests
python -m compileall -q taes
```

## Saídas

Os artefatos ficam em `outputs/`:

- `01_filter/`: submissões filtradas;
- `02_download/`: código humano e layout de comparação;
- `03_loop/`: problemas, resultados, tentativas e soluções da IA;
- `04_qodana/`: relatórios e resultados da análise.
