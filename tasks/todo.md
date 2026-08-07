# Tarefas: Prevenção de Auto-Sleep por Status de PC e Lâmpadas Hue

- [x] **1. Adicionar `keep_screen_on_pc_monitor` e `keep_screen_on_hue_ids` ao `config.yaml`** <!-- id: 0 -->
    - Adicionar chaves e comentários documentando a sintaxe
- [x] **2. Carregar Novas Chaves em `load_config()` em `main.py`** <!-- id: 1 -->
    - Tratar listas ou strings separadas por vírgula para os IDs de lâmpadas e IPs de PC
- [x] **3. Atualizar `check_screen_sleep()` em `main.py`** <!-- id: 2 -->
    - Prevenir o desligamento do display caso algum PC monitorado esteja online ou alguma lâmpada Hue listada esteja ligada
- [x] **4. Testar via `verify.py` e Validar** <!-- id: 3 -->
    - Executar a suíte automatizada (`verify_sleep.py`)
