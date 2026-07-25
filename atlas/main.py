from src.services.root.root import definir_categoria_da_pergunta
from src.services.produto.produtos import gerar_resposta_sobre_produtos
from src.services.suporte.suporte import gerar_resposta_sobre_suporte
from src.services.renda_extra.renda_extra import gerar_resposta_sobre_renda_extra


class ResultadoResposta:
    def __init__(self, texto: str, handoff_requested: bool = False, handoff_reason: str | None = None):
        self.texto = texto
        self.handoff_requested = handoff_requested
        self.handoff_reason = handoff_reason


def gerar_resposta(pergunta: str, agent_id: str, agent_name: str) -> ResultadoResposta:
    categoria = definir_categoria_da_pergunta(pergunta)

    if categoria == "atendimento_humano":
        return ResultadoResposta(
            texto="",
            handoff_requested=True,
            handoff_reason="Cliente pediu atendimento humano ou demonstrou frustração que o atendimento automático não resolveria.",
        )

    if categoria == "produto":
        texto = gerar_resposta_sobre_produtos(pergunta, agent_id, agent_name, categoria)
    elif categoria == "renda-extra":
        texto = gerar_resposta_sobre_renda_extra(pergunta, agent_id, agent_name, categoria)
    else:
        texto = gerar_resposta_sobre_suporte(pergunta, agent_id, agent_name, categoria)

    return ResultadoResposta(texto=texto)


if __name__ == "__main__":
    print(gerar_resposta("Como ganho dinheiro com renda extra", "fluxy-id", "fluxy").texto)
