#!/usr/bin/env python3
"""Gera os JSON dos dashboards do Grafana em grafana/dashboards/.

Uso:  python3 scripts/gerar_dashboards.py

Os dashboards também podem ser editados no próprio Grafana e exportados
(Share -> Export -> Save to file) para a mesma pasta.
"""
import json
from pathlib import Path

DESTINO = Path(__file__).resolve().parent.parent / "grafana" / "dashboards"

PROM = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}
TEMPO = {"type": "tempo", "uid": "tempo"}


class Painel:
    def __init__(self):
        self.id = 0
        self.y = 0
        self.x = 0
        self.altura_linha = 0
        self.paineis = []

    def _pos(self, w, h):
        if self.x + w > 24:
            self.x = 0
            self.y += self.altura_linha
            self.altura_linha = 0
        pos = {"x": self.x, "y": self.y, "w": w, "h": h}
        self.x += w
        self.altura_linha = max(self.altura_linha, h)
        return pos

    def linha(self, titulo):
        if self.x:
            self.y += self.altura_linha
        self.x, self.altura_linha = 0, 0
        self.id += 1
        self.paineis.append({
            "id": self.id, "type": "row", "title": titulo, "collapsed": False,
            "gridPos": {"x": 0, "y": self.y, "w": 24, "h": 1}, "panels": [],
        })
        self.y += 1

    def add(self, tipo, titulo, alvos, w=12, h=8, unidade=None, descricao="",
            ds=PROM, opcoes=None, field=None):
        self.id += 1
        p = {
            "id": self.id, "type": tipo, "title": titulo, "description": descricao,
            "datasource": ds, "gridPos": self._pos(w, h), "targets": [],
            "fieldConfig": {"defaults": {}, "overrides": []}, "options": opcoes or {},
        }
        for i, a in enumerate(alvos):
            expr, legenda = (a if isinstance(a, tuple) else (a, ""))
            alvo = {"refId": chr(65 + i), "datasource": ds}
            if ds is TEMPO:
                alvo.update({"queryType": "traceql", "query": expr, "limit": 20,
                             "tableType": "traces"})
            else:
                alvo.update({"expr": expr, "legendFormat": legenda or "__auto"})
                if ds is PROM and tipo != "stat":
                    alvo["exemplar"] = True
            p["targets"].append(alvo)
        d = p["fieldConfig"]["defaults"]
        if unidade:
            d["unit"] = unidade
        if tipo == "timeseries":
            d["custom"] = {"drawStyle": "line", "lineWidth": 2, "fillOpacity": 12,
                           "showPoints": "never", "spanNulls": True}
            p["options"].setdefault("legend", {"displayMode": "list", "placement": "bottom", "showLegend": True})
            p["options"].setdefault("tooltip", {"mode": "multi", "sort": "desc"})
        if tipo == "stat":
            p["options"].setdefault("reduceOptions", {"calcs": ["lastNotNull"], "fields": "", "values": False})
            p["options"].setdefault("colorMode", "value")
            p["options"].setdefault("graphMode", "area")
        if field:
            d.update(field)
        self.paineis.append(p)
        return p


def dashboard(uid, titulo, descricao, paineis, variaveis=None, tags=None):
    return {
        "uid": uid, "title": titulo, "description": descricao,
        "tags": tags or [], "timezone": "browser", "editable": True,
        "graphTooltip": 1, "refresh": "10s", "schemaVersion": 39, "version": 1,
        "time": {"from": "now-30m", "to": "now"},
        "templating": {"list": variaveis or []},
        "annotations": {"list": []},
        "links": [{"title": "Dashboards", "type": "dashboards", "tags": ["projeto-integrador"],
                   "asDropdown": True, "includeVars": False, "keepTime": True}],
        "panels": paineis,
    }


def var_query(nome, rotulo, query, multi=True):
    return {
        "name": nome, "label": rotulo, "type": "query", "datasource": PROM,
        "query": {"query": query, "refId": "var"}, "definition": query,
        "refresh": 2, "includeAll": True, "multi": multi, "sort": 1,
        "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
    }


LIMIARES_ERRO = {"thresholds": {"mode": "absolute", "steps": [
    {"color": "green", "value": None}, {"color": "orange", "value": 1}, {"color": "red", "value": 5}]}}


# ---------------------------------------------------------------------------
# 1) Dashboard de aplicação (JVM / HTTP / HikariCP / negócio / logs)
# ---------------------------------------------------------------------------
def dashboard_aplicacoes():
    p = Painel()
    A = 'application=~"$application"'

    p.linha("Visão geral")
    p.add("stat", "Uptime", [(f"process_uptime_seconds{{{A}}}", "{{application}}")], w=6, h=4, unidade="s")
    p.add("stat", "Requisições/s", [(f"sum by (application) (rate(http_server_requests_seconds_count{{{A}}}[1m]))", "{{application}}")], w=6, h=4, unidade="reqps")
    p.add("stat", "Latência p95", [(f"histogram_quantile(0.95, sum by (le, application) (rate(http_server_requests_seconds_bucket{{{A}}}[5m])))", "{{application}}")], w=6, h=4, unidade="s")
    p.add("stat", "% de erros 5xx", [(f'100 * sum by (application) (rate(http_server_requests_seconds_count{{{A}, status=~"5.."}}[5m])) / sum by (application) (rate(http_server_requests_seconds_count{{{A}}}[5m]))', "{{application}}")], w=6, h=4, unidade="percent", field=LIMIARES_ERRO)

    p.linha("HTTP")
    p.add("timeseries", "Requisições por segundo, por rota",
          [(f'sum by (application, uri) (rate(http_server_requests_seconds_count{{{A}, uri!~"/actuator.*"}}[1m]))', "{{application}} {{uri}}")], unidade="reqps")
    p.add("timeseries", "Latência p95 / p99",
          [(f"histogram_quantile(0.95, sum by (le, application) (rate(http_server_requests_seconds_bucket{{{A}}}[5m])))", "p95 {{application}}"),
           (f"histogram_quantile(0.99, sum by (le, application) (rate(http_server_requests_seconds_bucket{{{A}}}[5m])))", "p99 {{application}}")],
          unidade="s", descricao="Os pontos (exemplars) abrem o trace correspondente no Tempo.")
    p.add("timeseries", "Taxa de erros 5xx",
          [(f'sum by (application, uri) (rate(http_server_requests_seconds_count{{{A}, status=~"5.."}}[5m]))', "{{application}} {{uri}}")], unidade="reqps")
    p.add("timeseries", "Respostas por status HTTP",
          [(f"sum by (application, status) (rate(http_server_requests_seconds_count{{{A}}}[1m]))", "{{application}} {{status}}")], unidade="reqps")

    p.linha("JVM")
    p.add("timeseries", "Heap em uso x máximo",
          [(f'sum by (application) (jvm_memory_used_bytes{{{A}, area="heap"}})', "usado {{application}}"),
           (f'sum by (application) (jvm_memory_max_bytes{{{A}, area="heap"}})', "máximo {{application}}")], w=8, unidade="bytes")
    p.add("timeseries", "Non-heap em uso",
          [(f'sum by (application) (jvm_memory_used_bytes{{{A}, area="nonheap"}})', "{{application}}")], w=8, unidade="bytes")
    p.add("timeseries", "Threads",
          [(f"jvm_threads_live_threads{{{A}}}", "vivas {{application}}"),
           (f"jvm_threads_daemon_threads{{{A}}}", "daemon {{application}}")], w=8)
    p.add("timeseries", "Pausas de GC (tempo por segundo)",
          [(f"sum by (application, gc) (rate(jvm_gc_pause_seconds_sum{{{A}}}[1m]))", "{{application}} {{gc}}")], w=8, unidade="s")
    p.add("timeseries", "CPU do processo x sistema",
          [(f"process_cpu_usage{{{A}}}", "processo {{application}}"),
           (f"system_cpu_usage{{{A}}}", "sistema {{application}}")], w=8, unidade="percentunit")
    p.add("timeseries", "Classes carregadas",
          [(f"jvm_classes_loaded_classes{{{A}}}", "{{application}}")], w=8)

    p.linha("Banco de dados — pool HikariCP")
    p.add("timeseries", "Conexões do pool",
          [(f"hikaricp_connections_active{{{A}}}", "ativas {{application}}"),
           (f"hikaricp_connections_idle{{{A}}}", "ociosas {{application}}"),
           (f"hikaricp_connections_pending{{{A}}}", "aguardando {{application}}"),
           (f"hikaricp_connections_max{{{A}}}", "máximo {{application}}")], w=12)
    p.add("timeseries", "Tempo médio para obter conexão",
          [(f"rate(hikaricp_connections_acquire_seconds_sum{{{A}}}[5m]) / rate(hikaricp_connections_acquire_seconds_count{{{A}}}[5m])", "{{application}}")], w=12, unidade="s")

    p.linha("Métricas de negócio — HemoTrack: requisições e alocação (US01 / US04)")
    p.add("timeseries", "Requisições criadas por minuto (por urgência)",
          [('sum by (urgencia) (rate(hemotrack_requisicoes_criadas_total[5m])) * 60', "{{urgencia}}")], w=8,
          descricao="Counter hemotrack.requisicoes.criadas (tag urgencia = ROTINA | URGENTE | EMERGENCIA).")
    p.add("timeseries", "Requisições por status do fluxo",
          [('sum by (status) (hemotrack_requisicoes_por_status)', "{{status}}")], w=8,
          descricao="Gauge hemotrack.requisicoes.por.status (PENDENTE, ALOCADA, EM_TRANSPORTE, ENTREGUE).")
    p.add("timeseries", "Tempo de alocação de bolsas (FEFO)",
          [('sum(rate(hemotrack_alocacao_tempo_seconds_sum[5m])) / sum(rate(hemotrack_alocacao_tempo_seconds_count[5m]))', "médio"),
           ('histogram_quantile(0.95, sum by (le) (rate(hemotrack_alocacao_tempo_seconds_bucket[5m])))', "p95")], w=8, unidade="s",
          descricao="Timer hemotrack.alocacao.tempo: tempo de RequisicaoService.alocar (reserva FEFO).")
    p.add("timeseries", "Resultado das alocações por minuto",
          [('sum by (resultado) (rate(hemotrack_alocacao_tempo_seconds_count[5m])) * 60', "{{resultado}}")], w=8,
          descricao="alocada = bolsas reservadas; sem_estoque_ou_invalida = não havia bolsas compatíveis.")
    p.add("stat", "Requisições recusadas (última hora)", [("sum(increase(hemotrack_requisicoes_recusadas_total[1h]))", "")], w=4, h=8,
          descricao="Counter hemotrack.requisicoes.recusadas: pedidos com dados inválidos.", field={"decimals": 0, "color": {"mode": "fixed", "fixedColor": "orange"}})
    p.add("stat", "Requisições criadas (última hora)", [("sum(increase(hemotrack_requisicoes_criadas_total[1h]))", "")], w=4, h=8,
          field={"decimals": 0, "color": {"mode": "fixed", "fixedColor": "green"}})
    p.add("timeseries", "Entradas na plataforma (por resultado)",
          [('sum by (resultado) (increase(hemotrack_logins_total[5m]))', "{{resultado}}")], w=8,
          descricao="Counter hemotrack.logins (tag resultado = sucesso | falha).")

    p.linha("Métricas de negócio — HemoTrack: estoque e telemetria (US03 / US06 / US10)")
    p.add("bargauge", "Estoque disponível por tipo sanguíneo",
          [('sum by (tipo_sanguineo) (hemotrack_estoque_bolsas_disponiveis)', "{{tipo_sanguineo}}")], w=8, h=9,
          opcoes={"orientation": "horizontal", "displayMode": "gradient", "showUnfilled": True,
                  "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}},
          descricao="Gauge hemotrack.estoque.bolsas.disponiveis: bolsas disponíveis e dentro da validade.",
          field={"color": {"mode": "continuous-RdYlGr"}, "min": 0})
    p.add("timeseries", "Bolsas cadastradas por minuto (por tipo)",
          [('sum by (tipo_sanguineo) (rate(hemotrack_bolsas_cadastradas_total[5m])) * 60', "{{tipo_sanguineo}}")], w=8, h=9,
          descricao="Counter hemotrack.bolsas.cadastradas (entrada de bolsas no estoque).")
    p.add("timeseries", "Leituras de temperatura por minuto (por faixa)",
          [('sum by (faixa) (rate(hemotrack_telemetria_leituras_total[5m])) * 60', "{{faixa}}")], w=5, h=9,
          descricao="Counter hemotrack.telemetria.leituras (faixa = normal | fora da faixa segura).")
    p.add("stat", "Bolsas vencendo em 7 dias", [("sum(hemotrack_estoque_bolsas_vencendo)", "")], w=3, h=9,
          descricao="Gauge hemotrack.estoque.bolsas.vencendo (risco de descarte).",
          field={"decimals": 0, "thresholds": {"mode": "absolute", "steps": [
              {"color": "green", "value": None}, {"color": "orange", "value": 5}, {"color": "red", "value": 15}]}})

    p.linha("Logs (Loki)")
    p.add("logs", "Logs das aplicações selecionadas",
          [('{application=~"$application"}', "")], w=24, h=12, ds=LOKI,
          opcoes={"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending", "enableLogDetails": True},
          descricao="Clique numa linha e use o link do traceId para abrir o trace no Tempo.")

    return dashboard("pi-aplicacoes", "Projeto Integrador — HemoTrack (JVM / HTTP / Negócio)",
                     "Métricas do Spring Boot Actuator/Micrometer do HemoTrack.",
                     p.paineis, [var_query("application", "Aplicação", "label_values(process_uptime_seconds, application)")],
                     tags=["projeto-integrador", "aplicacao"])


# ---------------------------------------------------------------------------
# 2) Dashboard de infraestrutura (host + contêineres)
# ---------------------------------------------------------------------------
def dashboard_infra():
    p = Painel()
    p.linha("Saúde da coleta")
    p.add("stat", "Targets UP", [("sum(up)", "")], w=6, h=4, descricao="Quantidade de alvos do Prometheus em estado UP.")
    p.add("stat", "Targets DOWN", [("count(up == 0) or vector(0)", "")], w=6, h=4,
          field={"thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "red", "value": 1}]}})
    p.add("stat", "Uptime do host", [("time() - node_boot_time_seconds", "")], w=6, h=4, unidade="s")
    p.add("stat", "Núcleos de CPU", [('count(count by (cpu) (node_cpu_seconds_total{mode="idle"}))', "")], w=6, h=4)

    p.linha("Host — Node Exporter")
    p.add("timeseries", "CPU do host (%)",
          [('100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)', "uso total"),
           ('avg by (mode) (rate(node_cpu_seconds_total{mode=~"user|system|iowait"}[5m])) * 100', "{{mode}}")],
          w=8, unidade="percent", field={"min": 0, "max": 100})
    p.add("timeseries", "Load average",
          [("node_load1", "1 min"), ("node_load5", "5 min"), ("node_load15", "15 min")], w=8)
    p.add("timeseries", "Memória do host",
          [("node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes", "em uso"),
           ("node_memory_MemAvailable_bytes", "disponível"),
           ("node_memory_MemTotal_bytes", "total")], w=8, unidade="bytes")
    p.add("timeseries", "Uso de disco (%)",
          [('max by (device) (100 - (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs|nsfs|ramfs"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs|nsfs|ramfs"} * 100))', "{{device}}")],
          w=8, unidade="percent", field={"min": 0, "max": 100})
    p.add("timeseries", "Disco — leitura e escrita",
          [("sum(rate(node_disk_read_bytes_total[5m]))", "leitura"),
           ("sum(rate(node_disk_written_bytes_total[5m]))", "escrita")], w=8, unidade="Bps")
    p.add("timeseries", "Rede — recebido e enviado",
          [('sum(rate(node_network_receive_bytes_total{device!~"lo|veth.*|docker.*|br-.*"}[5m]))', "recebido"),
           ('sum(rate(node_network_transmit_bytes_total{device!~"lo|veth.*|docker.*|br-.*"}[5m]))', "enviado")], w=8, unidade="Bps")

    p.linha("Contêineres — cAdvisor")
    p.add("timeseries", "CPU por contêiner",
          [('sum by (name) (rate(container_cpu_usage_seconds_total{name!=""}[1m]))', "{{name}}")], unidade="percentunit",
          descricao="1,0 = 1 núcleo de CPU inteiro.")
    p.add("timeseries", "Memória por contêiner",
          [('sum by (name) (container_memory_working_set_bytes{name!=""})', "{{name}}")], unidade="bytes")
    p.add("timeseries", "Rede por contêiner (recebido)",
          [('sum by (name) (rate(container_network_receive_bytes_total{name!=""}[1m]))', "{{name}}")], unidade="Bps")
    p.add("bargauge", "Contêineres em execução (tempo no ar)",
          [('max by (name) (time() - container_start_time_seconds{name!=""})', "{{name}}")], unidade="s",
          opcoes={"orientation": "horizontal", "displayMode": "basic", "showUnfilled": True,
                  "valueMode": "color", "namePlacement": "left",
                  "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}},
          field={"color": {"mode": "fixed", "fixedColor": "green"}})

    return dashboard("pi-infraestrutura", "Projeto Integrador — Infraestrutura (Host / Contêineres)",
                     "Node Exporter e cAdvisor.", p.paineis,
                     tags=["projeto-integrador", "infraestrutura"])


# ---------------------------------------------------------------------------
# 3) Dashboard de logs e traces (Loki + Tempo)
# ---------------------------------------------------------------------------
def dashboard_logs_traces():
    p = Painel()
    var_app = {
        "name": "application", "label": "Aplicação", "type": "custom",
        "query": "hemotrack", "includeAll": True, "multi": True,
        "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
        "options": [], "allValue": "hemotrack",
    }
    p.linha("Logs (Loki)")
    p.add("timeseries", "Volume de logs por nível",
          [('sum by (application, level) (count_over_time({application=~"$application"} [1m]))', "{{application}} {{level}}")],
          w=12, ds=LOKI)
    p.add("timeseries", "Erros e avisos por minuto",
          [('sum by (application, level) (count_over_time({application=~"$application", level=~"ERROR|WARN"} [1m]))', "{{application}} {{level}}")],
          w=12, ds=LOKI)
    p.add("logs", "Logs de erro (ERROR)",
          [('{application=~"$application", level="ERROR"}', "")], w=24, h=10, ds=LOKI,
          opcoes={"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending", "enableLogDetails": True})
    p.add("logs", "Todos os logs — clique na linha e use o link do traceId",
          [('{application=~"$application"} != "traceId= "', "")], w=24, h=12, ds=LOKI,
          opcoes={"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending", "enableLogDetails": True})

    p.linha("Traces (Tempo)")
    p.add("table", "Traces recentes de criação de requisição (HTTP -> RequisicaoService -> banco H2)",
          [('{resource.service.name="hemotrack" && name="http post /requisicoes"}', "")], w=24, h=10, ds=TEMPO)
    p.add("table", "Traces com erro",
          [('{resource.service.name="hemotrack" && status=error}', "")], w=24, h=10, ds=TEMPO)
    p.add("nodeGraph", "Mapa de serviços (gerado pelo Tempo)",
          [("", "")], w=24, h=12, ds=TEMPO)
    p.paineis[-1]["targets"][0] = {"refId": "A", "datasource": TEMPO, "queryType": "serviceMap"}

    return dashboard("pi-logs-traces", "Projeto Integrador — Logs (Loki) e Traces (Tempo)",
                     "Logs centralizados e traces distribuídos, correlacionados pelo traceId.",
                     p.paineis, [var_app], tags=["projeto-integrador", "logs", "traces"])


if __name__ == "__main__":
    DESTINO.mkdir(parents=True, exist_ok=True)
    for nome, fn in [("aplicacoes.json", dashboard_aplicacoes),
                     ("infraestrutura.json", dashboard_infra),
                     ("logs-e-traces.json", dashboard_logs_traces)]:
        (DESTINO / nome).write_text(json.dumps(fn(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("gerado:", DESTINO / nome)
