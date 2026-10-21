from event_types import EventType

print(EventType.BOTAO_APERTADO.generate_payload())
print(EventType.JOGO_FINALIZADO.generate_payload(data={"QtdDePontos": 15}))
print(EventType.JOGO_FINALIZADO.generate_payload(data={"QtdDePontos": 5}))
