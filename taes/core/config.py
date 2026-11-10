"""Constantes compartilhadas pelo pacote."""

MAX_ATTEMPTS = 3            # máximo de submissões ao AtCoder por problema
MAX_VALIDATION_ATTEMPTS = 3 # máximo de falhas de validação local antes de encerrar um ciclo
MAX_FEEDBACK_CHARS = 2000   # tamanho máximo do feedback de erro enviado no prompt de reparo
FENCE = "`" * 3

LOCAL_PRECHECK = True       # roda sintaxe + exemplos localmente antes de submeter ao AtCoder
LOCAL_TIMEOUT_S = 10.0      # timeout por exemplo na checagem local
RECURSION_LIMIT = 100       # limite de passos do LangGraph (padrão 25 estoura com grafos multiagente)

GRAPH_NAME = "default"     # opções disponíveis: default, dummy
AVAILABLE_GRAPHS = ("default", "multiagent", "dummy")

# Colunas do CSV de resultados
# Mantém a compatibilidade com o histórico e também registra motivo/feedback da submissão.
RESULT_FIELDS = ["problem_id", "verdict", "attempts", "time_ms", "memory_kb", "reason", "feedback",
                 "validation_attempts", "llm_calls", "input_tokens", "output_tokens"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "en-US,en;q=0.9",
}
