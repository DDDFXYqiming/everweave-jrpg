"""Rotating JSONL diagnostics. Never records credentials or full model prompts."""
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
import uuid

SENSITIVE={'api_key','authorization','password','secret','session_token','access_token','refresh_token','token'}
CREDENTIAL=re.compile(r'(?i)(?:Bearer\s+\S+|sk-[A-Za-z0-9_-]{12,}|github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9]+)')


class NullAudit:
    def emit(self,*args,**kwargs):pass
    def add_secret(self,*args):pass
    def close(self):pass


class JsonFormatter(logging.Formatter):
    def __init__(self,audit):super().__init__();self.audit=audit
    def format(self,record):
        data={'time':datetime.fromtimestamp(record.created,timezone.utc).isoformat(),
              'level':record.levelname,'run_id':self.audit.run_id,'pid':record.process,
              'thread':record.threadName,'event':record.getMessage(),
              'data':getattr(record,'details',{})}
        if record.exc_info:data['exception']=self.formatException(record.exc_info)
        return json.dumps(self.audit.redact(data),ensure_ascii=False,default=str)


class AuditLog:
    def __init__(self,directory,*,max_bytes=5*1024*1024,backups=3):
        directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
        self.run_id=uuid.uuid4().hex;self.secrets=();self.closed=False
        self.logger=logging.Logger('everweave.'+self.run_id,level=logging.INFO)
        self.logger.propagate=False
        self.handler=RotatingFileHandler(directory/'engine.jsonl',maxBytes=max_bytes,backupCount=backups,encoding='utf-8')
        self.handler.setFormatter(JsonFormatter(self));self.logger.addHandler(self.handler)
    def add_secret(self,value):
        if isinstance(value,str) and len(value)>=4 and value not in self.secrets:self.secrets+= (value,)
    def redact(self,value):
        if isinstance(value,dict):
            return {str(k):'[REDACTED]' if str(k).lower() in SENSITIVE else self.redact(v) for k,v in value.items()}
        if isinstance(value,(list,tuple)):return [self.redact(v) for v in value]
        if isinstance(value,str):
            for secret in self.secrets:value=value.replace(secret,'[REDACTED]')
            return CREDENTIAL.sub('[REDACTED]',value)
        return value
    def emit(self,event,*,level=logging.INFO,exception=None,**fields):
        if self.closed:return
        info=(type(exception),exception,exception.__traceback__) if exception is not None else None
        self.logger.log(level,event,extra={'details':fields},exc_info=info)
    def close(self):
        if self.closed:return
        self.closed=True;self.handler.close();self.logger.removeHandler(self.handler)
