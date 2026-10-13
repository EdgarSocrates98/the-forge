# Receita — instalar o the-forge (um comando, de verdade)

**O quê:** `./setup.sh` (ou `setup.ps1`) roda o bootstrap canônico:
venv própria, runtime, launcher `forge`, registro e smoke-verify.
**Por que:** "clone once, setup once" — a mesma pipeline governada
(discover → venv → install → launcher → register → verify) funciona em
qualquer máquina sem tocar o venv do projeto.
**Quando:** primeira instalação numa máquina ou workspace novo.
**Quando não:** para reparar drift numa instalação existente —
`forge install doctor`/`repair`; para desinstalar, `forge uninstall`.

## Problema

"Clonei o monorepo de forges — como coloco o `forge` no PATH?"

## Pré-requisitos

Python ≥3.10 no PATH. O bootstrap é stdlib-only e só sai à rede no
passo explícito `pip install` (`--allow-download`).

## Passo a passo

```bash
./setup.sh                       # Linux/macOS/Git Bash
./setup.ps1                      # Windows PowerShell
theforge --version && forge doctor  # verificação
theforge init                       # dentro do workspace-alvo: cria .forge/
```

Dry-run para inspecionar o plano antes de escrever:

```bash
python scripts/forge_bootstrap.py --dry-run --verbose
```

## Saída esperada / interpretação

O bootstrap termina com um relatório por etapa (PASS/REFUSED). Launcher
criado → `forge` resolve. `forge doctor` deve listar checks `PASS`.

## Verificação

`forge doctor` num shell novo (o PATH precisa refletir o launcher).
`forge hosts observe` deve achar seus hosts de IA.

## Limitações

Sem Python ≥3.10 no PATH o bootstrap recusa com mensagem clara (não
instala Python por você). `--no-launcher` instala sem expor `forge`.

## Erros comuns

| Sintoma | Causa | Ação |
|---|---|---|
| `no python on PATH` | Python ausente/não-exportado | instale ≥3.10 ou passe `--python` |
| recibo `REFUSED` em download | política `--allow-download` ausente | revise e rode com a flag explícita |
| `forge` não resolve | PATH do shell velho | novo shell, ou use o caminho impresso |

## Uso por agentes

O bootstrap é determinístico e auditável (`--dry-run` imprime o plano
completo). Agente pode propor `--dry-run` e deixar o humano executar.
