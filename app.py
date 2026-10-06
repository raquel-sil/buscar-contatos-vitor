import hmac
import os
import smtplib
import time
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import Flask, Response, render_template_string, request, jsonify
import requests
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env (uso local). Em produção, vêm do painel da hospedagem.
load_dotenv()

HUBSPOT_ACCESS_TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN", "")
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")

JOEL_OWNER_ID = os.getenv("JOEL_OWNER_ID", "90392568")

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
JOEL_EMAIL_ADDRESS = os.getenv("JOEL_EMAIL_ADDRESS", "joel@startrh.io")
JOEL_EMAIL_PASSWORD = os.getenv("JOEL_EMAIL_PASSWORD", "")

# Login do painel (HTTP Basic Auth)
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

# TEMPLATE DE E-MAIL

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
        {"titulo": "(Estratégia Vitor) Segundo E-mail - Prova Social ou Dado de Mercado", "dias_prazo": 5, "tipo": "EMAIL", "status": "NOT_STARTED"},
        {"titulo": "(Estratégia Vitor) Linkedin - Comentário ou Mensagem", "dias_prazo": 8, "tipo": "TODO", "status": "NOT_STARTED"},
        {"titulo": "(Estratégia Vitor) Segunda Ligação - Ângulo Diferente", "dias_prazo": 11, "tipo": "CALL", "status": "NOT_STARTED"},
        {"titulo": "(Estratégia Vitor) WhatsApp - Só com Sinal Prévio", "dias_prazo": 15, "tipo": "TODO", "status": "NOT_STARTED"},
        {"titulo": "(Estratégia Vitor) Break Up E-mail", "dias_prazo": 19, "tipo": "EMAIL", "status": "NOT_STARTED"},
    ]
    agora_utc = datetime.now(timezone.utc)
    for t in tarefas:
        data_vencimento = adicionar_dias_uteis(agora_utc, t["dias_prazo"])
        vencimento_ms = int(data_vencimento.timestamp() * 1000)
        payload = {
            "properties": {
                "hs_task_subject": f"{t['titulo']} | {nome_lead} ({empresa_lead})",
                "hs_task_status": t.get("status", "NOT_STARTED"),
                "hs_task_type": t["tipo"],
                "hubspot_owner_id": str(bdr_id),
                "hs_timestamp": vencimento_ms,
            },
            "associations": [
                {
                    "to": {"id": str(contact_id)},
                    "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 204}],
                }
            ],
        }
        try:
            requests.post(url, headers=HEADERS_HUBSPOT, json=payload)
        except Exception:
            pass

def obter_ou_criar_empresa_hubspot(nome, dominio=""):
    if dominio:
        url_search = "https://api.hubapi.com/crm/v3/objects/companies/search"
        payload_search = {
            "filterGroups": [{"filters": [{"propertyName": "domain", "operator": "EQ", "value": dominio}]}]
        }
        res = requests.post(url_search, headers=HEADERS_HUBSPOT, json=payload_search)
        if res.status_code == 200 and res.json().get("results"):
            return res.json()["results"][0]["id"]

    url_create = "https://api.hubapi.com/crm/v3/objects/companies"
    payload_create = {
        "properties": {
            "name": nome,
            "domain": dominio,
            "description": "Adicionado via Painel do BDR.",
            "hubspot_owner_id": str(JOEL_OWNER_ID),
            "lifecyclestage": "lead",
        }
    }
    res_c = requests.post(url_create, headers=HEADERS_HUBSPOT, json=payload_create)
    if res_c.status_code == 201:
        return res_c.json().get("id")
    return None

def obter_ou_criar_contato_hubspot(email, nome="", sobrenome="", cargo="", linkedin=""):
    url_search = "https://api.hubapi.com/crm/v3/objects/contacts/search"
    payload_search = {
        "filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}]
    }
    res = requests.post(url_search, headers=HEADERS_HUBSPOT, json=payload_search)
    if res.status_code == 200 and res.json().get("results"):
        contact_id = res.json()["results"][0]["id"]
        if linkedin:
            url_update = f"https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}"
            payload_update = {"properties": {"hs_linkedin_url": str(linkedin)}}
            try:
                requests.patch(url_update, headers=HEADERS_HUBSPOT, json=payload_update)
            except Exception:
                pass
        return contact_id
    
    url_create = "https://api.hubapi.com/crm/v3/objects/contacts"
    payload_create = {
        "properties": {
            "email": str(email),
            "firstname": str(nome),
            "lastname": str(sobrenome),
            "jobtitle": str(cargo),
            "hs_linkedin_url": str(linkedin) if linkedin else "",
            "hubspot_owner_id": str(JOEL_OWNER_ID),
        }
    }
    res_c = requests.post(url_create, headers=HEADERS_HUBSPOT, json=payload_create)
    if res_c.status_code == 201:
        return res_c.json().get("id")
    return None

def associar_contato_empresa(contact_id, company_id):
    url = f"https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}/associations/companies/{company_id}/contact_to_company"
    requests.put(url, headers=HEADERS_HUBSPOT)

def registrar_email_enviado_no_hubspot(contact_id, assunto, corpo_html):
    url = "https://api.hubapi.com/crm/v3/objects/emails"
    timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    payload = {
        "properties": {
            "hs_email_subject": assunto,
            "hs_email_text": corpo_html,
            "hs_email_status": "SENT",
            "hs_timestamp": timestamp_ms,
            "hubspot_owner_id": str(JOEL_OWNER_ID),
        },
        "associations": [
            {
                "to": {"id": contact_id},
                "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 198}],
            }
        ],
    }
    requests.post(url, headers=HEADERS_HUBSPOT, json=payload)

def buscar_contatos_apollo(termo_empresa, limite=3):
    if not APOLLO_API_KEY:
        return [], "ERRO CRÍTICO: Chave de API do Apollo ausente no .env!", True

    url = "https://api.apollo.io/v1/mixed_people/api_search"
    termo_limpo = limpar_dominio(termo_empresa) if "." in termo_empresa else termo_empresa.strip()

    payload = {
        "api_key": APOLLO_API_KEY,
        "person_titles": [
            "RH", "HR", "Recrutamento", "Recruiter", "Talent Acquisition",
            "Recursos Humanos", "Gente e Gestão", "Gente e Gestao",
            "Head de RH", "Diretor de RH", "Gerente de RH", "HRBP",
            "VP of People", "Head of People", "Chief People Officer",
        ],
        "person_locations": ["Brazil"],
        "per_page": 100,
    }

    if "." in termo_limpo:
        payload["q_organization_domains"] = termo_limpo
    else:
        payload["q_keywords"] = termo_limpo

    contatos_validos = []
    try:
        res = requests.post(url, headers=HEADERS_APOLLO, json=payload)
        
        if res.status_code != 200:
            return [], f"Apollo rejeitou a busca (Erro {res.status_code}). Detalhe: {res.text}", True

        pessoas = res.json().get("people") or []

        for p in pessoas:
            email = p.get("email")
            linkedin = p.get("linkedin_url")
            
            if not email and p.get("id"):
                url_match = "https://api.apollo.io/v1/people/match"
                try:
                    p_match = requests.post(url_match, headers=HEADERS_APOLLO, json={"api_key": APOLLO_API_KEY, "id": p.get("id")})
                    if p_match.status_code == 200:
                        det = p_match.json().get("person") or {}
                        email = det.get("email")
                        linkedin = linkedin or det.get("linkedin_url")
                except Exception:
                    pass

            if email and "@" in email:
                contatos_validos.append({
                    "email": email,
                    "nome": p.get("first_name", ""),
                    "sobrenome": p.get("last_name", ""),
                    "cargo": p.get("title", ""),
                    "linkedin": linkedin or "",
                    "empresa_nome": p.get("organization", {}).get("name", termo_empresa),
                    "empresa_dominio": p.get("organization", {}).get("primary_domain", ""),
                })
            
            if len(contatos_validos) >= limite:
                break
                
        status_msg = f"Encontrei {len(contatos_validos)} pessoa(s) de {limite} requisitada(s)."
        return contatos_validos, status_msg, False
            
    except Exception as e:
        return [], f"Falha de conexão com Apollo: {str(e)}", True


app = Flask(__name__)


def _pedir_login():
    return Response(
        "Acesso restrito.", 401, {"WWW-Authenticate": 'Basic realm="Start RH - Painel BDR"'}
    )


@app.before_request
def exigir_login():
    if not APP_USER or not APP_PASSWORD:
        return Response("Servidor sem APP_USER/APP_PASSWORD configurados.", 503)
    auth = request.authorization
    if not auth:
        return _pedir_login()
    user_ok = hmac.compare_digest(auth.username or "", APP_USER)
    pass_ok = hmac.compare_digest(auth.password or "", APP_PASSWORD)
    if not (user_ok and pass_ok):
        return _pedir_login()


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Start RH - Prospecção do BDR</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen flex flex-col items-center p-6">
    <div class="max-w-4xl w-full bg-gray-800 rounded-xl shadow-2xl border border-gray-700 p-8 mt-6">
        
        <div class="flex items-center justify-between border-b border-gray-700 pb-6 mb-6">
            <div>
                <h1 class="text-2xl font-bold text-amber-500 flex items-center gap-2">
                    <i class="fa-solid fa-rocket"></i> Start RH - Enriquecimento Manual
                </h1>
                <p class="text-sm text-gray-400 mt-1">Dica de Ouro: Use os domínios (ex: apple.com, totvs.com.br) para resultados precisos!</p>
            </div>
            <div class="text-right">
                <span class="inline-block bg-amber-500/10 text-amber-400 text-xs px-3 py-1 rounded-full border border-amber-500/20 font-mono">
                    Owner: Joel Costa (90392568)
                </span>
            </div>
        </div>

        <div class="space-y-4">
            <div>
                <label class="block text-sm font-medium text-gray-300 mb-1">
                    Lista de Empresas ou Domínios (Separados por vírgula ou linha):
                </label>
                <textarea id="empresasInput" rows="5" 
                    class="w-full bg-gray-900 border border-gray-700 rounded-lg p-3 text-gray-100 focus:outline-none focus:border-amber-500 transition font-mono text-sm"
                    placeholder="Exemplo: apple.com, totvs.com.br, lg.com, lenovo.com"></textarea>
            </div>

            <div>
                <label class="block text-sm font-medium text-gray-300 mb-1">
                    Quantidade de contatos desejada por empresa:
                </label>
                <input type="number" id="limiteInput" value="3" min="1" max="1000"
                    class="w-32 bg-gray-900 border border-gray-700 rounded-lg p-2 text-gray-100 focus:outline-none focus:border-amber-500 transition font-mono text-sm">
            </div>

            <button id="btnProcessar" onclick="processarEmpresas()" 
                class="w-full bg-amber-500 hover:bg-amber-600 text-gray-950 font-bold py-3 px-6 rounded-lg transition flex items-center justify-center gap-2 shadow-lg shadow-amber-500/20">
                <i class="fa-solid fa-bolt"></i> Iniciar Prospecção
            </button>
        </div>

        <div id="loading" class="hidden my-8 text-center">
            <div class="inline-block animate-spin rounded-full h-10 w-10 border-4 border-amber-500 border-t-transparent"></div>
            <p class="text-gray-400 text-sm mt-3 animate-pulse">Consultando Apollo, criando no HubSpot e enviando e-mails...</p>
        </div>

        <div id="resultadoContainer" class="hidden mt-8 border-t border-gray-700 pt-6">
            <h2 class="text-lg font-semibold text-gray-200 mb-4 flex items-center gap-2">
                <i class="fa-solid fa-list-check text-amber-500"></i> Relatório da Execução:
            </h2>
            <div id="logList" class="space-y-4 font-mono text-xs"></div>
        </div>
    </div>

    <script>
        async function processarEmpresas() {
            const input = document.getElementById('empresasInput').value.trim();
            const limite = parseInt(document.getElementById('limiteInput').value) || 3;
            
            if (!input) return alert('Por favor, digite ao menos uma empresa.');

            const btn = document.getElementById('btnProcessar');
            const loading = document.getElementById('loading');
            const resultadoContainer = document.getElementById('resultadoContainer');
            const logList = document.getElementById('logList');

            btn.disabled = true;
            btn.classList.add('opacity-50', 'cursor-not-allowed');
            loading.classList.remove('hidden');
            resultadoContainer.classList.add('hidden');
            logList.innerHTML = '';

            try {
                const response = await fetch('/api/enriquecer', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ empresas: input, limite: limite })
                });

                if (!response.ok) {
                    const errorText = await response.text();
                    throw new Error(`Erro ${response.status} no servidor: ${errorText.substring(0, 150)}`);
                }
                
                const data = await response.json();
                
                loading.classList.add('hidden');
                resultadoContainer.classList.remove('hidden');

                if (data.status === 'success') {
                    data.resultados.forEach(item => {
                        let htmlItem = `<div class="bg-gray-900 border border-gray-700 rounded-lg p-4">`;
                        htmlItem += `<div class="text-sm font-bold text-amber-400 border-b border-gray-800 pb-2 mb-2 flex justify-between items-center">
                            <span><i class="fa-regular fa-building"></i> ${item.empresa_input}</span>
                            <span class="text-gray-400 text-xs">${item.hubspot_id ? 'HubSpot ID: ' + item.hubspot_id : 'Sem cadastro no HubSpot'}</span>
                        </div>`;

                        if (item.status_msg) {
                            const badgeClass = item.is_erro ? 'text-rose-400 bg-rose-500/10 border-rose-500/20' : 'text-amber-300 bg-amber-500/10 border-amber-500/20';
                            htmlItem += `<p class="text-xs p-2 rounded border mb-2 ${badgeClass}"><i class="fa-solid fa-circle-info"></i> ${item.status_msg}</p>`;
                        }

                        if (item.contatos && item.contatos.length > 0) {
                            htmlItem += `<ul class="space-y-2 mt-2">`;
                            item.contatos.forEach(c => {
                                htmlItem += `<li class="flex items-center justify-between text-gray-300 bg-gray-800/50 p-2 rounded">
                                    <div>
                                        <strong class="text-gray-100">${c.nome} ${c.sobrenome}</strong> (${c.cargo}) - <span class="text-gray-400">${c.email}</span>
                                        ${c.linkedin ? '<br><a href="' + c.linkedin + '" target="_blank" class="text-amber-500 underline mt-1 inline-block">LinkedIn</a>' : ''}
                                    </div>
                                    <div class="text-right">
                                        ${c.email_enviado 
                                            ? '<span class="text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded"><i class="fa-solid fa-check"></i> E-mail & Tarefas OK</span>' 
                                            : '<span class="text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded"><i class="fa-solid fa-xmark"></i> Contato OK (Erro E-mail)</span>'}
                                    </div>
                                </li>`;
                            });
                            htmlItem += `</ul>`;
                        }
                        htmlItem += `</div>`;
                        logList.innerHTML += htmlItem;
                    });
                } else {
                    logList.innerHTML = `<p class="text-rose-500 p-3 bg-rose-500/10 rounded border border-rose-500/20"><i class="fa-solid fa-bomb"></i> Erro no servidor: ${data.message}</p>`;
                }
            } catch (err) {
                loading.classList.add('hidden');
                resultadoContainer.classList.remove('hidden');
                logList.innerHTML = `<p class="text-rose-500 p-3 bg-rose-500/10 rounded border border-rose-500/20"><i class="fa-solid fa-triangle-exclamation"></i> ${err.message}</p>`;
            } finally {
                btn.disabled = false;
                btn.classList.remove('opacity-50', 'cursor-not-allowed');
            }
        }
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/enriquecer", methods=["POST"])
def api_enriquecer():
    try:
        data = request.json or {}
        empresas_raw = data.get("empresas", "")
        
        try:
            limite = max(1, int(data.get("limite", 3)))
        except (TypeError, ValueError):
            limite = 3

        lista_empresas = [e.strip() for e in empresas_raw.replace("\n", ",").split(",") if e.strip()]

        resultados = []

        for item in lista_empresas:
            contatos, status_msg, is_erro_critico = buscar_contatos_apollo(item, limite=limite)
            
            if is_erro_critico or not contatos:
                resultados.append({
                    "empresa_input": item,
                    "hubspot_id": None,
                    "status_msg": status_msg,
                    "is_erro": is_erro_critico,
                    "contatos": []
                })
                continue

            nome_empresa = contatos[0]["empresa_nome"] or item
            dominio_empresa = limpar_dominio(contatos[0]["empresa_dominio"] or (item if "." in item else ""))

            company_id = obter_ou_criar_empresa_hubspot(nome_empresa, dominio_empresa)
            contatos_resultado = []

            for c in contatos:
                nome_contato = c["nome"] or "Olá"
                contact_id = obter_ou_criar_contato_hubspot(
                    email=c["email"],
                    nome=c["nome"],
                    sobrenome=c["sobrenome"],
                    cargo=c["cargo"],
                    linkedin=c["linkedin"],
                )

                enviou = False
                if contact_id:
                    if company_id:
                        associar_contato_empresa(contact_id, company_id)
                    
                    enviou, msg_status = disparar_email_joel(c["email"], nome_contato, nome_empresa)
                    
                    if enviou:
                        registrar_email_enviado_no_hubspot(contact_id, EMAIL_ASSUNTO.format(nome=nome_contato, empresa=nome_empresa), EMAIL_CORPO_HTML.format(nome=nome_contato, empresa=nome_empresa))

                    criar_cadencia_tarefas_hubspot(
                        contact_id=contact_id,
                        bdr_id=JOEL_OWNER_ID,
                        bdr_name="Joel",
                        nome_lead=nome_contato,
                        empresa_lead=nome_empresa,
                    )

                contatos_resultado.append({
                    "nome": c["nome"],
                    "sobrenome": c["sobrenome"],
                    "cargo": c["cargo"],
                    "email": c["email"],
                    "linkedin": c["linkedin"],
                    "email_enviado": enviou
                })

            resultados.append({
                "empresa_input": nome_empresa,
                "hubspot_id": company_id,
                "status_msg": status_msg,
                "is_erro": False,
                "contatos": contatos_resultado
            })

        return jsonify({"status": "success", "resultados": resultados})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erro de execução no backend: {str(e)}"}), 500

if __name__ == "__main__":
    porta = int(os.getenv("PORT", "5000"))
    print("\n--- SERVIDOR LOCAL DA START RH INICIADO ---")
    print(f"Acesse no navegador: http://localhost:{porta}\n")
    app.run(host="127.0.0.1", port=porta, debug=False)
