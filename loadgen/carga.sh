#!/bin/sh
# Gerador de carga simples (R7 / seção 8): gera métricas, logs e traces o tempo todo.
#  - cria pedidos (sucesso e, às vezes, rejeição por falta de estoque)
#  - consulta pedidos e produtos
#  - a cada 10 ciclos chama os endpoints de erro (HTTP 500) e um produto inexistente (404)
#  - a cada 25 ciclos repõe o estoque de todos os produtos
PEDIDOS_URL=${PEDIDOS_URL:-http://app-pedidos:8080}
ESTOQUE_URL=${ESTOQUE_URL:-http://app-estoque:8080}
INTERVALO=${INTERVALO:-1}

# número aleatório 0..65535 (não depende do $RANDOM do shell)
aleatorio() { od -An -N2 -tu2 /dev/urandom | tr -d ' '; }

echo "Gerador de carga iniciado: $PEDIDOS_URL e $ESTOQUE_URL (intervalo ${INTERVALO}s)"
i=0
while true; do
  i=$((i + 1))
  produto=$(( $(aleatorio) % 5 + 1 ))
  quantidade=$(( $(aleatorio) % 5 + 1 ))

  curl -s -o /dev/null -X POST "$PEDIDOS_URL/api/pedidos" \
       -H "Content-Type: application/json" \
       -d "{\"produtoId\": $produto, \"quantidade\": $quantidade}"
  curl -s -o /dev/null "$PEDIDOS_URL/api/pedidos"
  curl -s -o /dev/null "$ESTOQUE_URL/api/produtos"
  curl -s -o /dev/null "$ESTOQUE_URL/api/produtos/$produto"

  if [ $((i % 10)) -eq 0 ]; then
    curl -s -o /dev/null "$PEDIDOS_URL/api/pedidos/erro"
    curl -s -o /dev/null "$ESTOQUE_URL/api/produtos/erro"
    curl -s -o /dev/null -X POST "$PEDIDOS_URL/api/pedidos" \
         -H "Content-Type: application/json" -d '{"produtoId": 999, "quantidade": 1}'
  fi

  if [ $((i % 25)) -eq 0 ]; then
    for p in 1 2 3 4 5; do
      curl -s -o /dev/null -X POST "$ESTOQUE_URL/api/produtos/$p/repor?quantidade=$(( $(aleatorio) % 20 + 5 ))"
    done
  fi

  sleep "$INTERVALO"
done
