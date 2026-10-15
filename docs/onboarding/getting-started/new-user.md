# Getting Started — Usuário novo no ecossistema

> Perfil: quem nunca usou o The Forge. As 8 seções obrigatórias do §10.3; todos os comandos
> existem na superfície instalada — nada aqui é aspiracional.

## Pré-requisitos

- Linux ou Windows (Git Bash/WSL nos scripts de instalação)
- Python >= 3.11 (the-forge; especialistas >= 3.10/3.12 conforme o repo)
- `git` no PATH

## Instalação

```bash
cd seu/projeto
theforge setup
```

O wizard guia escopo → hosts → perfil → plano → **aprovação única** → aplicação.
Para instalar só o núcleo sem o wizard: `pip install -e .` no checkout do
`the-forge` + `theforge init` no seu projeto.

## Configuração

`theforge setup` já cobre a configuração (hosts, perfil, componentes).
Revisar depois: `theforge status`, `theforge hosts`.

## Primeiro comando

```bash
theforge doctor
```

## Resultado esperado

```text
os.......... ok    Linux ...
python...... ok    3.12.x
git......... ok    /usr/bin/git
workspace... ok    <projeto>/.forge
healthy
```

## Explicação do resultado

`doctor` verifica pré-requisitos do ambiente e dos providers
registrados. `healthy` significa que o núcleo e cada provider instalado
responderam à verificação real — um `warn`/`fail` vem com a causa, nunca
silenciado.

## Resolução de problemas

| Sintoma | Ação |
|---|---|
| `theforge: command not found` | reabra o shell ou ative o venv onde instalou |
| `workspace.... not initialized` | rode `theforge init` dentro do projeto |
| provider `warn` | `theforge doctor` mostra a causa por linha |

## Próximos passos

- Escolha o guia do seu perfil nesta pasta (backend, data, platform…)
- `theforge task "primeira tarefa"` — primeira execução real
- Golden Paths em `docs/onboarding/golden-paths/`

