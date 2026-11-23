#!/bin/sh
# Gerador de carga do HemoTrack: gera metricas, logs e traces o tempo todo.
#  - entra no sistema como "operador" (sessao com cookie)
#  - navega pelas telas (inicio, estoque, requisicoes, hospitais, painel, demanda)
#  - cria requisicoes de hemocomponentes e tenta alocar bolsas (FEFO)
#  - cadastra bolsas novas para repor o estoque
#  - envia leituras de temperatura do sensor (API /api), as vezes fora da faixa segura
#  - a cada 10 ciclos: erro 500 de teste, requisicao inexistente (404),
#    requisicao invalida (recusada) e login com senha errada
URL=${HEMOTRACK_URL:-http://hemotrack:8080}
INTERVALO=${INTERVALO:-2}
COOKIES=/tmp/cookies.txt

aleatorio() { od -An -N2 -tu2 /dev/urandom | tr -d ' '; }
escolher() { shift $(( $(aleatorio) % $# )); echo "$1"; }

entrar() {
  rm -f "$COOKIES"
  curl -s -o /dev/null -c "$COOKIES" -b "$COOKIES" -X POST "$URL/login" \
       --data-urlencode "login=operador" --data-urlencode "senha=hemotrack123"
}

echo "Gerador de carga iniciado: $URL (intervalo ${INTERVALO}s)"
entrar
i=0
while true; do
  i=$((i + 1))

  # Sessao expirada? Entra de novo.
  destino=$(curl -s -o /dev/null -w '%{redirect_url}' -b "$COOKIES" "$URL/")
  case "$destino" in *"/login"*) entrar ;; esac

  # Telas
  for tela in / /bolsas /requisicoes /hospitais /dashboard /demanda; do
    curl -s -o /dev/null -b "$COOKIES" "$URL$tela"
  done

  # US01 + US04: nova requisicao e alocacao das bolsas
  tipo=$(escolher O_NEG O_POS A_POS A_NEG B_POS AB_POS O_POS A_POS)
  urgencia=$(escolher ROTINA ROTINA URGENTE EMERGENCIA)
  hospital=$(escolher 1 2)
  quantidade=$(( $(aleatorio) % 3 + 1 ))
  local_req=$(curl -s -o /dev/null -w '%{redirect_url}' -b "$COOKIES" -X POST "$URL/requisicoes" \
       -d "hospitalId=$hospital&hemocomponente=CONCENTRADO_HEMACIAS&tipoSanguineo=$tipo&quantidade=$quantidade&urgencia=$urgencia")
  id=$(echo "$local_req" | sed -n 's#.*/requisicoes/\([0-9][0-9]*\).*#\1#p')
  if [ -n "$id" ]; then
    curl -s -o /dev/null -b "$COOKIES" "$URL/requisicoes/$id"
    curl -s -o /dev/null -b "$COOKIES" -X POST -H "Referer: $URL/requisicoes/$id" "$URL/requisicoes/$id/alocar"
  fi

  # US03: entrada de bolsas no estoque (a cada 2 ciclos)
  if [ $((i % 2)) -eq 0 ]; then
    hoje=$(date +%F)
    validade=$(date -d "@$(( $(date +%s) + (20 + $(aleatorio) % 25) * 86400 ))" +%F)
    codigo="CARGA-$(date +%s)-$i"
    curl -s -o /dev/null -b "$COOKIES" -X POST "$URL/bolsas" \
         -d "codigo=$codigo&hemocomponente=CONCENTRADO_HEMACIAS&tipoSanguineo=$(escolher O_NEG O_POS A_POS A_NEG B_POS AB_POS)&dataColeta=$hoje&dataValidade=$validade"
  fi

  # US06: leitura do sensor de temperatura (faixa segura das hemacias: 2 a 6 C)
  if [ $(( $(aleatorio) % 8 )) -eq 0 ]; then temp="8.$(( $(aleatorio) % 9 ))"; else temp="$(( $(aleatorio) % 4 + 2 )).$(( $(aleatorio) % 9 ))"; fi
  curl -s -o /dev/null -X POST "$URL/api/requisicoes/REQ-0001/leituras" \
       -H "Content-Type: application/json" -d "{\"temperatura\": $temp}"

  # Casos de erro
  if [ $((i % 10)) -eq 0 ]; then
    curl -s -o /dev/null "$URL/api/teste/erro"
    curl -s -o /dev/null "$URL/api/requisicoes/REQ-9999/leituras"
    curl -s -o /dev/null -b "$COOKIES" -X POST "$URL/requisicoes" -d "hospitalId=1&quantidade=50"
    curl -s -o /dev/null -X POST "$URL/login" --data-urlencode "login=operador" --data-urlencode "senha=errada"
  fi

  sleep "$INTERVALO"
done
