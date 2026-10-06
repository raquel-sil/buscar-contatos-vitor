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

load_dotenv()

# ==========================================
# CONFIGURAÇÕES E CHAVES
# ==========================================
HUBSPOT_ACCESS_TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN", "COLE_SUA_CHAVE_DO_HUBSPOT_AQUI")
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "COLE_SUA_CHAVE_DO_APOLLO_AQUI")

JOEL_OWNER_ID = os.getenv("JOEL_OWNER_ID", "90392568")

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
JOEL_EMAIL_ADDRESS = os.getenv("JOEL_EMAIL_ADDRESS", "joel@startrh.io")
JOEL_EMAIL_PASSWORD = os.getenv("JOEL_EMAIL_PASSWORD", "COLE_SUA_SENHA_DE_APP_AQUI")

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
# TEMPLATE DE E-MAIL (COM ASSINATURA)
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
# FUNÇÕES DE LÓGICA E APIS
# ==========================================
def limpar_dominio(url: str) -> str:
    if not url: return ""
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
    print(f"   [E-mail] Conectando ao Gmail para enviar a {email_destino}...")
    if not JOEL_EMAIL_PASSWORD or JOEL_EMAIL_PASSWORD == "COLE_SUA_SENHA_DE_APP_AQUI":
        print("   [E-mail ERRO] Senha do Gmail não configurada!")
        return False, "Senha do Gmail não configurada"
    try:
        assunto = EMAIL_ASSUNTO.format(nome=nome_contato, empresa=nome_empresa)
        corpo = EMAIL_CORPO_HTML.format(nome=nome_contato, empresa=nome_empresa)
        msg = MIMEMultipart()
        msg["From"] = f"Joel <{JOEL_EMAIL_ADDRESS}>"
        msg["To"] = email_destino
        msg["Subject"] = assunto
        msg.attach(MIMEText(corpo, "html"))
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(JOEL_EMAIL_ADDRESS, JOEL_EMAIL_PASSWORD)
            server.send_message(msg)
        print("   [E-mail SUCESSO]")
        return True, "Enviado com sucesso"
    except Exception as e:
        print(f"   [E-mail ERRO] {e}")
        return False, str(e)

def criar_cadencia_tarefas_hubspot(contact_id, bdr_id, nome_lead, empresa_lead):
    print("   [HubSpot] Criando 8 tarefas da cadência...")
    url = "https://api.hubapi.com/crm/v3/objects/tasks"
    tarefas = [
        {"titulo": "(Estratégia Vitor) Conexão - LinkedIn", "dias_prazo": 1, "tipo": "TODO"},
        {"titulo": "(Estratégia Vitor) Primeiro E-mail (Problema)", "dias_prazo": 1, "tipo": "EMAIL", "status": "COMPLETED"},
        {"titulo": "(Estratégia Vitor) Primeira Ligação - Referencia o E-mail", "dias_prazo": 3, "tipo": "CALL"},
        {"titulo": "(Estratégia Vitor) Segundo E-mail - Prova Social", "dias_prazo": 5, "tipo": "EMAIL"},
        {"titulo": "(Estratégia Vitor) Linkedin - Comentário", "dias_prazo": 8, "tipo": "TODO"},
        {"titulo": "(Estratégia Vitor) Segunda Ligação", "dias_prazo": 11, "tipo": "CALL"},
        {"titulo": "(Estratégia Vitor) WhatsApp", "dias_prazo": 15, "tipo": "TODO"},
        {"titulo": "(Estratégia Vitor) Break Up E-mail", "dias_prazo": 19, "tipo": "EMAIL"},
    ]
    agora_utc = datetime.now(timezone.utc)
    for t in tarefas:
        vencimento_ms = int(adicionar_dias_uteis(agora_utc, t["dias_prazo"]).timestamp() * 1000)
        payload = {
            "properties": {
                "hs_task_subject": f"{t['titulo']} | {nome_lead}",
                "hs_task_status": t.get("status", "NOT_STARTED"),
                "hs_task_type": t["tipo"],
                "hubspot_owner_id": str(bdr_id),
                "hs_timestamp": vencimento_ms,
            },
            "associations": [{"to": {"id": str(contact_id)}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 204}]}],
        }
        try:
            requests.post(url, headers=HEADERS_HUBSPOT, json=payload, timeout=5)
        except: pass

def obter_ou_criar_empresa_hubspot(nome, dominio=""):
    print(f"   [HubSpot] Buscando/Criando empresa '{nome}'...")
    url_create = "https://api.hubapi.com/crm/v3/objects/companies"
    payload_create = {
        "properties": {"name": nome, "domain": dominio, "hubspot_owner_id": str(JOEL_OWNER_ID), "lifecyclestage": "lead"}
    }
    try:
        res_c = requests.post(url_create, headers=HEADERS_HUBSPOT, json=payload_create, timeout=10)
        if res_c.status_code in [200, 201]:
            return res_c.json().get("id")
    except Exception as e:
        print(f"   [HubSpot ERRO REDE]: {e}")
    return None

def obter_ou_criar_contato_hubspot(email, nome="", sobrenome="", cargo="", linkedin=""):
    print(f"   [HubSpot] Buscando/Criando contato '{email}'...")
    url_create = "https://api.hubapi.com/crm/v3/objects/contacts"
    payload_create = {
        "properties": {
            "email": str(email), "firstname": str(nome), "lastname": str(sobrenome),
            "jobtitle": str(cargo), "hs_linkedin_url": str(linkedin) if linkedin else "",
            "hubspot_owner_id": str(JOEL_OWNER_ID),
        }
    }
    try:
        res_c = requests.post(url_create, headers=HEADERS_HUBSPOT, json=payload_create, timeout=10)
        if res_c.status_code in [200, 201]:
            return res_c.json().get("id")
        elif res_c.status_code == 409:
            return res_c.json().get("message", "").split("Id: ")[-1]
    except: pass
    return None

def associar_contato_empresa(contact_id, company_id):
    url = f"https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}/associations/companies/{company_id}/contact_to_company"
    try: requests.put(url, headers=HEADERS_HUBSPOT, timeout=5)
    except: pass

def buscar_contatos_apollo(termo_empresa, limite=3):
    print(f"\n🚀 [Apollo] Buscando decisores em: '{termo_empresa}' (Limite: {limite})")
    if not APOLLO_API_KEY or APOLLO_API_KEY == "COLE_SUA_CHAVE_DO_APOLLO_AQUI":
        return [], "ERRO CRÍTICO: Chave de API do Apollo ausente!", True

    url = "https://api.apollo.io/v1/mixed_people/api_search"
    termo_limpo = limpar_dominio(str(termo_empresa)) if "." in str(termo_empresa) else str(termo_empresa).strip()

    payload = {
        "api_key": APOLLO_API_KEY,
        "person_titles": ["RH", "HR", "Recrutamento", "Recruiter", "Talent Acquisition", "Gente"],
        "person_locations": ["Brazil"],
        "per_page": 20,
    }
    if "." in termo_limpo: payload["q_organization_domains"] = termo_limpo
    else: payload["q_keywords"] = termo_limpo

    contatos_validos = []
    try:
        res = requests.post(url, headers=HEADERS_APOLLO, json=payload, timeout=10)
        if res.status_code != 200:
            print(f"❌ [Apollo ERRO]: {res.status_code} - {res.text}")
            return [], f"Apollo rejeitou a busca (Erro {res.status_code}).", True

        pessoas = res.json().get("people") or []
        for p in pessoas:
            email = p.get("email")
            if not email and p.get("id"):
                try:
                    p_match = requests.post("https://api.apollo.io/v1/people/match", headers=HEADERS_APOLLO, json={"api_key": APOLLO_API_KEY, "id": p.get("id")}, timeout=5)
                    if p_match.status_code == 200: email = (p_match.json().get("person") or {}).get("email")
                except: pass

            if email and "@" in email:
                org_obj = p.get("organization") or {}
                
                contatos_validos.append({
                    "email": email, "nome": p.get("first_name", ""), "sobrenome": p.get("last_name", ""),
                    "cargo": p.get("title", ""), "linkedin": p.get("linkedin_url", ""),
                    "empresa_nome": org_obj.get("name") or str(termo_empresa),
                    "empresa_dominio": org_obj.get("primary_domain") or "",
                })
            
            if len(contatos_validos) >= limite: break
                
        return contatos_validos, f"Encontrei {len(contatos_validos)} pessoa(s).", False
    except Exception as e:
        print(f"❌ [Apollo ERRO REDE]: {e}")
        return [], str(e), True

# ==========================================
# SERVIDOR FLASK E FRONTEND
# ==========================================
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Start RH - Prospecção do BDR</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen flex flex-col items-center p-6">
    <div class="max-w-4xl w-full bg-gray-800 rounded-xl shadow-2xl p-8 mt-6">
        <h1 class="text-2xl font-bold text-amber-500 mb-4 flex items-center gap-2">
            <i class="fa-solid fa-rocket"></i> Start RH - Enriquecimento Manual
        </h1>
        <div class="space-y-4">
            <div>
                <label class="block text-sm font-medium text-gray-300 mb-1">
                    Lista de Empresas ou Domínios (Separados por vírgula ou linha):
                </label>
                <textarea id="empresasInput" rows="3" class="w-full bg-gray-900 border border-gray-700 rounded-lg p-3 text-gray-100" placeholder="Ex: totvs.com.br, nubank.com.br"></textarea>
            </div>
            <div>
                <label class="block text-sm font-medium text-gray-300 mb-1">Contatos por empresa:</label>
                <input type="number" id="limiteInput" value="1" min="1" max="10" class="w-24 bg-gray-900 border border-gray-700 rounded-lg p-2 text-gray-100">
            </div>
            <button id="btnProcessar" onclick="processar()" class="w-full bg-amber-500 hover:bg-amber-600 text-gray-950 font-bold py-3 rounded-lg mt-4 transition">
                <i class="fa-solid fa-bolt"></i> Iniciar Prospecção
            </button>
        </div>
        <div id="loading" class="hidden mt-6 text-center text-amber-400 animate-pulse font-bold">
            <i class="fa-solid fa-spinner fa-spin text-2xl mb-2"></i><br>
            Processando empresas... VEJA O TERMINAL DO VS CODE PARA ACOMPANHAR!
        </div>
        <div id="logList" class="mt-6 space-y-4 font-mono text-sm"></div>
    </div>
    <script>
        async function processar() {
            const btn = document.getElementById('btnProcessar');
            btn.disabled = true; btn.classList.add('opacity-50');
            document.getElementById('loading').classList.remove('hidden');
            document.getElementById('logList').innerHTML = '';
            
            try {
                const res = await fetch('/api/enriquecer', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ empresas: document.getElementById('empresasInput').value, limite: document.getElementById('limiteInput').value })
                });
                
                const data = await res.json();
                document.getElementById('loading').classList.add('hidden');
                btn.disabled = false; btn.classList.remove('opacity-50');
                
                if (data.status === 'success') {
                    data.resultados.forEach(item => {
                        let htmlItem = `<div class="bg-gray-900 border border-gray-700 rounded-lg p-4">`;
                        htmlItem += `<div class="font-bold text-amber-400 border-b border-gray-800 pb-2 mb-2 flex justify-between">
                            <span><i class="fa-regular fa-building"></i> ${item.empresa_input}</span>
                            <span class="text-gray-400 text-xs">${item.hubspot_id ? 'ID: ' + item.hubspot_id : 'Sem CRM'}</span>
                        </div>`;

                        const badgeClass = item.is_erro ? 'text-rose-400 bg-rose-500/10' : 'text-emerald-400 bg-emerald-500/10';
                        htmlItem += `<p class="text-xs p-2 rounded mb-2 ${badgeClass}">${item.status_msg}</p>`;

                        if (item.contatos && item.contatos.length > 0) {
                            htmlItem += `<ul class="space-y-2">`;
                            item.contatos.forEach(c => {
                                htmlItem += `<li class="flex items-center justify-between text-gray-300 bg-gray-800/50 p-2 rounded border border-gray-700">
                                    <div>
                                        <strong class="text-gray-100">${c.nome} ${c.sobrenome}</strong> (${c.cargo}) <br> <span class="text-gray-400">${c.email}</span>
                                        ${c.linkedin ? `<br><a href="${c.linkedin}" target="_blank" class="text-sky-400 hover:text-sky-300 mt-1 inline-block"><i class="fa-brands fa-linkedin"></i> LinkedIn</a>` : ''}
                                    </div>
                                    <div class="text-right">
                                        ${c.email_enviado 
                                            ? '<span class="text-emerald-400 bg-emerald-500/10 px-2 py-1 rounded"><i class="fa-solid fa-check"></i> Enviado</span>' 
                                            : '<span class="text-rose-400 bg-rose-500/10 px-2 py-1 rounded"><i class="fa-solid fa-xmark"></i> Erro Email</span>'}
                                    </div>
                                </li>`;
                            });
                            htmlItem += `</ul>`;
                        }
                        htmlItem += `</div>`;
                        document.getElementById('logList').innerHTML += htmlItem;
                    });
                } else { 
                    document.getElementById('logList').innerHTML = `<div class='p-4 bg-rose-900/50 text-rose-300 font-bold border border-rose-500 rounded'>❌ O CÓDIGO QUEBROU:<br><br>${data.message}</div>`;
                }
            } catch(e) {
                document.getElementById('loading').classList.add('hidden');
                btn.disabled = false; btn.classList.remove('opacity-50');
                document.getElementById('logList').innerHTML = `<div class='text-rose-500 p-4 border border-rose-500 rounded'>Erro grave de conexão do navegador com o Python: ${e}</div>`;
            }
        }
    </script>
</body>
</html>
"""

@app.route("/")
def index(): return render_template_string(HTML_TEMPLATE)

@app.route("/api/enriquecer", methods=["POST"])
def api_enriquecer():
    try:
        data = request.json or {}
        empresas_str = str(data.get("empresas", ""))
        empresas = [e.strip() for e in empresas_str.replace("\n", ",").split(",") if e.strip()]
        
        try: limite = int(data.get("limite") or 1)
        except: limite = 1

        resultados = []

        for item in empresas:
            contatos, status_msg, erro = buscar_contatos_apollo(item, limite)
            if erro or not contatos:
                resultados.append({"empresa_input": item, "status_msg": status_msg, "is_erro": erro, "contatos": []})
                continue

            nome_empresa = contatos[0]["empresa_nome"]
            dominio_empresa = limpar_dominio(contatos[0]["empresa_dominio"] or item)
            company_id = obter_ou_criar_empresa_hubspot(nome_empresa, dominio_empresa)
            
            contatos_resultado = []

            for c in contatos:
                contact_id = obter_ou_criar_contato_hubspot(c["email"], c["nome"], c["sobrenome"], c["cargo"], c["linkedin"])
                enviou = False
                
                if contact_id:
                    if company_id: associar_contato_empresa(contact_id, company_id)
                    enviou, _ = disparar_email_joel(c["email"], c["nome"], nome_empresa)
                    criar_cadencia_tarefas_hubspot(contact_id, JOEL_OWNER_ID, c["nome"], nome_empresa)

                contatos_resultado.append({
                    "nome": c["nome"], "sobrenome": c["sobrenome"], "cargo": c["cargo"], 
                    "email": c["email"], "linkedin": c["linkedin"], "email_enviado": enviou
                })

            resultados.append({
                "empresa_input": nome_empresa, 
                "hubspot_id": company_id,
                "status_msg": status_msg + " Cadastrado no CRM com sucesso.", 
                "is_erro": False,
                "contatos": contatos_resultado
            })
            
        return jsonify({"status": "success", "resultados": resultados})
        
    except Exception as e:
        erro_completo = traceback.format_exc()
        print(f"\n❌ ERRO DETECTADO:\n{erro_completo}\n")
        return jsonify({"status": "error", "message": str(e) + " | Olhe o terminal do VS Code para ver a linha exata!"})

if __name__ == "__main__":
    print("\n--- SERVIDOR LOCAL DA START RH INICIADO ---")
    app.run(host="127.0.0.1", port=5000, debug=True)
