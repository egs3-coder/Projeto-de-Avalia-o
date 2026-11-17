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

    p.linha("Métricas de negócio — app-pedidos")
    p.add("timeseries", "Pedidos criados por minuto (por status)",
          [('sum by (status) (rate(pedidos_criados_total[1m])) * 60', "{{status}}")], w=8, unidade="short",
          descricao="Counter pedidos.criados (tag status = aprovado | rejeitado).")
    p.add("timeseries", "Tempo de processamento do pedido",
          [("rate(pedidos_processamento_seconds_sum[5m]) / rate(pedidos_processamento_seconds_count[5m])", "médio"),
           ("histogram_quantile(0.95, sum by (le) (rate(pedidos_processamento_seconds_bucket[5m])))", "p95")], w=8, unidade="s",
          descricao="Timer pedidos.processamento (inclui a chamada ao app-estoque).")
    p.add("stat", "Pedidos em processamento agora", [("sum(pedidos_em_processamento)", "")], w=4, h=8,
          descricao="Gauge pedidos.em.processamento.")
    p.add("stat", "Unidades vendidas (última hora)", [("sum(increase(pedidos_itens_vendidos_total[1h]))", "")], w=4, h=8,
          descricao="Counter pedidos.itens.vendidos.", field={"decimals": 0})

    p.linha("Métricas de negócio — app-estoque")
    p.add("timeseries", "Reservas de estoque por minuto (por resultado)",
          [('sum by (resultado) (rate(estoque_reservas_total[1m])) * 60', "{{resultado}}")], w=8,
          descricao="Counter estoque.reservas (tag resultado = sucesso | insuficiente).")
    p.add("timeseries", "Unidades disponíveis no estoque",
          [("sum(estoque_unidades_disponiveis)", "unidades")], w=8, descricao="Gauge estoque.unidades.disponiveis.")
    p.add("stat", "Produtos abaixo do mínimo", [("sum(estoque_produtos_abaixo_minimo)", "")], w=4, h=8,
          descricao="Gauge estoque.produtos.abaixo.minimo.",
          field={"thresholds": {"mode": "absolute", "steps": [
              {"color": "green", "value": None}, {"color": "orange", "value": 1}, {"color": "red", "value": 3}]}})
    p.add("stat", "Tempo médio de reserva", [("sum(rate(estoque_reserva_tempo_seconds_sum[5m])) / sum(rate(estoque_reserva_tempo_seconds_count[5m]))", "")], w=4, h=8,
          unidade="s", descricao="Timer estoque.reserva.tempo.")

    p.linha("Logs (Loki)")
    p.add("logs", "Logs das aplicações selecionadas",
          [('{application=~"$application"}', "")], w=24, h=12, ds=LOKI,
          opcoes={"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending", "enableLogDetails": True},
          descricao="Clique numa linha e use o link do traceId para abrir o trace no Tempo.")

    return dashboard("pi-aplicacoes", "Projeto Integrador — Aplicações (JVM / HTTP / Negócio)",
                     "Métricas do Spring Boot Actuator/Micrometer das aplicações web Java.",
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
          [('100 - (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs"} * 100)', "{{mountpoint}}")],
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
    p.add("table", "Contêineres em execução",
          [('max by (name, image) (container_last_seen{name!=""})', "")], unidade="dateTimeFromNow",
          opcoes={"showHeader": True})
    p.paineis[-1]["targets"][0].update({"format": "table", "instant": True})

    p.linha("Banco de dados — postgres_exporter")
    p.add("timeseries", "Conexões no PostgreSQL por banco",
          [('sum by (datname) (pg_stat_database_numbackends{datname=~"pedidos|estoque"})', "{{datname}}")], w=12)
    p.add("timeseries", "Transações por segundo",
          [('sum by (datname) (rate(pg_stat_database_xact_commit{datname=~"pedidos|estoque"}[1m]))', "commits {{datname}}")], w=12)

    return dashboard("pi-infraestrutura", "Projeto Integrador — Infraestrutura (Host / Contêineres)",
                     "Node Exporter, cAdvisor e postgres_exporter.", p.paineis,
                     tags=["projeto-integrador", "infraestrutura"])


# ---------------------------------------------------------------------------
# 3) Dashboard de logs e traces (Loki + Tempo)
# ---------------------------------------------------------------------------
def dashboard_logs_traces():
    p = Painel()
    var_app = {
        "name": "application", "label": "Aplicação", "type": "custom",
        "query": "app-pedidos,app-estoque", "includeAll": True, "multi": True,
        "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
        "options": [], "allValue": "app-.*",
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
    p.add("table", "Traces recentes de criação de pedido (app-pedidos -> app-estoque -> banco)",
          [('{resource.service.name="app-pedidos" && name="http post /api/pedidos"}', "")], w=24, h=10, ds=TEMPO)
    p.add("table", "Traces com erro",
          [("{status=error}", "")], w=24, h=10, ds=TEMPO)
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
