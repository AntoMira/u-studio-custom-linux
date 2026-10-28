# Tarefas: Debouncer de Teclas no Stream Deck (Prevenção de Duplo Clique)

- [x] **1. Configuração e Parâmetro Global de Debounce** <!-- id: 0 -->
    - Adicionado `button_debounce_seconds: 0.35` em `server/config.yaml` sob a seção de configurações globais com documentação clara.
    - Atualizado `server/main.py:load_config()` para ler `button_debounce_seconds` (padrão `0.35`).
    - Repassado `debounce_seconds` na instanciação de `DeckManager` em `server/main.py`.
- [x] **2. Implementação do Debouncer no `DeckManager` (`server/deck_manager.py`)** <!-- id: 1 -->
    - Adicionado `debounce_seconds: float = 0.35` ao `__init__` e inicializado mapa de timestamps `self.last_press_time = {}`.
    - No handler físico `_on_hardware_keypress(key_index, pressed)`:
      - Descarte imediato se `not pressed` (ignora liberação da tecla).
      - Filtro de repique/duplo clique por botão: descarta eventos ocorridos dentro da janela `debounce_seconds`.
      - Registro de `last_press_time[key_index] = now` antes de avaliar wake da tela ou callbacks (evita que repique de contato logo após o despertar da tela ligue a lâmpada acidentalmente).
    - No método `simulate_press(button_index, force=False)`:
      - Aplicada mesma lógica de debounce por botão para paridade de testes e simulador.
      - Retorno booleano indicando se o clique foi processado (`True`) ou descartado pelo debounce (`False`).
    - Adicionado método utilitário `reset_debounce(button_index=None)` para limpeza sob demanda.
- [x] **3. Atualizar e Expandir Suíte de Testes Automatizados** <!-- id: 2 -->
    - Atualizado `test_config_parsing` em `server/verify.py` para validar `button_debounce_seconds` (> 0).
    - Criado teste automatizado dedicado de debounce (`test_button_debounce`) cobrindo:
      - Clique inicial aceito.
      - Clique consecutivo imediato no mesmo botão rejeitado (debounced).
      - Clique imediato em outro botão aceito (debounce independente por botão).
      - Clique aceito após transcorrido o intervalo de debounce.
      - Parâmetro `force=True` para bypass quando necessário.
      - Eventos de liberação de tecla (`pressed=False`) ignorados.
      - Proteção contra repique durante o despertar da tela (wake-up bounce).
    - Executados `server/verify.py` e `server/verify_sleep.py` com 100% de sucesso.
- [x] **4. Documentar Resultados e Revisão** <!-- id: 3 -->
    - Resultados e validações registrados.

## Resultados e Revisão
- Todos os testes da suíte automatizada `server/verify.py` e `server/verify_sleep.py` passaram com sucesso (100%).
- O debouncer foi implementado na camada do hardware (`DeckManager`), garantindo que:
  1. Qualquer oscilação ou clique duplo mecânico no mesmo botão físico em um intervalo inferior a 0.35s (configurável via `button_debounce_seconds` no `config.yaml`) seja descartado antes de acionar alternâncias no Philips Hue, timers ou chamadas MQTT/Weather.
  2. Cliques em botões distintos não interferem entre si (debounce isolado por índice de botão).
  3. Repiques que ocorram ao pressionar uma tecla para acordar o visor são igualmente filtrados, impedindo que a luz seja acesa ou apagada no mesmo instante em que a tela acende.
