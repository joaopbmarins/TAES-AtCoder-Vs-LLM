# Filtro de submissões do AtCoder

Script em Python que lê o dataset de submissões do AtCoder Problems, aplica filtros e gera um CSV com duas colunas extras: o **início do contest** e a **data/hora do envio**.

## Como funciona

1. Procura `submissions.csv` ou `submissions.csv.gz` na pasta atual. Se nenhum existir, baixa o `.csv.gz` automaticamente.
2. Baixa o `contests.json` (para saber a data de início de cada contest).
3. Lê o dataset em blocos de 1 milhão de linhas, aplica os filtros e grava o resultado.


## Estrutura de arquivos

```
pasta/
├── filtrar_submissoes.py      # o script
├── submissions.csv.gz         # dataset (baixado sozinho se não existir)
└── submissoes_filtradas.csv   # saída gerada
```

> Salve o código com o nome que preferir. Aqui usamos `filtrar_submissoes.py`.

## Configuração geral

No topo do script:

| Variável | O que é | Padrão |
|---|---|---|
| `SUBS_URL` | URL do dataset de submissões | S3 do kenkoooo |
| `SUBS_CANDIDATOS` | Arquivos locais procurados, em ordem | `submissions.csv`, `submissions.csv.gz` |
| `CONTESTS` | URL do `contests.json` | kenkoooo.com |
| `TZ` | Fuso horário usado nas datas | `America/Sao_Paulo` |

## Parâmetros do `processar()`

Todos são opcionais. Os filtros se combinam com **E** entre si; dentro de uma lista, funciona como **OU**.

| Parâmetro | Tipo | Descrição | Exemplo |
|---|---|---|---|
| `contests_lista` | lista | IDs exatos de contests | `["abc300", "abc301"]` |
| `prefixos_contest` | lista | Contests cujo ID começa com o prefixo | `["abc", "arc"]` |
| `linguagens` | lista | Linguagens que **começam com** o texto | `["C++", "Python", "PyPy"]` |
| `linguagens_exatas` | lista | Nome completo da linguagem | `["C++ 20 (gcc 12.2)"]` |
| `resultados` | lista ou `None` | Status da submissão. Padrão: só aprovadas | `["AC"]`, `None` para todos |
| `corte` | texto | Mantém só contests que **começaram** a partir dessa data | `"2026-01-01"` |
| `envio_de` | texto | Início da janela de envio | `"2026-03-01"` ou `"2026-03-01 21:00"` |
| `envio_ate` | texto | Fim da janela de envio | `"2026-03-31"` |
| `saida` | texto | Nome do CSV de saída | `"resultado.csv"` |

### Sobre as datas

- Formatos aceitos: `"YYYY-MM-DD"` ou `"YYYY-MM-DD HH:MM"` (também com segundos).
- São sempre interpretadas no fuso definido em `TZ`.
- Em `envio_ate`, se você passar **só a data**, o dia inteiro é incluído (`"2026-03-31"` vai até 23:59:59).
- Se passar com horário, o limite é exclusivo.
- `envio_de` deve ser anterior a `envio_ate`, senão o script levanta um erro.
- Dá para usar só `envio_de` (tudo a partir de) ou só `envio_ate` (tudo até).

### Sobre linguagens

O campo `language` traz o nome completo do compilador, e ele varia por versão (por exemplo `C++ (GCC 9.2.1)`, `C++ 20 (gcc 12.2)`, `Python (3.8.2)`, `Python (CPython 3.11.4)`).

- `linguagens=["C++"]` usa "começa com" e pega todas as variantes de C++.
- Cuidado: `"C"` pegaria também `C++` e `C#`. Use um prefixo mais específico (como `"C (GCC"`) ou `linguagens_exatas`.

Para ver os nomes reais no seu arquivo:

```python
import pandas as pd
print(pd.read_csv("submissions.csv.gz", usecols=["language"], nrows=2_000_000)["language"].value_counts().head(40))
```

## Exemplos de uso

Edite o bloco `if __name__ == "__main__":` no final do script.

**Contests específicos, só Python/PyPy, só aprovadas:**

```python
processar(
    contests_lista=["abc300", "abc301", "abc302"],
    linguagens=["Python", "PyPy"],
    saida="abc300_302_py.csv",
)
```

**Todos os ABC enviados em março de 2026:**

```python
processar(
    prefixos_contest=["abc"],
    envio_de="2026-03-01",
    envio_ate="2026-03-31",
    saida="abc_marco_2026.csv",
)
```

**Janela com horário:**

```python
processar(
    contests_lista=["abc300"],
    envio_de="2026-03-04 21:00",
    envio_ate="2026-03-05 00:00",
    saida="abc300_janela.csv",
)
```

**Contests iniciados em 2026, em várias linguagens:**

```python
processar(
    prefixos_contest=["abc"],
    linguagens=["C++", "Python", "PyPy"],
    corte="2026-01-01",
    saida="abc_2026.csv",
)
```

**Manter todos os resultados (WA, TLE, CE etc.):**

```python
processar(contests_lista=["abc300"], resultados=None, saida="abc300_todos.csv")
```

## Executando

```bash
python filtrar_submissoes.py
```

Na primeira vez, se o dataset não estiver na pasta, ele é baixado com barra de progresso. O download grava em `submissions.csv.gz.part` e só renomeia ao terminar, então uma queda de conexão não deixa um arquivo corrompido.

## Colunas do CSV de saída

Colunas originais do dataset:

`id, epoch_second, problem_id, contest_id, user_id, language, point, length, result, execution_time`

Colunas adicionadas:

| Coluna | Descrição |
|---|---|
| `contest_start_epoch` | Início do contest em timestamp Unix |
| `submission_datetime` | Data/hora do envio no fuso `TZ` |
| `contest_start_datetime` | Data/hora do início do contest no fuso `TZ` |

## Solução de problemas

- **Aparecem submissões não aprovadas**: confira se `resultados` não foi passado como `None`. Por padrão só `AC` é mantido.
- **"Nenhuma submissão passou nos filtros"**: nenhum arquivo é criado. Afrouxe os filtros ou confira os nomes das linguagens.
- **Arquivo de saída antigo**: o script apaga a saída anterior antes de começar, para não misturar execuções.
- **Contests sem data de início**: submissões cujo `contest_id` não está no `contests.json` ficam com `contest_start_epoch` vazio e são descartadas quando `corte` é usado.
- **Dataset desatualizado**: o arquivo é atualizado semanalmente no servidor. Para dados novos, apague o arquivo local e rode de novo.
- **Memória**: a leitura em blocos de 1 milhão de linhas funciona em máquinas modestas. Se tiver pouca RAM, reduza o `chunksize`.
- **Nomes de campos do `contests.json`**: o script usa `id` e `start_epoch_second`. Se a API mudar, ajuste na criação do `inicio`.
- **Uso responsável da API**: o script só faz uma requisição ao `contests.json` e, se necessário, um download do dataset. Se for chamar os endpoints da API em outros scripts, mantenha mais de 1 segundo entre as requisições.