"""Actionable diagnostics (cycle 16.1, FRENTE F §10.2).

Every failing doctor check gets a structured guidance block in the
``PROBLEMA / CAUSA PROVÁVEL / AÇÃO / ESTADO`` shape (the operator's
language — the spec's wording, kept verbatim). ``causa`` is always a
*probable* cause: the doctor reports observed evidence and the most
likely explanation, never certainty it does not have.
"""

from __future__ import annotations

from typing import Final

_GUIDANCE: Final[tuple[tuple[str, dict[str, str]], ...]] = (
    # --- missing runtime ---------------------------------------------------
    (
        "python",
        {
            "problema": "runtime Python incompatível ou ausente",
            "causa": "interpretador < 3.11 ou fora do PATH",
            "acao": "instale Python >= 3.11 e reexecute `theforge doctor`",
        },
    ),
    (
        "git",
        {
            "problema": "git não encontrado",
            "causa": "git ausente do PATH neste ambiente",
            "acao": "instale git ou ajuste PATH; estado git do workspace fica UNVERIFIED até lá",
        },
    ),
    # --- workspace / registry -----------------------------------------------
    (
        "workspace",
        {
            "problema": "workspace não inicializado ou não gravável",
            "causa": "`theforge init` nunca rodou aqui ou permissões mudaram",
            "acao": "rode `theforge init` no root ou corrija permissões de .forge/",
        },
    ),
    (
        "registry",
        {
            "problema": "registry com aviso ou erro",
            "causa": "providers.toml/cache desatualizado ou corrompido",
            "acao": "`theforge registry refresh`; persistindo, remova o "
            "arquivo indicado e deixe o cache ser recriado",
        },
    ),
    (
        "account-environment",
        {
            "problema": "ambiente de conta Forge inválido ou parcial",
            "causa": "variáveis `*_HOME/INSTALL_ROOT/VENV/PYTHON/CLI` apontam "
            "para caminhos movidos/removidos, ou o bootstrap instalou "
            "parcialmente",
            "acao": "rode o install.sh/install.ps1 da forge indicada para "
            "republicar o ambiente, ou remova as variáveis órfãs",
        },
    ),
    # --- stale manifest / provider health -------------------------------------
    (
        "provider",
        {
            "problema": "provider indisponível ou degradado",
            "causa": "manifest desatualizado (forge atualizada sem re-sync), "
            "trust alterado, ou o CLI do provider falhou no probe",
            "acao": "`theforge providers sync --yes` re-descreve e recalcula "
            "o surface; `theforge specialists doctor` tem o probe real",
        },
    ),
    # --- contracts -------------------------------------------------------------
    (
        "contracts",
        {
            "problema": "camada de contexto inválida ou desatualizada",
            "causa": ".forge/context escrito por versão antiga ou editado à mão",
            "acao": "`theforge install repair --yes` re-registra registry, "
            "routing e manifests de capacidade",
        },
    ),
    # --- MCP probe / config ------------------------------------------------------
    (
        "mcp",
        {
            "problema": "configuração ou probe MCP falhou",
            "causa": "server crashou no startup, argv mudou (atualização ou "
            "reinstalação), ou o host ainda não recarregou a config",
            "acao": "`theforge install mcp-verify` tem o handshake real; "
            "`theforge install repair --yes` regrava a chave gerenciada com "
            "o argv resolvido; reinicie o host antes de re-testar",
        },
    ),
    # --- drift / foreign file ----------------------------------------------------
    (
        "drift",
        {
            "problema": "arquivo gerenciado diverge do ledger",
            "causa": "edição manual, reinstalação fora do ledger, ou upgrade "
            "que mudou o conteúdo canônico",
            "acao": "`theforge install repair` mostra o plano; "
            "`--yes` regrava só o conteúdo gerenciado (nunca deleta nada)",
        },
    ),
    (
        "unsafe",
        {
            "problema": "caminho do ledger sai do root",
            "causa": "ledger adulterado ou corrompido (arquivo estranho)",
            "acao": "revise .forge/install/ledger.json à mão — repair "
            "recusa caminhos unsafe, não os corrige",
        },
    ),
    # --- secrets -------------------------------------------------------------------
    (
        "secrets",
        {
            "problema": "arquivo com formato de segredo dentro do escopo",
            "causa": "credencial gravada em caminho inspecionado (nomes "
            "observados, conteúdo nunca lido)",
            "acao": "movo-o para um gestor de segredos; o core redige o que "
            "persiste, mas o arquivo original continua no disco",
        },
    ),
    # --- receipts / ownership -------------------------------------------------------
    (
        "ownership",
        {
            "problema": "ledger de instalação ausente",
            "causa": "nada instalado neste escopo ou .forge/install removido",
            "acao": "`theforge install apply --yes` cria o ledger com a "
            "primeira escrita gerenciada",
        },
    ),
    (
        "receipts",
        {
            "problema": "último receipt registra falha",
            "causa": "apply/repair anterior abortou no meio",
            "acao": "o receipt é reexecutável: repita o comando com --yes; "
            "backups ficam em .forge/install/backups/",
        },
    ),
    # --- members -------------------------------------------------------------------
    (
        "members",
        {
            "problema": "membro de workspace sem instalação ou inconsistente",
            "causa": "membro adicionado depois do install auto, ou estado "
            "parcial de um apply anterior",
            "acao": "`theforge install auto --member <relpath> --yes` instala só naquele membro",
        },
    ),
)

_DEFAULT: Final[dict[str, str]] = {
    "problema": "verificação falhou",
    "causa": "indeterminada — veja o detalhe do check",
    "acao": "corrija a causa observada e reexecute `theforge doctor`",
}


def guidance_for(check_name: str, detail: str = "") -> dict[str, str]:
    """``{problema, causa, acao, estado}`` for a failing check.

    Match by check-name prefix (``drift:*`` → drift, ``mcp-*`` → mcp…);
    unknown checks get the honest default instead of no guidance.
    ``estado`` is the check's observed state, filled by the caller.
    """
    name = check_name.lower()
    for prefix, template in _GUIDANCE:
        if name == prefix or name.startswith(f"{prefix}:") or name.startswith(f"{prefix}-"):
            return {**template}
    if "unsafe" in detail.lower() or "unsafe" in name:
        return dict(_GUIDANCE[8][1])  # foreign/unsafe path template
    return dict(_DEFAULT)


def block_for(check_name: str, status: str, detail: str = "") -> dict[str, str]:
    """The full PROBLEMA/CAUSA/AÇÃO/ESTADO block for a check."""
    g = guidance_for(check_name, detail)
    return {
        "problema": g["problema"],
        "causa_provavel": g["causa"],  # labeled probable — never certain
        "acao": g["acao"],
        "estado": status,
    }


__all__ = ["block_for", "guidance_for"]
