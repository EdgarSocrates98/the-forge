# Remaining risks

1. **External provider authentication — BLOCKED:** falta uma sessão autorizada
   para comprovar execução agêntica externa e seus limites de custo/política.
2. **Cloud parity — BLOCKED:** AWS/Azure/GCP não foram exercitados neste
   ambiente; a prova local não substitui IAM, rede e quotas reais.
3. **Remote Product Forge — NOT_RUN:** o Portal tem cliente e estados reais, mas
   precisa de uma sessão autenticada contra um backend Product Forge implantado.
4. **Spark AWS full rerun — NOT_RUN:** após a correção de allowlist, foi
   executado o alvo afetado e o CI do PR; a suíte de 4h não foi repetida.

Nenhum risco P0 local permaneceu aberto. Os itens acima são pré-condições para
promover `CONDITIONAL GO` a `GO` de produção.
