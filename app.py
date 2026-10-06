import hmac
import os
import smtplib
import time
import traceback
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import Flask, Response, render_template_string, request, jsonify
import requests
from dotenv import load_dotenv

# Carrega as variáveis do .env (local) ou do painel da nuvem
load_dotenv()

HUBSPOT_ACCESS_TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN", "")
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")

JOEL_OWNER_ID = os.getenv("JOEL_OWNER_ID", "90392568")

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
JOEL_EMAIL_ADDRESS = os.getenv("JOEL_EMAIL_ADDRESS", "joel@startrh.io")
JOEL_EMAIL_PASSWORD = os.getenv("JOEL_EMAIL_PASSWORD", "")

APP_USER = os.getenv("APP_USER", "")
APP_PASSWORD = os.getenv("APP_PASSWORD", "")

HEADERS_HUBSPOT = {
    "Authorization": f"Bearer {HUBSPOT_ACCESS_TOKEN}",
    "Content-Type": "application/json",
}

HEADERS_APOLLO = {
    "Cache-Control": "no-cache",
    "Content-Type": "application/json",
    "x-api-key": APOLLO_API_KEY,
}

# ==========================================
# TEMPLATE DE E-MAIL (HTML)
# ==========================================
EMAIL_ASSUNTO = "{empresa} + START RH - Parceria Estratégica em Recrutamento e Seleção"
EMAIL_CORPO_HTML = """
<p>Olá {nome}, tudo bem?</p>

<p>Me chamo Joel e faço parte da <strong>Start RH</strong>, consultoria de Recrutamento e Seleção que apoia empresas a contratar com mais velocidade e assertividade.</p>

<p>Atuamos em vagas pontuais, executivas e técnicas, e também em projetos de alta demanda. Só na <strong>Cielo</strong>, fechamos mais de <strong>1.200 posições</strong>. Também somos parceiros de marcas como <strong>Porto Seguro, Mapfre e Natura</strong>.</p>

<p>E temos um diferencial: oferecemos <strong>garantia de assertividade</strong> nas contratações. Se a escolha não der certo, fazemos a reposição sem custo.</p>

<p>Podemos ter uma conversa rápida de 15 minutos para eu te apresentar nosso projeto?</p>

<p>Me diga qual o melhor dia e horário para você ou, se preferir, <a href="https://meetings.hubspot.com/joel-oliveira?uuid=3dae6946-5a35-483c-a5ce-f14e4c42ae76" style="color: #F5A623; font-weight: bold; text-decoration: underline;">escolha direto aqui na minha agenda</a>.</p>

<p>Abraço,</p>

<table cellpadding="0" cellspacing="0" border="0" style="font-family: Arial, sans-serif; font-size: 13px; color: #333333; margin-top: 16px;">
  <tbody>
    <tr>
      <td style="padding-right: 16px; border-right: 2px solid #e0e0e0; vertical-align: middle; text-align: center;">
        <a href="https://startrh.io" target="_blank">
          <img src="https://startrh.io/wp-content/uploads/2025/04/startrh-logo.png" alt="Start RH" width="100" style="display: block; margin: 0 auto;">
        </a>
      </td>
      <td style="padding-left: 16px; vertical-align: middle;">
        <p style="margin: 0; font-weight: bold; font-size: 14px; color: #1a1a1a;">Joel Costa</p>
        <p style="margin: 2px 0 6px 0; font-weight: bold; color: #555555;">Comercial, Start RH</p>
        <p style="margin: 0 0 4px 0; color: #333333;">
          11 92552-5691 &nbsp;|&nbsp;
          <a href="https://startrh.io" target="_blank" style="color: #F5A623; text-decoration: none;">startrh.io</a>
          &nbsp;|&nbsp;
          <a href="mailto:joel@startrh.io" style="color: #F5A623; text-decoration: none;">joel@startrh.io</a>
        </p>
      </td>
    </tr>
  </tbody>
</table>
"""

# ==========================================
# FUNÇÕES DE AUXÍLIO E INTEGRAÇÕES
# ==========================================
def limpar_dominio(url: str) -> str:
    if not url:
        return ""
    d = url.lower().strip()
    d = d.replace("https://", "").replace("http://", "").replace("www.", "")
    return d.split("/")[0]

def adicionar_dias_uteis(data_inicial, dias_uteis_prazo):
    data_atual = data_inicial
    dias_adicionados = 0
    while dias_adicionados < dias_uteis_prazo:
        data_atual += timedelta(days=1)
        if data_atual.weekday() < 5:
            dias_adicionados += 1
    return data_atual

def disparar_email_joel(email_destino, nome_contato, nome_empresa):
    if not JOEL_EMAIL_PASSWORD:
        return False, "E-mail não configurado"
    try:
        time.sleep(1.2)  # Pausa estratégica contra bloqueio SMTP
        
        assunto = EMAIL_ASSUNTO.format(nome=nome_contato, empresa=nome_empresa)
        corpo = EMAIL_CORPO_HTML.format(nome=nome_contato, empresa=nome_empresa)
        msg = MIMEMultipart()
        msg["From"] = f"Joel <{JOEL_EMAIL_ADDRESS}>"
        msg["To"] = email_destino
        msg["Subject"] = assunto
        msg.attach(MIMEText(corpo, "html"))
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(JOEL_EMAIL_ADDRESS, JOEL_EMAIL_PASSWORD)
            server.send_message(msg)
        return True, "Enviado com sucesso"
    except Exception as e:
        return False, str(e)

def criar_cadencia_tarefas_hubspot(contact_id, bdr_id, bdr_name, nome_lead, empresa_lead):
    url = "https://api.hubapi.com/crm/v3/objects/tasks"
    tarefas = [
        {"titulo": "(Estratégia Vitor) Conexão - LinkedIn", "dias_prazo": 1, "tipo": "TODO", "status": "NOT_STARTED"},
        {"titulo": "(Estratégia Vitor) Primeiro E-mail (Problema)", "dias_prazo": 1, "tipo": "EMAIL", "status": "COMPLETED"},
        {"titulo": "(Estratégia Vitor) Primeira Ligação - Referencia o E-mail", "dias_prazo": 3, "tipo": "CALL", "status": "NOT_STARTED"},
        {"titulo": "(Estratégia Vitor) Segundo E-mail - Prova Social ou Dado de Mercado", "dias_prazo": 5, "tipo": "EMAIL
