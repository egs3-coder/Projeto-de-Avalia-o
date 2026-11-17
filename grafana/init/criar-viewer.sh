#!/bin/sh
# Cria o usuário de leitura (papel Viewer) do professor no Grafana.
# Roda uma vez a cada "docker compose up"; se o usuário já existir, apenas avisa.
set -u

echo "Aguardando o Grafana em $GRAFANA_URL ..."
until curl -sf "$GRAFANA_URL/api/health" > /dev/null; do sleep 2; done

payload=$(printf '{"name":"Professor","login":"%s","email":"%s@localhost","password":"%s","OrgId":1}' \
  "$GRAFANA_VIEWER_USER" "$GRAFANA_VIEWER_USER" "$GRAFANA_VIEWER_PASSWORD")

status=$(curl -s -o /tmp/resp.json -w '%{http_code}' \
  -u "$GRAFANA_ADMIN_USER:$GRAFANA_ADMIN_PASSWORD" \
  -H "Content-Type: application/json" \
  -X POST "$GRAFANA_URL/api/admin/users" -d "$payload")

case "$status" in
  200) echo "Usuário '$GRAFANA_VIEWER_USER' criado com papel Viewer." ;;
  412) echo "Usuário '$GRAFANA_VIEWER_USER' já existe — nada a fazer." ;;
  *)   echo "Falha ao criar o usuário (HTTP $status):"; cat /tmp/resp.json; echo; exit 1 ;;
esac
