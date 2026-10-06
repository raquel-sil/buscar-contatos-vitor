import hmac
import os
import time
import traceback
from datetime import datetime, timedelta, timezone
from flask import Flask, Response, render_template_string, request, jsonify
import requests
from dotenv import load_dotenv

# Carrega as variáveis do .env (local) ou do painel da nuvem
load_dotenv()

HUBSPOT_ACCESS_TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN", "")
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")

JOEL_OWNER_ID = os.getenv("JOEL_OWNER_ID", "90392568")

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

def criar_cadencia_tarefas_hubspot(contact_id, bdr_id, bdr_name, nome_lead, empresa_lead):
    url = "https://api.hubapi.com/crm/v3/objects/tasks"
    tarefas = [
        {"titulo": "(Estratégia Vitor) Conexão - LinkedIn", "dias_prazo": 1, "tipo": "TODO", "status": "NOT_STARTED"},
        # A TAREFA ABAIXO AGORA FICA COMO "NOT_STARTED" (NÃO MARCADA)
        {"titulo": "(Estratégia Vitor) Primeiro E-mail (Problema)", "dias_prazo": 1, "tipo": "EMAIL", "status": "NOT_STARTED"},
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
            requests.post(url, headers=HEADERS_HUBSPOT, json=payload, timeout=10)
            time.sleep(0.2)  # Previne estouro de rate limit no HubSpot
        except Exception:
            pass

def obter_ou_criar_empresa_hubspot(nome, dominio=""):
    if dominio:
        url_search = "https://api.hubapi.com/crm/v3/objects/companies/search"
        payload_search = {
            "filterGroups": [{"filters": [{"propertyName": "domain", "operator": "EQ", "value": dominio}]}]
        }
        try:
            res = requests.post(url_search, headers=HEADERS_HUBSPOT, json=payload_search, timeout=10)
            if res.status_code == 200 and res.json().get("results"):
                return res.json()["results"][0]["id"]
        except Exception:
            pass

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
    try:
        res_c = requests.post(url_create, headers=HEADERS_HUBSPOT, json=payload_create, timeout=10)
        if res_c.status_code == 201:
            return res_c.json().get("id")
    except Exception:
        pass
    return None

def obter_ou_criar_contato_hubspot(email, nome="", sobrenome="", cargo="", linkedin=""):
    url_search = "https://api.hubapi.com/crm/v3/objects/contacts/search"
    payload_search = {
        "filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}]
    }
    try:
        res = requests.post(url_search, headers=HEADERS_HUBSPOT, json=payload_search, timeout=10)
        if res.status_code == 200 and res.json().get("results"):
            contact_id = res.json()["results"][0]["id"]
            if linkedin:
                url_update = f"https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}"
                payload_update = {"properties": {"hs_linkedin_url": str(linkedin)}}
                try:
                    requests.patch(url_update, headers=HEADERS_HUBSPOT, json=payload_update, timeout=5)
                except Exception:
                    pass
            return contact_id
    except Exception:
        pass

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
    try:
        res_c = requests.post(url_create, headers=HEADERS_HUBSPOT, json=payload_create, timeout=10)
        if res_c.status_code == 201:
            return res_c.json().get("id")
        elif res_c.status_code == 409:
            return res_c.json().get("message", "").split("Id: ")[-1]
    except Exception:
        pass
    return None

def associar_contato_empresa(contact_id, company_id):
    url = f"https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}/associations/companies/{company_id}/contact_to_company"
    try:
        requests.put(url, headers=HEADERS_HUBSPOT, timeout=10)
    except Exception:
        pass

def buscar_contatos_apollo(termo_empresa, limite=3):
    if not APOLLO_API_KEY:
        return [], "ERRO CRÍTICO: Chave de API do Apollo ausente!", True

    url = "https://api.apollo.io/v1/mixed_people/api_search"
    termo_limpo = limpar_dominio(str(termo_empresa)) if "." in str(termo_empresa) else str(termo_empresa).strip()

    # Raízes universais de Recrutamento/RH para ampla abrangência
    palavras_raiz = [
        "rh", "hr", "recruiter", "recrutador", "recrutadora", "recrutamento", 
        "talent", "people", "gente", "sourcing", "sourcer", "headhunter", "dho"
    ]

    payload = {
        "api_key": APOLLO_API_KEY,
        "person_titles": palavras_raiz,
        "per_page": 50,
    }

    # TENTA BUSCA POR DOMÍNIO PRIMEIRO
    if "." in termo_limpo:
        payload["q_organization_domains"] = termo_limpo
    else:
        payload["q_keywords"] = termo_limpo

    contatos_validos = []
    
    try:
        res = requests.post(url, headers=HEADERS_APOLLO, json=payload, timeout=12)
        
        if res.status_code != 200:
            return [], f"Apollo rejeitou a busca (Erro {res.status_code}). Detalhe: {res.text}", True

        pessoas = res.json().get("people") or []
        
        # PLANO B: Se não achou pelo domínio, busca pelo nome e ignora o ponto
        if not pessoas and "." in termo_limpo:
            nome_sem_ponto = termo_limpo.split('.')[0]
            payload_fallback = {
                "api_key": APOLLO_API_KEY,
                "person_titles": palavras_raiz,
                "q_keywords": nome_sem_ponto,
                "per_page": 50,
            }
            res_fallback = requests.post(url, headers=HEADERS_APOLLO, json=payload_fallback, timeout=12)
            if res_fallback.status_code == 200:
                pessoas = res_fallback.json().get("people") or []

        for p in pessoas:
            email = p.get("email")
            linkedin = p.get("linkedin_url")
            
            if not email and p.get("id"):
                url_match = "https://api.apollo.io/v1/people/match"
                try:
                    p_match = requests.post(
                        url_match, 
                        headers=HEADERS_APOLLO, 
                        json={"api_key": APOLLO_API_KEY, "id": p.get("id")}, 
                        timeout=5
                    )
                    if p_match.status_code == 200:
                        det = p_match.json().get("person") or {}
                        email = det.get("email")
                        linkedin = linkedin or det.get("linkedin_url")
                except Exception:
                    pass

            if email and "@" in email:
                org_obj = p.get("organization") or {}
                
                contatos_validos.append({
                    "email": email,
                    "nome": p.get("first_name", ""),
                    "sobrenome": p.get("last_name", ""),
                    "cargo": p.get("title", ""),
                    "linkedin": linkedin or "",
                    "empresa_nome": org_obj.get("name") or str(termo_empresa),
                    "empresa_dominio": org_obj.get("primary_domain") or "",
                })
            
            if len(contatos_validos) >= limite:
                break
                
        status_msg = f"Encontrei {len(contatos_validos)} pessoa(s) de {limite} solicitada(s)."
        return contatos_validos, status_msg, False
            
    except Exception as e:
        return [], f"Falha de conexão com Apollo: {str(e)}", True


# ==========================================
# SERVIDOR FLASK E FRONTEND
# ==========================================
app = Flask(__name__)

def _pedir_login():
    return Response("Acesso restrito.", 401, {"WWW-Authenticate": 'Basic realm="Start RH - Painel BDR"'})

@app.before_request
def exigir_login():
    if APP_USER and APP_PASSWORD:
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
                    Quantidade máxima de contatos por empresa:
                </label>
                <input type="number" id="limiteInput" value="1" min="1" max="50"
                    class="w-32 bg-gray-900 border border-gray-700 rounded-lg p-2 text-gray-100 focus:outline-none focus:border-amber-500 transition font-mono text-sm">
            </div>

            <button id="btnProcessar" onclick="processarEmpresas()" 
                class="w-full bg-amber-500 hover:bg-amber-600 text-gray-950 font-bold py-3 px-6 rounded-lg transition flex items-center justify-center gap-2 shadow-lg shadow-amber-500/20">
                <i class="fa-solid fa-bolt"></i> Iniciar Prospecção
            </button>
        </div>

        <div id="loading" class="hidden my-8 text-center">
            <div class="inline-block animate-spin rounded-full h-10 w-10 border-4 border-amber-500 border-t-transparent"></div>
            <p class="text-gray-400 text-sm mt-3 animate-pulse">Consultando Apollo, criando contatos e tarefas no HubSpot...</p>
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
            const limite = parseInt(document.getElementById('limiteInput').value) || 1;
            
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
                                        ${c.linkedin ? '<br><a href="' + c.linkedin + '" target="_blank" class="text-sky-400 hover:text-sky-300 font-semibold mt-1 inline-block"><i class="fa-brands fa-linkedin"></i> LinkedIn</a>' : ''}
                                    </div>
                                    <div class="text-right">
                                        <span class="text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded"><i class="fa-solid fa-check"></i> Contato & Tarefas Salvos</span>
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
        
        if isinstance(empresas_raw, list):
            empresas_raw = ",".join([str(item) for item in empresas_raw])
        elif not isinstance(empresas_raw, str):
            empresas_raw = str(empresas_raw)
        
        try:
            limite = max(1, int(data.get("limite", 1)))
        except (TypeError, ValueError):
            limite = 1

        lista_empresas = [e.strip() for e in empresas_raw.replace("\n", ",").split(",") if e.strip()]

        resultados = []

        for item in lista_empresas:
            time.sleep(1.5)  # Estabilização para evitar Rate Limits da API na nuvem
            
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

                if contact_id:
                    if company_id:
                        associar_contato_empresa(contact_id, company_id)
                    
                    # Chamadas de disparo de e-mail foram removidas

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
                    "linkedin": c["linkedin"]
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
        print("\n--- ERRO DETECTADO NO BACKEND ---")
        traceback.print_exc()
        print("----------------------------------\n")
        return jsonify({"status": "error", "message": f"Erro de execução no backend: {str(e)}"}), 500

if __name__ == "__main__":
    porta = int(os.getenv("PORT", "5000"))
    print("\n--- SERVIDOR DA START RH INICIADO ---")
    print(f"Ativo na porta: {porta}\n")
    app.run(host="0.0.0.0", port=porta, debug=False)
