"""Constantes compartilhadas pelo pacote."""

MAX_ATTEMPTS = 5            # tentativas por problema (1 geração + até 4 reparos)
MAX_FEEDBACK_CHARS = 2000   # tamanho máximo do feedback de erro enviado no prompt de reparo
FENCE = "`" * 3

GRAPH_NAME = "default"     # opções disponíveis: default, dummy
AVAILABLE_GRAPHS = ("default", "dummy")

# Colunas do CSV de resultados
# Mantém a compatibilidade com o histórico e também registra motivo/feedback da submissão.
RESULT_FIELDS = ["problem_id", "verdict", "attempts", "time_ms", "memory_kb", "reason", "feedback"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "en-US,en;q=0.9",
}
