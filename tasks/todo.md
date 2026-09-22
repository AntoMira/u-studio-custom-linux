# Tarefas: Widget de Temperatura e Umidade Tasmota via MQTT

- [x] **1. Criar Plano de Implementação e Alinhar com o Usuário** <!-- id: 0 -->
    - Definir estrutura do `config.yaml` para MQTT (host, porta, usuário, senha) e widget `tasmota_sensor` (tópico).
    - Definir regras de parsing de payload Tasmota MQTT (temperatura e umidade).
    - Definir renderização gráfica da temperatura (mesma escala de cores `get_color_for_temp`, container escuro arredondado, ícone de termômetro e texto `Temp°C | Hum%`).
- [x] **2. Implementar Módulo de Serviço MQTT (`server/mqtt_service.py`)** <!-- id: 1 -->
    - Suporte a `paho-mqtt` com autenticação e fallback gracioso se não instalado/desconectado.
    - Loop de escuta/assinatura dos tópicos dos widgets configurados.
    - Parser resiliente de JSON Tasmota (sub-chaves como `AM2301`, `DHT11`, `BME280`, `DS18B20`, `SHT3X` ou raízes `Temperature`/`Humidity`).
- [x] **3. Atualizar Renderizador em `server/deck_manager.py`)** <!-- id: 2 -->
    - Adicionar desenho geométrico do ícone de **Termômetro** (tubo, bulbo, mercúrio e marcações laterais).
    - Aplicar cor de fundo sólida/gradiente `get_color_for_temp(temp)` e container translúcido para o widget Tasmota.
- [x] **4. Atualizar Aplicação Principal em `server/main.py`)** <!-- id: 3 -->
    - Carregar credenciais MQTT de `config.yaml`.
    - Inicializar `MqttService` e registrar tópicos dos widgets.
    - Atualizar estado dos botões ao receber atualizações de telemetria MQTT.
- [x] **5. Adicionar Dependência e Atualizar `config.yaml`)** <!-- id: 4 -->
    - Incluir `paho-mqtt` em `requirements.txt`.
    - Exemplo de configuração de broker MQTT com autenticação e novo widget no `config.yaml`.
- [x] **6. Criar e Executar Suíte de Testes/Verificação (`server/verify.py`)** <!-- id: 5 -->
    - Validar parsing de configuração e payloads JSON Tasmota.
    - Validar renderização de imagem do botão com escala de cores e ícone de termômetro.

## Resultados e Revisão
- Todos os testes da suíte `server/verify.py` passaram com sucesso (100%).
- `MqttService` criado em `server/mqtt_service.py` com suporte a autenticação, reconexão e parsing de JSON Tasmota (`AM2301`, `DHT11`, `BME280`, `DS18B20`, `SHT3X`, `SI7021`, etc.).
- Desenho geométrico do ícone de termômetro implementado no `DeckManager`.
- Botão simulado de teste (`button_8.png`) gerado com sucesso demonstrando fundo colorido pela temperatura (24.5°C -> Azul), container arredondado escuro, ícone de termômetro e status `24.5°C | 52%`.
