# Guia de execução e parâmetros

Este documento descreve os parâmetros das interfaces `taes-pipeline`,
`taes-loop` e `taes-qodana`. Execute os comandos na raiz do repositório.
Os caminhos relativos são interpretados a partir do diretório atual.

## Preparar o ambiente

O projeto requer Python 3.10 a 3.14.

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

Defina a chave do provedor de LLM selecionado e, para enviar soluções ao
AtCoder, o cookie de uma sessão autenticada. As variáveis podem ficar em
`.env` na raiz:

```text
GOOGLE_API_KEY=...
OPENAI_API_KEY=...
NVIDIA_API_KEY=...
ATCODER_SESSION_COOKIE=...
```

O cookie também pode ser fornecido diretamente a `taes-loop` com
`--atcoder-session-cookie`. Não compartilhe nem versione credenciais.

## `taes-pipeline`

Esse comando executa etapas individuais ou a pipeline completa. Consulte as
opções reconhecidas pela instalação com:

```text
taes-pipeline --help
taes-pipeline <etapa> --help
```

### `filter`: selecionar submissões

Exemplo:

```powershell
taes-pipeline filter `
  --csv submissions.csv `
  --contests abc399 arc195 agc071 `
  --linguagens Python PyPy `
  --resultados AC `
  --max-por-problema 5 `
  --max-por-contest 50
```

Todos os filtros informados são aplicados em conjunto. Sem `--csv`, o dataset
é baixado do AtCoder Problems; se já existir `submissions.csv` ou
`submissions.csv.gz` na raiz, esse arquivo é usado. O download do dataset pode
ser retomado se for interrompido.

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `--csv ARQUIVO` | Baixa/usa o dataset encontrado na raiz | Dataset bruto local de submissões. Informe um CSV ou CSV compactado `.gz` existente para não baixar automaticamente. |
| `--out ARQUIVO` | `outputs/01_filter/01_filter_filtered_submissions.csv` | Caminho do CSV filtrado a criar. |
| `--contests ID...` | Sem restrição | Mantém somente os IDs exatos informados, por exemplo `abc300 abc301`. |
| `--prefixos-contest PREFIXO...` | Sem restrição | Mantém contests cujos IDs começam por qualquer prefixo informado, por exemplo `abc arc`. |
| `--linguagens PREFIXO...` | Sem restrição | Mantém linguagens cujo nome começa com um dos valores, por exemplo `Python PyPy`. |
| `--linguagens-exatas NOME...` | Sem restrição | Mantém somente nomes de linguagem exatamente iguais aos valores informados. Pode ser combinado com `--linguagens`. |
| `--resultados RESULTADO...` | `AC` | Resultados das submissões a manter, por exemplo `AC WA`. |
| `--all-results` | Desativado | Desativa o filtro por resultado e mantém todos os resultados; prevalece sobre `--resultados`. |
| `--corte AAAA-MM-DD` | Sem restrição | Mantém contests iniciados nessa data ou depois dela. A data é interpretada no fuso `America/Sao_Paulo`. |
| `--envio-de DATA[ HORA]` | Sem limite inferior | Mantém submissões enviadas a partir do instante informado. Formatos aceitos: `AAAA-MM-DD` ou `AAAA-MM-DD HH:MM[:SS]`. |
| `--envio-ate DATA[ HORA]` | Sem limite superior | Limita o instante de envio. Uma data sem hora inclui o dia inteiro; com hora, o instante é o limite exclusivo. |
| `--max-por-problema N` | Sem limite | Limita o número de submissões por contest e problema. Deve ser maior que zero. |
| `--max-por-contest N` | Sem limite | Limita o número de submissões por contest. Deve ser maior que zero. |
| `--seed N` | `42` | Semente para tornar reprodutível a amostragem usada pelos limites. |

Ao aplicar os limites, o filtro remove duplicatas de usuário por problema e
prioriza resultados como `AC`, `WA`, `TLE` e `RE` nessa ordem; dentro da mesma
prioridade, a seleção é aleatória e controlada por `--seed`.
Quando informar data e hora, passe o valor como um único argumento entre
aspas, por exemplo `--envio-de "2024-01-01 09:00"`.

### `download`: baixar códigos humanos

```text
taes-pipeline download [opções]
```

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `--input ARQUIVO` | CSV produzido por `filter` | CSV de submissões a baixar. Precisa conter `id`, `contest_id`, `problem_id`, `language` e `result`. |
| `--out DIRETÓRIO` | `outputs/02_download/AtCoder` | Diretório para os códigos humanos e metadados. |
| `--all-results` | Desativado | Baixa também submissões que não são `AC`; por padrão somente `AC`. |
| `--workers N` | `4` | Número de downloads simultâneos. Deve ser pelo menos `1`. |
| `--delay SEGUNDOS` | `1.5` | Pausa por worker depois de cada requisição. Deve ser zero ou maior. |

O arquivo de metadados registra IDs já baixados, então executar a etapa
novamente evita downloads duplicados. A lista de problemas também é exportada
para o diretório de saída.

### `problems`: gerar a lista de problemas

```text
taes-pipeline problems [opções]
```

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `--input ARQUIVO` | CSV filtrado padrão | CSV de entrada; precisa ter a coluna `problem_id`. |
| `--out ARQUIVO` | `outputs/03_loop/03_loop_problems.csv` | CSV de saída com IDs de problema únicos. |

### `loop`: resolver problemas com um LLM

```text
taes-pipeline loop [opções]
```

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `--input ARQUIVO` | `outputs/03_loop/03_loop_problems.csv` | CSV com a coluna `problem_id`. |
| `--out ARQUIVO` | `outputs/03_loop/03_loop_resultados.csv` | CSV de resultados. |
| `--out-dir DIRETÓRIO` | `outputs/03_loop/03_loop_solucoes` | Diretório de soluções e registros de tentativas. |
| `--provider {openai,google,nvidia}` | `google` | Provedor do modelo. Requer `OPENAI_API_KEY`, `GOOGLE_API_KEY` ou `NVIDIA_API_KEY`, respectivamente. |
| `--model NOME` | `gemini-3.8-flash` | Identificador do modelo usado no grafo padrão e como modelo padrão dos agentes. |
| `--graph NOME` | Configuração `GRAPH_NAME` (`default`) | Grafo a executar: `default`, `multiagent` ou `dummy`. |
| `--planner-model NOME` | `--model` | Modelo do Planner no grafo `multiagent`. |
| `--coder-model NOME` | `--model` | Modelo do Coder no grafo `multiagent`. |
| `--test-model NOME` | `--model` | Modelo do Test Agent no grafo `multiagent`. |
| `--planner-reasoning {low,medium,high}` | `high` | Esforço de raciocínio pedido ao Planner no grafo `multiagent`. |
| `--coder-reasoning {low,medium,high}` | `medium` | Esforço de raciocínio pedido ao Coder no grafo `multiagent`. |
| `--test-reasoning {low,medium,high}` | `medium` | Esforço de raciocínio pedido ao Test Agent no grafo `multiagent`. |
| `--max-tokens N` | `4096` | Limite de tokens de saída configurado para cada modelo. |
| `--no-resume` | Desativado | Reprocessa problemas mesmo que já constem como `AC` no CSV ou nos registros de tentativas. |
| `--atcoder-session-cookie VALOR` | Variável de ambiente | Cookie/jar autenticado para enviar código ao AtCoder. Alternativamente, use `ATCODER_SESSION_COOKIE` ou `ATCODER_COOKIES` no ambiente ou no `.env`. |
| `-v`, `--verbose` | Desativado | Ativa logs detalhados (`DEBUG`). |

O grafo `default` gera, valida localmente e submete a solução; em caso de
falha, pode tentar corrigi-la. `multiagent` separa planejamento, codificação e
teste; as opções específicas de modelo e raciocínio só se aplicam a esse
grafo. O suporte ao parâmetro de raciocínio depende do provedor e é aplicado
pela integração OpenAI; os outros provedores podem ignorá-lo.

Uma submissão requer uma sessão autenticada do AtCoder. O loop pode executar
os exemplos do enunciado antes de submeter, e registra resultados, uso de
tokens, tentativas e soluções aceitas. Problemas já aceitos são ignorados,
exceto quando `--no-resume` é informado.

### `ai-layout`: organizar as soluções aceitas

```text
taes-pipeline ai-layout [opções]
```

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `--results ARQUIVO` | CSV de resultados do loop | CSV usado para identificar problemas com veredicto `AC`. |
| `--solutions DIRETÓRIO` | Diretório de soluções do loop | Origem dos arquivos de solução gerados. |
| `--target DIRETÓRIO` | `outputs/02_download/IA` | Raiz de destino; os arquivos são organizados por contest e problema. |

### `qodana`: análise estática comparativa

```text
taes-pipeline qodana [opções]
```

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `--root DIRETÓRIO` | `outputs/02_download` | Diretório que contém as pastas de origem, como `AtCoder/` e `IA/`. |
| `--out PREFIXO` | `outputs/04_qodana/04_qodana_relatorio` | Prefixo dos três CSVs: `_submissoes.csv`, `_resumo.csv` e `_comparacao.csv`. |
| `--rules-python ARQUIVO` | Não definido | Arquivo com IDs de inspeções Python, um por linha. Comentários iniciados por `#` são ignorados. |
| `--rules-cpp ARQUIVO` | Não definido | Arquivo com IDs de inspeções C/C++, um por linha. Comentários iniciados por `#` são ignorados. |
| `--linter-python IMAGEM` | `jetbrains/qodana-python-community:2026.2` | Imagem Qodana usada quando há regras Python. |
| `--linter-cpp IMAGEM` | `jetbrains/qodana-clang:2026.2` | Imagem Qodana usada quando há regras C/C++. |
| `--sources PASTA=RÓTULO,...` | `AtCoder=humano,IA=IA` | Pastas relativas a `ROOT` e os rótulos que aparecerão nos relatórios. |

Informe pelo menos um arquivo de regras não vazio. Para opções adicionais de
compilação e organização da análise, use diretamente o executável
`taes-qodana`; seus parâmetros estão na seção correspondente abaixo.

### `all`: pipeline completa

```text
taes-pipeline all [opções]
```

Esta etapa filtra o dataset, baixa submissões, gera a lista de problemas,
executa o loop e prepara o layout das soluções aceitas. `--with-qodana`
acrescenta a análise Qodana ao final.

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `--raw-csv ARQUIVO` | Baixa/usa o dataset encontrado na raiz | Dataset bruto local; sem essa opção, o filtro localiza ou baixa o dataset automaticamente. |
| `--out-dir DIRETÓRIO` | `outputs/00_pipeline` | Diretório de trabalho da execução completa. |
| `--contests ID...` | Sem restrição | IDs exatos de contests a manter no filtro. |
| `--prefixos-contest PREFIXO...` | Sem restrição | Prefixos de contest a manter. |
| `--linguagens PREFIXO...` | Sem restrição | Prefixos de nomes de linguagem. |
| `--linguagens-exatas NOME...` | Sem restrição | Nomes exatos de linguagem. |
| `--resultados RESULTADO...` | `AC` | Resultados a manter no filtro. |
| `--all-results` | Desativado | Mantém todos os resultados no filtro e permite baixar submissões não `AC`. |
| `--download-workers N` | `4` | Downloads simultâneos; deve ser pelo menos `1`. |
| `--download-delay SEGUNDOS` | `1.5` | Pausa por worker entre requisições; deve ser zero ou maior. |
| `--corte AAAA-MM-DD` | Sem restrição | Data mínima de início dos contests, no fuso `America/Sao_Paulo`. |
| `--envio-de DATA[ HORA]` | Sem limite inferior | Limite inferior dos instantes de envio. |
| `--envio-ate DATA[ HORA]` | Sem limite superior | Limite superior dos instantes de envio; data sem hora inclui o dia todo. |
| `--max-por-problema N` | Sem limite | Máximo de submissões por contest/problema; deve ser maior que zero. |
| `--max-por-contest N` | Sem limite | Máximo de submissões por contest; deve ser maior que zero. |
| `--seed N` | `42` | Semente de amostragem dos limites do filtro. |
| `--loop-provider {openai,google,nvidia}` | `google` | Provedor do LLM e variável de API key correspondente. |
| `--loop-model NOME` | `gemini-3.8-flash` | Modelo padrão para o loop. |
| `--loop-graph NOME` | Configuração `GRAPH_NAME` (`default`) | Grafo: `default`, `multiagent` ou `dummy`. |
| `--planner-model NOME` | `--loop-model` | Modelo do Planner em `multiagent`. |
| `--coder-model NOME` | `--loop-model` | Modelo do Coder em `multiagent`. |
| `--test-model NOME` | `--loop-model` | Modelo do Test Agent em `multiagent`. |
| `--planner-reasoning {low,medium,high}` | `high` | Esforço de raciocínio do Planner em `multiagent`. |
| `--coder-reasoning {low,medium,high}` | `medium` | Esforço de raciocínio do Coder em `multiagent`. |
| `--test-reasoning {low,medium,high}` | `medium` | Esforço de raciocínio do Test Agent em `multiagent`. |
| `--loop-max-tokens N` | `4096` | Limite de tokens de saída por modelo. |
| `--no-loop-resume` | Desativado | Refaz problemas já aceitos pelo loop. |
| `--with-qodana` | Desativado | Executa também a análise Qodana ao final. |
| `--rules-python ARQUIVO` | Não definido | Arquivo de regras Python para a etapa Qodana opcional. |
| `--rules-cpp ARQUIVO` | Não definido | Arquivo de regras C/C++ para a etapa Qodana opcional. |
| `--linter-python IMAGEM` | `jetbrains/qodana-python-community:2026.2` | Imagem Qodana Python. |
| `--linter-cpp IMAGEM` | `jetbrains/qodana-clang:2026.2` | Imagem Qodana C/C++. |

Os arquivos de cada etapa são criados sob `--out-dir`. Ao ativar Qodana,
defina pelo menos uma das opções de regras. A autenticação do AtCoder para
submissão deve estar nas variáveis `ATCODER_SESSION_COOKIE` ou
`ATCODER_COOKIES` do ambiente/`.env`: `all` não oferece um argumento de cookie.

## `taes-loop` diretamente

Use este executável quando precisar das opções adicionais de cookie,
detalhamento de logs ou CSV de erros:

```text
taes-loop [CSV] [opções]
```

Ele aceita os mesmos parâmetros de execução de loop documentados em
[`taes-pipeline loop`](#loop-resolver-problemas-com-um-llm), além de:

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `CSV` | `outputs/02_download/AtCoder/02_download_atcoder_submissions_problems.csv` | CSV de entrada com a coluna `problem_id`. É posicional e opcional. |
| `--out-errors ARQUIVO` | Nome do CSV de saída acrescido de `_erros` | CSV separado para problemas com erro ou veredicto diferente de `AC`. |

No executável direto, os outros defaults são os mesmos da tabela de loop,
exceto que o CSV de entrada padrão é a lista exportada pelo download (e não
`outputs/03_loop/03_loop_problems.csv`).

Exemplo:

```powershell
taes-loop outputs/03_loop/03_loop_problems.csv `
  --provider google `
  --model gemini-3.8-flash `
  --graph multiagent `
  --out outputs/03_loop/03_loop_resultados.csv `
  --out-errors outputs/03_loop/03_loop_resultados_erros.csv `
  --out-dir outputs/03_loop/03_loop_solucoes
```

## `taes-qodana` diretamente

```text
taes-qodana ROOT [opções]
```

As opções `--sources`, `--rules-python`, `--rules-cpp`,
`--linter-python`, `--linter-cpp` e `--out` têm o mesmo significado descrito
na seção `taes-pipeline qodana`. A chamada direta expõe ainda:

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `--c-std VALOR` | `c17` | Padrão de linguagem usado ao analisar arquivos C. |
| `--cpp-std VALOR` | `c++20` | Padrão de linguagem usado ao analisar arquivos C++. |
| `--cpp-flags FLAGS` | Vazio | Flags extras passadas aos comandos de compilação C/C++, por exemplo `"-I/caminho/ac-library"`. |
| `--container-root CAMINHO` | `/data/project` | Caminho da raiz do projeto dentro do container Docker. Use valor vazio (`--container-root ""`) para usar o caminho local. |
| `--layout NÍVEIS` | `contest,problem` | Nomes, separados por vírgula, dos níveis de pasta dentro de cada origem e acima dos arquivos. São usados como colunas dos relatórios. |
| `--scope {contest,all}` | `contest` | `contest` inicia uma análise por contest; `all` inicia uma análise por pasta de origem. |
| `--results-root DIRETÓRIO` | `outputs/04_qodana/04_qodana_results` | Diretório dos resultados brutos e logs do Qodana. |
| `--include-non-ac` | Desativado | Inclui arquivos com sufixos de veredicto como `_WA`, `_TLE` e `_RE`; por padrão, esses arquivos são ignorados. |

O Qodana requer Docker e o executável `qodana`. A execução também pode
criar um repositório Git na raiz analisada quando ela ainda não estiver em um.

## Ajustes internos do loop

Os valores abaixo não são opções de linha de comando. Para alterá-los,
modifique `taes/core/config.py`:

| Constante | Valor padrão | Efeito |
|---|---:|---|
| `MAX_ATTEMPTS` | `3` | Máximo de submissões ao AtCoder por problema. |
| `MAX_VALIDATION_ATTEMPTS` | `3` | Máximo de falhas de validação local antes de encerrar o ciclo. |
| `MAX_FEEDBACK_CHARS` | `2000` | Máximo de caracteres de feedback de erro incluídos no prompt de reparo. |
| `LOCAL_PRECHECK` | `True` | Executa sintaxe e exemplos localmente antes de submeter. |
| `LOCAL_TIMEOUT_S` | `10.0` | Timeout em segundos por exemplo na validação local. |
| `RECURSION_LIMIT` | `100` | Limite de passos do LangGraph por problema. |
| `GRAPH_NAME` | `"default"` | Grafo usado quando `--graph`/`--loop-graph` não é informado. Opções implementadas: `default`, `multiagent`, `dummy`. |

## Diretórios padrão

```text
outputs/
├── 01_filter/       CSV filtrado
├── 02_download/     códigos e metadados humanos; layout da IA
├── 03_loop/         problemas, tentativas, soluções e resultados
└── 04_qodana/       relatórios e resultados brutos do Qodana
```

Os resultados curados para publicação ficam em `results/`. Artefatos de
execução ficam em `outputs/`.

## Ajuda e validação

```text
taes-pipeline --help
taes-pipeline filter --help
taes-pipeline all --help
taes-loop --help
taes-qodana --help
```

Para validar a instalação no Windows:

```powershell
python -m pytest
ruff check taes tests
python -m compileall -q taes
```

No Linux, use os mesmos comandos com o ambiente virtual ativado.
