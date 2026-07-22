<#
COMO CONFIGURAR PARA RODAR AO INICIAR O WINDOWS:

Método 1: Agendador de Tarefas (Recomendado - Roda antes de fazer o login)
1. Pressione Win + R, digite 'taskschd.msc' e aperte Enter.
2. No painel direito, clique em "Criar Tarefa...".
3. Na guia "Geral":
   - Defina o nome (ex: "Ligar Monitor Philips Hue").
   - Em "Opções de segurança", selecione "Executar estando o usuário conectado ou não" (isso permite rodar antes do login).
   - Marque a opção "Executar com privilégios mais altos".
4. Na guia "Disparadores", clique em "Novo...":
   - Em "Iniciar a tarefa", selecione "Ao iniciar" (At startup). Clique em OK.
5. Na guia "Ações", clique em "Novo...":
   - Em "Ação", selecione "Iniciar um programa".
   - Em "Programa/script", digite: powershell.exe
   - Em "Adicionar argumentos (opcional)", cole:
     -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\caminho\completo\para\ligar_luz.ps1"
     (Certifique-se de usar o caminho completo correto para onde salvou este script)
   - Clique em OK.
6. Clique em OK para salvar a tarefa. O Windows solicitará as credenciais do seu usuário para salvar e poder executar antes do login.

Método 2: Pasta Inicializar (Rápido, mas mostra a janela do PowerShell brevemente)
1. Pressione Win + R, digite 'shell:startup' e aperte Enter.
2. Crie um arquivo com a extensão .bat na pasta aberta (ex: 'ligar_monitor.bat').
3. Edite o arquivo .bat e cole a seguinte linha:
   powershell.exe -ExecutionPolicy Bypass -File "C:\caminho\completo\para\ligar_luz.ps1"
#>

# Configurações do Philips Hue
$bridgeIp = "[ip hue hub]"  # Substitua pelo IP da sua Hue Bridge
$apiToken = "[api token]"  # Substitua pelo seu token/username do Philips Hue
$lightId = "6"  # ID da tomada do monitor

# Corpo da requisição para ligar o dispositivo
$body = @{
    on = $true
} | ConvertTo-Json

# URI da API do Philips Hue (V1)
$uri = "http://$bridgeIp/api/$apiToken/lights/$lightId/state"

Write-Output "Enviando requisição para ligar o monitor (ID: $lightId)..."

try {
    $response = Invoke-RestMethod -Uri $uri -Method Put -Body $body -ContentType "application/json"
    Write-Output "Sucesso! Resposta da Bridge:"
    Write-Output ($response | ConvertTo-Json)
} catch {
    Write-Error "Falha ao conectar ou enviar comando para a Hue Bridge. Verifique o IP e o Token. Detalhes: $_"
}

