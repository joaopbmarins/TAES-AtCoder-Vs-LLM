# Comandos para executar o experimento

Execute os comandos na raiz do repositório, com o ambiente virtual ativado.
O experimento descrito no README seleciona 17 problemas dos contests
`abc399`, `arc195` e `agc071`, usando submissões humanas em Python/PyPy com
veredicto `AC`; essa seleção produziu 73 submissões humanas. A sequência
abaixo prepara esses dados e executa as quatro configurações de modelo e
grafo avaliadas.

Os blocos de comando deste documento estão no formato do Windows PowerShell.
Para executá-los em Bash:

- Ative o ambiente virtual com `source .venv/bin/activate`.
- Troque o acento grave (`` ` ``) no fim das linhas pelo caractere `\` de
  continuação do Bash. Comandos em uma única linha não precisam ser alterados.
- Use barras `/` nos caminhos. Os caminhos mostrados nos exemplos já usam
  esse formato.
- Se não ativar o ambiente virtual, invoque os executáveis em `.venv/bin/`
  (por exemplo, `.venv/bin/taes-loop`) em vez dos nomes simples.

Antes de começar, configure no `.env` as chaves dos provedores usados e um
cookie de sessão autenticada do AtCoder:

```text
GOOGLE_API_KEY=...
OPENAI_API_KEY=...
ATCODER_SESSION_COOKIE=...
QODANA_TOKEN=...
```

## 1. Filtrar submissões

```powershell
taes-pipeline filter `
  --csv submissions.csv `
  --linguagens Python PyPy `
  --resultados AC `
  --contests abc399 arc195 agc071 `
  --max-por-problema 5 `
  --max-por-contest 50
```

O CSV filtrado será gravado em
`outputs/01_filter/01_filter_filtered_submissions.csv`.

## 2. Baixar os códigos humanos

```powershell
taes-pipeline download
```

O comando usa o CSV filtrado padrão e grava os arquivos em
`outputs/02_download/AtCoder`. Também gera uma lista de problemas em
`outputs/02_download/AtCoder/02_download_atcoder_submissions_problems.csv`.

## 3. Executar os modelos

### Gemini 3.5 Flash Lite — grafo padrão

```powershell
taes-loop `
  --provider google `
  --model gemini-3.5-flash-lite `
  --out outputs/03_loop/gemini-3.5-flash-lite/resultados.csv `
  --out-dir outputs/03_loop/gemini-3.5-flash-lite/solucoes
```

### Gemini 3.5 Flash Lite — grafo multiagente

```powershell
taes-loop `
  --provider google `
  --model gemini-3.5-flash-lite `
  --graph multiagent `
  --out outputs/03_loop/gemini-3.5-flash-lite-multiagent/resultados.csv `
  --out-dir outputs/03_loop/gemini-3.5-flash-lite-multiagent/solucoes
```

### GPT-6 Luna — grafo multiagente

```powershell
taes-loop `
  --graph multiagent `
  --provider openai `
  --model gpt-6-luna `
  --planner-model gpt-6-luna `
  --coder-model gpt-6-luna `
  --test-model gpt-6-luna `
  --max-tokens 50000 `
  --planner-reasoning high `
  --coder-reasoning medium `
  --test-reasoning medium `
  --out outputs/03_loop/gpt-6-luna-multiagent/resultados.csv `
  --out-dir outputs/03_loop/gpt-6-luna-multiagent/solucoes
```

### GPT-6 Luna — grafo padrão

```powershell
taes-loop `
  --graph default `
  --provider openai `
  --model gpt-6-luna `
  --max-tokens 50000 `
  --out outputs/03_loop/gpt-6-luna-default/resultados.csv `
  --out-dir outputs/03_loop/gpt-6-luna-default/solucoes
```

O loop usa por padrão a lista de problemas exportada pelo download, coleta
cada enunciado, executa os exemplos localmente e submete a solução ao AtCoder.
Em caso de falha, pode tentar corrigir o código até o limite configurado.
Cada execução grava resultados, um CSV de erros e soluções em sua própria
pasta. Problemas já aceitos são retomados; use `--no-resume` para processá-los
novamente.

## 4. Análise Qodana (opcional)

Para comparar os códigos humanos com as soluções aceitas por uma execução,
prepare o layout da IA apontando para os resultados e soluções dessa execução.
O exemplo abaixo usa GPT-6 Luna com o grafo padrão:

```powershell
taes-pipeline ai-layout `
  --results outputs/03_loop/gpt-6-luna-default/resultados.csv `
  --solutions outputs/03_loop/gpt-6-luna-default/solucoes `
  --target outputs/02_download/IA

taes-qodana outputs/02_download `
  --rules-python rules_py.txt `
  --rules-cpp rules_cpp.txt
```

O Qodana requer Docker e o executável `qodana`. Para analisar outra execução,
substitua `--results` e `--solutions` pelos caminhos correspondentes. Prepare
uma execução por vez no destino `outputs/02_download/IA`.
