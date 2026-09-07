# Tarefas: Ativação Automática da Tela por Itens Monitorados (PC / Hue) durante Horário de Sleep

- [x] **1. Criar Plano de Implementação e Definir Casos de Teste** <!-- id: 0 -->
    - Analisar comportamento do despertar quando itens em `keep_screen_on_pc_monitor` ou `keep_screen_on_hue_ids` forem ligados durante a janela de sleep.
- [x] **2. Modificar `check_screen_sleep()` em `server/main.py`** <!-- id: 1 -->
    - Permitir que `keep_awake_override` desperte a tela (`screen_on = True` e brilho 80) mesmo estando dentro do `in_sleep_window`.
    - Garantir que ao desligar os itens monitorados, a tela volte a desligar se estiver no horário de sleep.
- [x] **3. Atualizar e Executar Testes em `server/verify_sleep.py`** <!-- id: 2 -->
    - Simular tela desligada no horário de sono.
    - Ligar lâmpada Hue monitorada / PC e verificar se a tela religa automaticamente.
    - Desligar lâmpada / PC e verificar se a tela desliga novamente.
- [x] **4. Reiniciar o Serviço ou Validar em Produção** <!-- id: 3 -->
    - Executar suíte de validação e instruir reinício do serviço.

## Resultados e Revisão
- Todos os testes automatizados da suíte `server/verify_sleep.py` passaram com sucesso (100%).
- Cenários testados:
  1. Tela em modo de sono durante o horário programado (`in_sleep_window == True`) permanece desligada se itens estiverem desligados.
  2. Ao ligar lâmpada monitorada (`keep_screen_on_hue_ids`), a tela desperta automaticamente e define brilho para 80%.
  3. Ao desligar a lâmpada monitorada, a tela volta para o modo de sono automaticamente.
  4. Ao receber telemetria de PC monitorado (`keep_screen_on_pc_monitor`), a tela desperta automaticamente e define brilho para 80%.
  5. Ao cessar a telemetria do PC monitorado, a tela desliga automaticamente.
  6. Recuperação fora da janela de sono funcionando normalmente.
