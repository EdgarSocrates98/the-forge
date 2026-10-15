# Getting Started — Usuário de Copilot

> Perfil: host GitHub Copilot. As 8 seções obrigatórias do §10.3; todos os comandos
> existem na superfície instalada — nada aqui é aspiracional.

## Pré-requisitos

- Copilot habilitado no editor
- Guia do usuário novo concluído

## Instalação

```bash
theforge setup
# etapa de hosts → Copilot
```

O setup configura as instruções do Copilot a partir dos manifests —
a mesma fonte dos demais hosts.

## Configuração

Instruções ficam em `.github/copilot-instructions.md` (ou equivalente
do editor); `theforge hosts` reporta o estado observado.

## Primeiro comando

Abra o projeto no editor e peça ao Copilot para descrever a Forja
disponível para a sua intenção — o roteamento continua no `theforge`.

## Resultado esperado

O assistente cita os especialistas instalados via manifests,
com a mesma resposta `ambiguous` para intenções cruzadas.

## Explicação do resultado

Copilot é um host de interface — o routing determinístico e as
garantias de evidência vivem no The Forge, não no modelo do editor.

## Resolução de problemas

| Sintoma | Ação |
|---|---|
| instruções stale | `theforge setup` re-renderiza a partir dos manifests |
| host `NOT_DETECTED` | confirme a extensão/plugin do Copilot no editor |

## Próximos passos

- `docs/agentic.md` — adaptação por host (ADR-0056)
- Golden Path multi-forge

