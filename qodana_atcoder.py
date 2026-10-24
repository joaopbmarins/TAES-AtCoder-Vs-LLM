#!/usr/bin/env python3
"""
Compara code smells de submissões aceitas no AtCoder (humanos x IA) com o JetBrains Qodana.

Estrutura esperada:
    submissoes/
        AtCoder/                 -> submissões humanas
            abc300/
                a/
                    12345678.py
                    12345679.cpp
        IA/                      -> submissões geradas por LLM
            abc300/
                a/
                    gpt_01.py
                    claude_01.cpp

Uso:
    python qodana_atcoder.py ./submissoes \
        --rules-python rules_py.txt --rules-cpp rules_cpp.txt \
        --linter-python jetbrains/qodana-python-community:2026.2 \
        --linter-cpp jetbrains/qodana-clang:2026.2 --out relatorio

Gera:
    <out>_submissoes.csv  -> uma linha por submissão (coluna 'origem' = humano | IA)
    <out>_resumo.csv      -> agregado por origem + campeonato + problema + linguagem
    <out>_comparacao.csv  -> humano x IA lado a lado por campeonato + problema + linguagem
"""
import argparse
import csv
import json
import shlex
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import unquote

LEVELS = ["error", "warning", "note", "none"]
IGNORED_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".idea"}
GROUPS = {
    "python": {"exts": {".py"}, "prefix": "py"},
    "cpp": {"exts": {".c", ".cc", ".cpp", ".cxx"}, "prefix": "cpp"},
}


def load_rules(path: Path) -> list[str]:
    rules = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            rules.append(line)
    return rules


def write_qodana_yaml(dest: Path, linter: str, rules: list[str]) -> None:
    """profile 'empty' + include => roda SOMENTE as inspeções listadas."""
    lines = ['version: "1.0"', f"linter: {linter}", "profile:", "  name: empty",
             "failThreshold: 100000000", "include:"]
    lines += [f"  - name: {r}" for r in rules]
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def find_files(base: Path, exts: set[str]) -> list[Path]:
    return sorted(p for p in base.rglob("*")
                  if p.is_file() and p.suffix.lower() in exts
                  and not any(part in IGNORED_DIRS for part in p.relative_to(base).parts))


def count_lines(path: Path) -> int:
    try:
        with path.open("rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def make_compile_commands(project: Path, files: list[Path], container_root: str,
                          c_std: str, cpp_std: str, extra: list[str]) -> Path:
    """Gera <projeto>/build/compile_commands.json (local padrão do qodana-clang)."""
    root = container_root or str(project)
    entries = []
    for f in files:
        rel = f.relative_to(project).as_posix()
        full = f"{root}/{rel}"
        is_c = f.suffix.lower() == ".c"
        args = (["clang", f"-std={c_std}"] if is_c else ["clang++", f"-std={cpp_std}"]) + extra + ["-c", full]
        entries.append({"directory": root, "file": full, "arguments": args})
    out_dir = project / "build"
    out_dir.mkdir(exist_ok=True)
    cc = out_dir / "compile_commands.json"
    cc.write_text(json.dumps(entries, indent=1), encoding="utf-8")
    return cc


def run_qodana(project: Path, results_dir: Path, linter: str):
    cmd = ["qodana", "scan", "--linter", linter, "--project-dir", str(project),
           "--results-dir", str(results_dir), "--save-report=false"]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (results_dir / "qodana.log").write_text(
        f"CMD: {' '.join(cmd)}\nEXIT: {proc.returncode}\n--- STDOUT ---\n{proc.stdout}\n--- STDERR ---\n{proc.stderr}\n",
        encoding="utf-8")
    return proc


def ensure_git_repo(root: Path) -> None:
    """O Qodana CLI chama 'git rev-parse' e falha fora de um repositório git."""
    probe = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=root,
                           capture_output=True, text=True)
    if probe.returncode == 0:
        return
    print(f"[i] {root} não está em um repositório git; executando 'git init' ...")
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)


def parse_sarif(sarif_path: Path):
    """Retorna {caminho_relativo_ao_projeto: (Counter por regra, Counter por nível)}."""
    data = json.loads(sarif_path.read_text(encoding="utf-8"))
    out = defaultdict(lambda: (Counter(), Counter()))
    for run in data.get("runs", []):
        for res in run.get("results", []):
            rule = res.get("ruleId", "unknown")
            level = res.get("level", "warning")
            for loc in res.get("locations", [])[:1]:
                uri = loc.get("physicalLocation", {}).get("artifactLocation", {}).get("uri")
                if uri:
                    by_rule, by_level = out[unquote(uri).lstrip("/")]
                    by_rule[rule] += 1
                    by_level[level] += 1
    return out


def split_path(rel: Path, layout: list[str]) -> dict:
    parts = rel.parts
    info = {name: (parts[i] if i < len(parts) - 1 else "") for i, name in enumerate(layout)}
    info["submissao"] = rel.stem
    info["linguagem"] = rel.suffix.lstrip(".").lower()
    return info


def parse_sources(text: str) -> list[tuple[str, str]]:
    out = []
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        folder, _, label = item.partition("=")
        out.append((folder.strip(), (label or folder).strip()))
    return out


def ratio(a, b, nd=2):
    return round(a / b, nd) if b else ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("root", type=Path, help="pasta raiz (contém as pastas AtCoder e IA)")
    ap.add_argument("--sources", default="AtCoder=humano,IA=IA",
                    help="pasta=rótulo separados por vírgula (padrão: AtCoder=humano,IA=IA)")
    ap.add_argument("--rules-python", type=Path, help="inspeções para Python (um ID por linha)")
    ap.add_argument("--rules-cpp", type=Path, help="inspeções para C/C++ (um ID por linha)")
    ap.add_argument("--linter-python", default="jetbrains/qodana-python-community:2026.2")
    ap.add_argument("--linter-cpp", default="jetbrains/qodana-clang:2026.2")
    ap.add_argument("--c-std", default="c17")
    ap.add_argument("--cpp-std", default="c++20")
    ap.add_argument("--cpp-flags", default="", help='flags extras do compilador, ex: "-I/caminho/ac-library"')
    ap.add_argument("--container-root", default="/data/project",
                    help="caminho do projeto DENTRO do container Docker ('' para usar o caminho local)")
    ap.add_argument("--layout", default="contest,problem",
                    help="níveis de pasta dentro de cada origem, acima do arquivo (padrão: contest,problem)")
    ap.add_argument("--scope", choices=["contest", "all"], default="contest",
                    help="'contest': uma execução por campeonato; 'all': uma execução por origem")
    ap.add_argument("--out", default="relatorio", help="prefixo dos CSVs de saída")
    ap.add_argument("--results-root", type=Path, default=Path("qodana_results"))
    args = ap.parse_args()

    group_cfg = {}
    if args.rules_python:
        group_cfg["python"] = {"rules": load_rules(args.rules_python), "linter": args.linter_python}
    if args.rules_cpp:
        group_cfg["cpp"] = {"rules": load_rules(args.rules_cpp), "linter": args.linter_cpp}
    if not group_cfg or any(not c["rules"] for c in group_cfg.values()):
        sys.exit("Informe --rules-python e/ou --rules-cpp com pelo menos uma regra.")

    sources = parse_sources(args.sources)
    layout = [x.strip() for x in args.layout.split(",") if x.strip()]
    root = args.root.resolve()
    ensure_git_repo(root)
    extra_flags = shlex.split(args.cpp_flags)

    id_cols = ["origem"] + layout + ["submissao", "linguagem", "grupo"]
    metric_cols = ["status", "linhas", "total_problemas", "problemas_por_100_linhas",
                   *[f"nivel_{l}" for l in LEVELS]]
    rule_cols = [f"{GROUPS[g]['prefix']}:{r}" for g, c in group_cfg.items() for r in c["rules"]]
    detail_cols = id_cols + metric_cols + rule_cols + ["erro"]

    summary = defaultdict(lambda: {"n": 0, "falhas": 0, "com_problema": 0, "linhas": 0,
                                   "total": 0, "rules": Counter()})

    args.results_root.mkdir(parents=True, exist_ok=True)
    with open(f"{args.out}_submissoes.csv", "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=detail_cols)
        writer.writeheader()

        for src_dir, origem in sources:
            src_root = root / src_dir
            if not src_root.is_dir():
                print(f"[!] pasta '{src_dir}' não encontrada em {root}; ignorando.")
                continue
            units = ([(d, d.name) for d in sorted(src_root.iterdir())
                      if d.is_dir() and d.name not in IGNORED_DIRS]
                     if args.scope == "contest" else [(src_root, "")])

            for project, prefix in units:
                for group, cfg in group_cfg.items():
                    files = find_files(project, GROUPS[group]["exts"])
                    if not files:
                        continue
                    print(f"[+] {src_dir}/{prefix}/{group}: {len(files)} arquivos ...".replace("//", "/"), flush=True)
                    results_dir = args.results_root / src_dir / (prefix or "_all") / group
                    results_dir.mkdir(parents=True, exist_ok=True)

                    # O Qodana roda em Docker e só enxerga a pasta do projeto: o qodana.yaml
                    # precisa ficar nela (nome padrão) e é removido ao final.
                    config = project / "qodana.yaml"
                    backup = None
                    if config.exists():
                        backup = config.with_name("qodana.yaml.bak_orig")
                        config.replace(backup)
                    write_qodana_yaml(config, cfg["linter"], cfg["rules"])

                    cc = None
                    build_dir = project / "build"
                    created_build = not build_dir.exists()
                    try:
                        if group == "cpp":
                            cc = make_compile_commands(project, files, args.container_root,
                                                       args.c_std, args.cpp_std, extra_flags)
                        proc = run_qodana(project, results_dir, cfg["linter"])
                    finally:
                        if cc:
                            cc.unlink(missing_ok=True)
                        if created_build:
                            shutil.rmtree(build_dir, ignore_errors=True)
                        config.unlink(missing_ok=True)
                        if backup:
                            backup.replace(config)

                    sarif = results_dir / "qodana.sarif.json"
                    issues, error = {}, ""
                    if sarif.exists():
                        issues = parse_sarif(sarif)
                    else:
                        tail = (proc.stderr or proc.stdout or "sem SARIF").strip()[-300:].replace("\n", " ")
                        error = f"log completo: {results_dir / 'qodana.log'} | {tail}"
                        print(f"    FALHA (exit {proc.returncode}): veja {results_dir / 'qodana.log'}")

                    pfx = GROUPS[group]["prefix"]
                    for f in files:
                        rel_in_project = f.relative_to(project).as_posix()
                        row = {c: "" for c in detail_cols}
                        row.update(split_path(f.relative_to(src_root), layout))
                        row["origem"] = origem
                        row["grupo"] = group
                        row["linhas"] = loc = count_lines(f)
                        total = 0
                        by_rule = Counter()
                        if error:
                            row["status"], row["erro"] = "falha", error
                        else:
                            by_rule, by_level = issues.get(rel_in_project, (Counter(), Counter()))
                            total = sum(by_rule.values())
                            row.update(status="ok", total_problemas=total,
                                       problemas_por_100_linhas=ratio(total * 100, loc))
                            for l in LEVELS:
                                row[f"nivel_{l}"] = by_level.get(l, 0)
                            for r in cfg["rules"]:
                                row[f"{pfx}:{r}"] = by_rule.get(r, 0)
                        writer.writerow(row)

                        s = summary[(origem,) + tuple(row[c] for c in layout) + (group,)]
                        s["n"] += 1
                        if error:
                            s["falhas"] += 1
                        else:
                            s["linhas"] += loc
                            s["total"] += total
                            s["com_problema"] += 1 if total else 0
                            s["rules"].update({f"{pfx}:{k}": v for k, v in by_rule.items()})
                    fh.flush()

    # ---------- resumo por origem ----------
    sum_cols = ["origem"] + layout + ["grupo", "submissoes", "falhas", "submissoes_com_problema",
                                      "pct_com_problema", "linhas", "total_problemas",
                                      "media_problemas_por_submissao", "problemas_por_100_linhas"] + rule_cols
    with open(f"{args.out}_resumo.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=sum_cols)
        w.writeheader()
        for key, s in sorted(summary.items()):
            ok = s["n"] - s["falhas"]
            origem, group = key[0], key[-1]
            pfx = GROUPS[group]["prefix"]
            row = {c: "" for c in sum_cols}
            row.update(dict(zip(layout, key[1:-1])), origem=origem, grupo=group,
                       submissoes=s["n"], falhas=s["falhas"],
                       submissoes_com_problema=s["com_problema"],
                       pct_com_problema=ratio(100 * s["com_problema"], ok, 1),
                       linhas=s["linhas"], total_problemas=s["total"],
                       media_problemas_por_submissao=ratio(s["total"], ok),
                       problemas_por_100_linhas=ratio(100 * s["total"], s["linhas"]))
            for r in group_cfg[group]["rules"]:
                row[f"{pfx}:{r}"] = s["rules"].get(f"{pfx}:{r}", 0)
            w.writerow(row)

    # ---------- comparação lado a lado ----------
    labels = [lab for _, lab in sources]
    by_problem = defaultdict(dict)
    for key, s in summary.items():
        by_problem[key[1:]][key[0]] = s
    cmp_cols = layout + ["grupo"]
    for lab in labels:
        cmp_cols += [f"n_{lab}", f"media_problemas_{lab}", f"problemas_por_100_linhas_{lab}",
                     f"media_linhas_{lab}"]
    has_diff = "humano" in labels and "IA" in labels
    if has_diff:
        cmp_cols += ["dif_media_problemas_IA_menos_humano", "dif_problemas_por_100_linhas_IA_menos_humano"]
    with open(f"{args.out}_comparacao.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cmp_cols)
        w.writeheader()
        for key, per_origin in sorted(by_problem.items()):
            row = {c: "" for c in cmp_cols}
            row.update(dict(zip(layout + ["grupo"], key)))
            for lab in labels:
                s = per_origin.get(lab)
                if not s:
                    continue
                ok = s["n"] - s["falhas"]
                row[f"n_{lab}"] = s["n"]
                row[f"media_problemas_{lab}"] = ratio(s["total"], ok)
                row[f"problemas_por_100_linhas_{lab}"] = ratio(100 * s["total"], s["linhas"])
                row[f"media_linhas_{lab}"] = ratio(s["linhas"], ok, 1)
            if has_diff:
                for col, a, b in [("dif_media_problemas_IA_menos_humano", "media_problemas_IA", "media_problemas_humano"),
                                  ("dif_problemas_por_100_linhas_IA_menos_humano",
                                   "problemas_por_100_linhas_IA", "problemas_por_100_linhas_humano")]:
                    if row[a] != "" and row[b] != "":
                        row[col] = round(row[a] - row[b], 2)
            w.writerow(row)

    print(f"\nGerado: {args.out}_submissoes.csv, {args.out}_resumo.csv e {args.out}_comparacao.csv")


if __name__ == "__main__":
    main()