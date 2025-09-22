"""
Log Sender SDK
"""

import asyncio
import csv
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field
from enum import Enum
import threading
import os

import httpx
from pydantic import BaseModel, Field, validator



class LogLevel(str, Enum):
    """Níveis de log suportados"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class LogStatus(str, Enum):
    """Status dos logs"""
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    RETRY = "retry"


@dataclass
class LogSenderConfig:
    """Configuração do Log Sender"""
    log_api: str
    project_id: str
    upload_delay: int = 120
    log_dir: str = "logs"
    timeout: int = 30
    max_retries: int = 3
    batch_size: int = 100
    enable_backup: bool = True
    enable_async: bool = True
    headers: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validação pós-inicialização"""
        if not self.log_api:
            raise ValueError("log_api é obrigatório")
        if not self.project_id:
            raise ValueError("project_id é obrigatório")
        
        # Criar diretório de logs se não existir
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)
    
    @property
    def csv_filename(self) -> str:
        return os.path.join(self.log_dir, 'datalogs.csv')
    
    @property
    def backup_filename(self) -> str:
        return os.path.join(self.log_dir, 'datalogs_backup.csv')


class LogEntry(BaseModel):
    """Modelo de dados para entrada de log com nova especificação"""
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    project: str
    level: str = "INFO"
    tags: List[str] = Field(default_factory=list)
    message: str
    data: Dict[str, Any] = Field(default_factory=dict)
    request_id: str
    
    @validator('timestamp', pre=True)
    def parse_timestamp(cls, v):
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace('Z', '+00:00'))
        return v
    
    @validator('level')
    def validate_level(cls, v):
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Level deve ser um de: {valid_levels}")
        return v.upper()
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat().replace('+00:00', 'Z')
        }


class LogSenderException(Exception):
    """Exceção base do Log Sender"""
    pass


class ConfigurationError(LogSenderException):
    """Erro de configuração"""
    pass


class NetworkError(LogSenderException):
    """Erro de rede"""
    pass


class ValidationError(LogSenderException):
    """Erro de validação"""
    pass


class LogStorage:
    """Gerenciador de armazenamento de logs"""
    
    def __init__(self, config: LogSenderConfig):
        self.config = config
        self._init_csv_files()
    
    def _init_csv_files(self):
        """Inicializa arquivos CSV com cabeçalhos corretos"""
        for filename in [self.config.csv_filename, self.config.backup_filename]:
            if not os.path.exists(filename):
                try:
                    with open(filename, mode='w', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        # Cabeçalhos para estrutura compatível com a nova API
                        writer.writerow(['id', 'timestamp', 'project', 'level', 'tags', 'message', 'data', 'request_id'])
                except Exception as e:
                    raise ConfigurationError(f"Falha ao inicializar CSV: {e}")
    
    def store_log(self, log_entry: LogEntry) -> bool:
        """Armazena log no CSV"""
        try:
            # Usar o novo formato compatível com a API
            row_data = {
                'id': log_entry.id,
                'timestamp': log_entry.timestamp.isoformat().replace('+00:00', 'Z'),
                'project': log_entry.project,
                'level': log_entry.level.lower(),
                'tags': json.dumps(log_entry.tags) if log_entry.tags else '[]',
                'message': log_entry.message,
                'data': json.dumps(log_entry.data) if log_entry.data else '{}',
                'request_id': log_entry.request_id
            }
            
            with open(self.config.csv_filename, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=['id', 'timestamp', 'project', 'level', 'tags', 'message', 'data', 'request_id'])
                writer.writerow(row_data)
            
            return True
        except Exception as e:
            return False
    
    def read_pending_logs(self) -> List[LogEntry]:
        """Lê logs pendentes do CSV"""
        logs = []
        try:
            if not os.path.exists(self.config.csv_filename):
                return logs
                
            with open(self.config.csv_filename, mode='r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        log_entry = LogEntry(
                            id=row['id'],
                            timestamp=datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00')),
                            project=row['project'],
                            level=row['level'].upper(),
                            tags=json.loads(row.get('tags', '[]')),
                            message=row['message'],
                            data=json.loads(row.get('data', '{}')),
                            request_id=row['request_id']
                        )
                        logs.append(log_entry)
                    except Exception as e:
                        pass  # Ignora entradas inválidas
        except Exception as e:
            pass  # Ignora erros de leitura
        
        return logs
    
    def clear_sent_logs(self, sent_logs: List[LogEntry]):
        """Remove logs enviados do arquivo principal"""
        try:
            all_logs = self.read_pending_logs()
            remaining_logs = [log for log in all_logs if log not in sent_logs]
            
            with open(self.config.csv_filename, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'timestamp', 'project', 'level', 'tags', 'message', 'data', 'request_id'])
                for log in remaining_logs:
                    writer.writerow([
                        log.id,
                        log.timestamp.isoformat(),
                        log.project,
                        log.level,
                        json.dumps(log.tags),
                        log.message,
                        json.dumps(log.data),
                        log.request_id
                    ])
        except Exception as e:
            pass  # Ignora erros de limpeza
    
    def backup_logs(self, logs: List[LogEntry]):
        """Faz backup dos logs enviados"""
        if not self.config.enable_backup:
            return
            
        try:
            with open(self.config.backup_filename, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                for log in logs:
                    writer.writerow([
                        log.id,
                        log.timestamp.isoformat(),
                        log.project,
                        log.level,
                        json.dumps(log.tags),
                        log.message,
                        json.dumps(log.data),
                        log.request_id
                    ])
        except Exception as e:
            pass  # Ignora erros de backup


class LogTransmitter:
    """Responsável pelo envio de logs"""
    
    def __init__(self, config: LogSenderConfig):
        self.config = config
        self.client = httpx.AsyncClient(timeout=config.timeout) if config.enable_async else httpx.Client(timeout=config.timeout)
    
    async def send_log_async(self, log_entry: LogEntry) -> bool:
        """Envia log de forma assíncrona"""
        url = f"{self.config.log_api}/logs/"
        
        # Converter para formato compatível com OpenAPI LogCreate schema
        payload = {
            'project': log_entry.project,
            'level': log_entry.level.lower(),
            'message': log_entry.message,
            'tags': log_entry.tags if log_entry.tags else [],
            'data': {
                'id': log_entry.id,
                'timestamp': log_entry.timestamp.isoformat().replace('+00:00', 'Z'),
                **log_entry.data
            },
            'request_id': log_entry.request_id
        }
        
        # Headers para JSON
        headers = {
            'Content-Type': 'application/json',
            **self.config.headers
        }
        
        for attempt in range(self.config.max_retries):
            try:
                response = await self.client.post(
                    url, 
                    json=payload, 
                    headers=headers
                )
                
                if response.status_code in [200, 201]:
                    return True
                    
            except Exception as e:
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Backoff exponencial
        
        return False
    
    def send_log_sync(self, log_entry: LogEntry) -> bool:
        """Envia log de forma síncrona"""
        url = f"{self.config.log_api}/logs/"
        
        # Converter para formato compatível com OpenAPI LogCreate schema
        payload = {
            'project': log_entry.project,
            'level': log_entry.level.lower(),
            'message': log_entry.message,
            'tags': log_entry.tags if log_entry.tags else [],
            'data': {
                'id': log_entry.id,
                'timestamp': log_entry.timestamp.isoformat().replace('+00:00', 'Z'),
                **log_entry.data
            },
            'request_id': log_entry.request_id
        }
        
        # Headers para JSON
        headers = {
            'Content-Type': 'application/json',
            **self.config.headers
        }
        
        for attempt in range(self.config.max_retries):
            try:
                response = self.client.post(
                    url, 
                    json=payload, 
                    headers=headers
                )
                
                if response.status_code == 200:
                    return True
            except Exception as e:
                if attempt < self.config.max_retries - 1:
                    time.sleep(2 ** attempt)  # Backoff exponencial
        
        return False
    
    async def send_batch_async(self, logs: List[LogEntry]) -> List[LogEntry]:
        """Envia lote de logs de forma assíncrona"""
        sent_logs = []
        tasks = []
        
        for log in logs[:self.config.batch_size]:
            task = self.send_log_async(log)
            tasks.append((task, log))
        
        results = await asyncio.gather(*[task for task, _ in tasks], return_exceptions=True)
        
        for (task, log), result in zip(tasks, results):
            if result is True:
                sent_logs.append(log)
        
        return sent_logs
    
    def send_batch_sync(self, logs: List[LogEntry]) -> List[LogEntry]:
        """Envia lote de logs de forma síncrona"""
        sent_logs = []
        
        for log in logs[:self.config.batch_size]:
            if self.send_log_sync(log):
                sent_logs.append(log)
        
        return sent_logs
    
    def close(self):
        """Fecha cliente HTTP"""
        if hasattr(self.client, 'close'):
            if asyncio.iscoroutinefunction(self.client.close):
                asyncio.create_task(self.client.close())
            else:
                self.client.close()


class LogSender:
    """Classe principal do Log Sender reestruturada"""
    
    def __init__(self, config: LogSenderConfig):
        self.config = config
        self.storage = LogStorage(config)
        self.transmitter = LogTransmitter(config)
        self._running = False
        self._thread = None
    
    def log(self, message: str, project: str = None, level: str = "INFO", tags: List[str] = None, data: Dict[str, Any] = None, request_id: str = None) -> bool:
        """Registra um log"""
        try:
            log_entry = LogEntry(
                message=message,
                project=project or self.config.project_id,
                level=level,
                tags=tags or [],
                data=data or {},
                request_id=request_id or str(uuid.uuid4())
            )
            
            return self.storage.store_log(log_entry)
        except Exception as e:
            return False
    
    def send_log(self, status: str, additional: str = '', level: LogLevel = LogLevel.INFO, metadata: Dict[str, Any] = None) -> bool:
        """Envia um log imediatamente (método legado)"""
        try:
            # Converter para nova estrutura LogEntry
            log_entry = LogEntry(
                message=status,
                project=self.config.project_id,
                level=level.value.upper(),
                tags=["legacy"],
                data={"additional": additional, "metadata": metadata or {}}
            )
            
            if self.config.enable_async:
                # Para uso síncrono de método assíncrono
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(self.transmitter.send_log_async(log_entry))
                finally:
                    loop.close()
            else:
                return self.transmitter.send_log_sync(log_entry)
        except Exception as e:
            return False
    
    def start_background_sender(self):
        """Inicia o envio em background"""
        if self._running:
            return
        
        self._running = True
        if self.config.enable_async:
            self._thread = threading.Thread(target=self._async_background_worker, daemon=True)
        else:
            self._thread = threading.Thread(target=self._sync_background_worker, daemon=True)
        
        self._thread.start()
    
    def stop_background_sender(self):
        """Para o envio em background"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
    
    def _async_background_worker(self):
        """Worker assíncrono em background"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(self._async_process_logs())
        finally:
            loop.close()
    
    async def _async_process_logs(self):
        """Processa logs de forma assíncrona"""
        while self._running:
            try:
                pending_logs = self.storage.read_pending_logs()
                if pending_logs:
                    sent_logs = await self.transmitter.send_batch_async(pending_logs)
                    
                    if sent_logs:
                        self.storage.backup_logs(sent_logs)
                        self.storage.clear_sent_logs(sent_logs)
                
                await asyncio.sleep(self.config.upload_delay)
            except Exception as e:
                await asyncio.sleep(self.config.upload_delay)
    
    def _sync_background_worker(self):
        """Worker síncrono em background"""
        while self._running:
            try:
                pending_logs = self.storage.read_pending_logs()
                if pending_logs:
                    sent_logs = self.transmitter.send_batch_sync(pending_logs)
                    
                    if sent_logs:
                        self.storage.backup_logs(sent_logs)
                        self.storage.clear_sent_logs(sent_logs)
                
                time.sleep(self.config.upload_delay)
            except Exception as e:
                time.sleep(10)  # Aguarda antes de tentar novamente
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do log sender"""
        pending_logs = self.storage.read_pending_logs()
        return {
            'pending_logs': len(pending_logs),
            'running': self._running,
            'config': {
                'project_id': self.config.project_id,
                'upload_delay': self.config.upload_delay,
                'batch_size': self.config.batch_size,
                'enable_async': self.config.enable_async
            }
        }
    
    def __enter__(self):
        """Context manager entry"""
        self.start_background_sender()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop_background_sender()
        self.transmitter.close()


# Funções utilitárias
def create_log_sender_from_env() -> LogSender:
    """
    Cria LogSender a partir de variáveis de ambiente
    
    Variáveis esperadas:
    - LOG_API: URL da API de logs
    - PROJECT_ID: ID do projeto
    - UPLOAD_DELAY: Delay de upload (opcional, padrão: 120)
    - LOG_DIR: Diretório de logs (opcional, padrão: "logs")
    """
    config = LogSenderConfig(
        log_api=os.getenv('LOG_API', ''),
        project_id=os.getenv('PROJECT_ID', ''),
        upload_delay=int(os.getenv('UPLOAD_DELAY', '120')),
        log_dir=os.getenv('LOG_DIR', 'logs')
    )
    
    if not config.log_api or not config.project_id:
        raise ConfigurationError("LOG_API e PROJECT_ID são obrigatórios")
    
    return LogSender(config)


# Instância global opcional
_log_sender_instance = None

def get_log_sender_instance() -> Optional[LogSender]:
    """Retorna instância global do LogSender"""
    return _log_sender_instance

def set_log_sender_instance(log_sender: LogSender):
    """Define instância global do LogSender"""
    global _log_sender_instance
    _log_sender_instance = log_sender