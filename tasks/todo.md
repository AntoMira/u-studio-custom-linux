# Tarefas: Widget Dedicado de GPU (`gpu_monitor`)

- [x] **1. Expandir Extração de Métricas de GPU em `main.py`** <!-- id: 0 -->
    - Extrair `gpu_usage`, `gpu_vram` e `gpu_temp` do payload do LibreHardwareMonitor
- [x] **2. Suportar `action_type: gpu_monitor` em `main.py` e `deck_manager.py`** <!-- id: 1 -->
    - Permitir passar rótulos de colunas customizados (`GPU`, `RAM`, `TMP`) para o botão
- [x] **3. Adicionar Botão de GPU em `config.yaml`** <!-- id: 2 -->
    - Mapear um botão dedicado (`index: 7`) para a GPU ("RTX 5080")
- [x] **4. Testar e Validar** <!-- id: 3 -->
    - Executar `python3 server/verify.py`
    - Inspecionar `output_sim/button_7.png`
