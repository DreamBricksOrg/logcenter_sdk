# Log Sender SDK

## 🚀 Características Principais

### Arquitetura Modular
- **LogSenderConfig**: Configuração centralizada e validada
- **LogEntry**: Modelo de dados estruturado com validação Pydantic
- **LogStorage**: Gerenciamento de armazenamento local em CSV
- **LogTransmitter**: Responsável pelo envio HTTP dos logs
- **LogSender**: Classe principal que orquestra todas as funcionalidades

### Funcionalidades Avançadas
- ✅ **Envio Assíncrono e Síncrono**: Suporte completo para ambos os modos
- ✅ **Armazenamento Local**: Persistência em CSV com backup automático
- ✅ **Envio em Lote**: Processamento eficiente de múltiplos logs
- ✅ **Retry Automático**: Tentativas com backoff exponencial
- ✅ **Background Processing**: Worker em thread separada
- ✅ **Context Manager**: Gerenciamento automático de recursos
- ✅ **Configuração por Ambiente**: Suporte a variáveis de ambiente
- ✅ **Validação Robusta**: Validação de dados com Pydantic
- ✅ **Níveis de Log**: DEBUG, INFO, WARNING, ERROR, CRITICAL

## 📦 Instalação

```bash
pip install -r requirements.txt
```

### Dependências
- `httpx>=0.24.0` - Cliente HTTP assíncrono
- `pydantic>=2.0.0` - Validação de dados
- `structlog>=23.1.0` - Logging estruturado
- `python-dotenv==1.1.1` - Gerenciamento de variáveis de ambiente

## 🔧 Configuração

### Configuração Manual

```python
from log_sender import LogSenderConfig, LogSender

config = LogSenderConfig(
    log_api="https://api.exemplo.com",
    project_id="meu-projeto",
    upload_delay=10,           # Intervalo de envio em segundos
    log_dir="logs",           # Diretório para armazenamento local
    timeout=30,               # Timeout HTTP
    max_retries=3,            # Máximo de tentativas
    batch_size=100,           # Tamanho do lote
    enable_backup=True,       # Habilitar backup
    enable_async=True,        # Modo assíncrono
    headers={"Authorization": "Bearer token"}  # Headers customizados
)

log_sender = LogSender(config)
```

### Configuração por Variáveis de Ambiente

Crie um arquivo `.env`:
```env
LOG_API=https://api.exemplo.com
PROJECT_ID=meu-projeto
UPLOAD_DELAY=120
LOG_DIR=logs
```

```python
from log_sender import create_log_sender_from_env

log_sender = create_log_sender_from_env()
```

## 📝 Uso Básico

### Registrando Logs

```python
# Log simples
log_sender.log("Aplicação iniciada", level="INFO")

# Log com dados estruturados
log_sender.log(
    message="Usuário logado",
    level="INFO",
    tags=["auth", "login"],
    data={"user_id": 123, "ip": "192.168.1.1"},
    request={"id": "req-123"}
)

# Log de erro
log_sender.log(
    message="Erro na conexão com banco",
    level="ERROR",
    data={"error_code": "DB001", "retry_count": 3}
)
```

### Context Manager (Recomendado)

```python
with LogSender(config) as sender:
    sender.log("Processamento iniciado")
    # Processamento automático em background
    sender.log("Processamento concluído")
# Cleanup automático ao sair do contexto
```

### Controle Manual do Background Worker

```python
log_sender = LogSender(config)

# Iniciar processamento em background
log_sender.start_background_sender()

# Registrar logs (serão enviados automaticamente)
log_sender.log("Log 1")
log_sender.log("Log 2")

# Parar processamento
log_sender.stop_background_sender()
```

## 🔄 Modos de Operação

### Modo Assíncrono (Padrão)
```python
config = LogSenderConfig(
    log_api="https://api.exemplo.com",
    project_id="projeto",
    enable_async=True  # Padrão
)
```

### Modo Síncrono
```python
config = LogSenderConfig(
    log_api="https://api.exemplo.com",
    project_id="projeto",
    enable_async=False
)
```

## 📊 Monitoramento e Estatísticas

```python
stats = log_sender.get_stats()
print(f"Logs pendentes: {stats['pending_logs']}")
print(f"Worker ativo: {stats['running']}")
print(f"Configuração: {stats['config']}")
```

## 🔧 Exemplos Avançados

### Integração com Aplicação Web

```python
from flask import Flask, request
from log_sender import create_log_sender_from_env

app = Flask(__name__)
log_sender = create_log_sender_from_env()

@app.before_first_request
def setup_logging():
    log_sender.start_background_sender()

@app.route('/api/users', methods=['POST'])
def create_user():
    try:
        # Lógica da aplicação
        user_data = request.json
        
        # Log de auditoria
        log_sender.log(
            message="Usuário criado",
            level="INFO",
            tags=["user", "create"],
            data={"user_id": user_data.get("id")},
            request={"id": request.headers.get("X-Request-ID")}
        )
        
        return {"status": "success"}
    except Exception as e:
        # Log de erro
        log_sender.log(
            message=f"Erro ao criar usuário: {str(e)}",
            level="ERROR",
            tags=["user", "error"],
            data={"error": str(e)}
        )
        return {"status": "error"}, 500

@app.teardown_appcontext
def cleanup_logging(exception):
    if exception:
        log_sender.stop_background_sender()
```

### Uso com Instância Global

```python
from log_sender import set_log_sender_instance, get_log_sender_instance

# Configurar instância global
sender = LogSender(config)
set_log_sender_instance(sender)

# Usar em qualquer lugar da aplicação
def minha_funcao():
    sender = get_log_sender_instance()
    if sender:
        sender.log("Função executada")
```

### Tratamento de Erros

```python
from log_sender import LogSenderException, ConfigurationError, NetworkError

try:
    config = LogSenderConfig(
        log_api="",  # API vazia causará erro
        project_id="projeto"
    )
except ConfigurationError as e:
    print(f"Erro de configuração: {e}")

try:
    log_sender.send_log("Teste de conectividade")
except NetworkError as e:
    print(f"Erro de rede: {e}")
```

## 📁 Estrutura de Arquivos

O SDK cria automaticamente a seguinte estrutura:

```
logs/
├── datalogs.csv        # Logs pendentes
└── datalogs_backup.csv # Backup dos logs enviados
```

### Formato do CSV

```csv
id,timestamp,project,level,tags,message,data,request_id
uuid-123,2024-01-15T10:30:00Z,meu-projeto,info,"[""auth""]",Usuário logado,"{""user_id"": 123}",req-456
```

## 🔒 Segurança

- **Headers Customizados**: Suporte a autenticação via headers
- **Timeout Configurável**: Evita travamentos em requisições
- **Validação de Dados**: Pydantic garante integridade dos dados
- **Backup Local**: Logs não são perdidos em caso de falha de rede

## ⚡ Performance

- **Envio em Lote**: Reduz overhead de rede
- **Processamento Assíncrono**: Não bloqueia a aplicação principal
- **Backoff Exponencial**: Evita spam em caso de falhas
- **Thread Separada**: Worker dedicado para envio

## 🐛 Troubleshooting

### Logs não estão sendo enviados
1. Verifique a conectividade com a API
2. Confirme as credenciais/headers
3. Verifique os logs de erro no console
4. Confirme se o background worker está ativo

### Performance lenta
1. Ajuste o `batch_size` para lotes maiores
2. Reduza o `upload_delay`
3. Use modo assíncrono (`enable_async=True`)

### Arquivos CSV corrompidos
1. Verifique permissões do diretório `log_dir`
2. Confirme espaço em disco disponível
3. Use `enable_backup=True` para redundância

## 📄 Licença

Este projeto está sob licença MIT. Veja o arquivo LICENSE para mais detalhes.

## 🤝 Contribuição

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📞 Suporte

Para dúvidas ou problemas, abra uma issue no repositório do projeto.