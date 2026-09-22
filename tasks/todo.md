# Tarefas: Barra Lateral de Consumo no Widget tasmota_power

- [x] **1. Criar Plano de Implementação e Alinhar com o Usuário** <!-- id: 0 -->
    - Definir posição e dimensões da barra vertical lateral esquerda no botão (ex: `x=16`, largura `12px`, altura `156px`).
    - Definir interpolação de cor `get_scale_color(pct)` (0% Verde -> 50% Amarelo -> 100% Vermelho).
    - Suporte ao parâmetro `max_power` no `config.yaml` (padrão: `1000`).
- [x] **2. Atualizar Renderizador em `server/deck_manager.py`** <!-- id: 1 -->
    - Adicionar renderização da barra vertical de energia na borda esquerda quando `power_val` for informado.
- [x] **3. Atualizar Lógica em `server/main.py`** <!-- id: 2 -->
    - Ler `max_power` da configuração do botão (padrão `1000.0`).
    - Calcular a porcentagem de energia e repassar `power_val` e `max_power` para `update_button`.
- [x] **4. Atualizar Configuração (`server/config.yaml`)** <!-- id: 3 -->
    - Documentar `max_power` e incluir no exemplo do botão 8.
- [x] **5. Atualizar Suíte de Verificação (`server/verify.py`)** <!-- id: 4 -->
    - Adicionar teste de renderização da barra de potência lateral e validar geração da imagem.

## Resultados e Revisão
- Todos os testes da suíte `server/verify.py` passaram com sucesso (100%).
- Barra de progresso vertical adicionada na borda esquerda do widget `tasmota_power` utilizando a mesma graduação de cores dos widgets do PC (Verde -> Amarelo -> Vermelho).
- Imagem simulada (`button_8.png`) gerada com sucesso demonstrando a barra lateral proporcional a `max_power`.
