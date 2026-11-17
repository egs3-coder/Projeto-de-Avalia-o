package br.com.projetointegrador.pedidos;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.observation.annotation.Observed;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Regras de negócio de pedidos + métricas de negócio (ponto adicional).
 *
 * Métricas expostas em /actuator/prometheus:
 *  - pedidos_criados_total{status="aprovado|rejeitado"}   (Counter)
 *  - pedidos_itens_vendidos_total                         (Counter)
 *  - pedidos_processamento_seconds_*                      (Timer, com histograma p95/p99)
 *  - pedidos_em_processamento                             (Gauge)
 *
 * Fluxo com vários spans: HTTP POST /api/pedidos -> PedidoService#criar
 *   -> HTTP POST app-estoque /api/produtos/{id}/reservar -> EstoqueService#reservar -> JDBC
 *   -> INSERT do pedido (JDBC)
 */
@Service
public class PedidoService {

    private static final Logger log = LoggerFactory.getLogger(PedidoService.class);

    private final PedidoRepository repository;
    private final RestClient estoqueClient;
    private final Counter pedidosAprovados;
    private final Counter pedidosRejeitados;
    private final Counter itensVendidos;
    private final Timer tempoProcessamento;
    private final AtomicInteger emProcessamento = new AtomicInteger();

    public PedidoService(PedidoRepository repository, RestClient estoqueClient, MeterRegistry registry) {
        this.repository = repository;
        this.estoqueClient = estoqueClient;

        this.pedidosAprovados = Counter.builder("pedidos.criados")
                .description("Total de pedidos criados, por status")
                .tag("status", "aprovado")
                .register(registry);
        this.pedidosRejeitados = Counter.builder("pedidos.criados")
                .description("Total de pedidos criados, por status")
                .tag("status", "rejeitado")
                .register(registry);
        this.itensVendidos = Counter.builder("pedidos.itens.vendidos")
                .description("Total de unidades vendidas em pedidos aprovados")
                .register(registry);
        this.tempoProcessamento = Timer.builder("pedidos.processamento")
                .description("Tempo de processamento de um pedido (inclui reserva no estoque)")
                .register(registry);
        Gauge.builder("pedidos.em.processamento", emProcessamento, AtomicInteger::get)
                .description("Pedidos sendo processados neste momento")
                .register(registry);
    }

    @Observed(name = "pedidos.criar", contextualName = "pedido-service#criar")
    public Pedido criar(NovoPedido novo) {
        if (novo.produtoId() == null || novo.quantidade() <= 0) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "produtoId e quantidade > 0 são obrigatórios");
        }
        emProcessamento.incrementAndGet();
        try {
            return tempoProcessamento.record(() -> processar(novo));
        } finally {
            emProcessamento.decrementAndGet();
        }
    }

    private Pedido processar(NovoPedido novo) {
        log.info("Processando pedido: produto={}, quantidade={}", novo.produtoId(), novo.quantidade());
        try {
            estoqueClient.post()
                    .uri("/api/produtos/{id}/reservar?quantidade={q}", novo.produtoId(), novo.quantidade())
                    .retrieve()
                    .toBodilessEntity();
        } catch (HttpClientErrorException.Conflict e) {
            Pedido rejeitado = repository.save(new Pedido(novo.produtoId(), novo.quantidade(), Pedido.Status.REJEITADO));
            pedidosRejeitados.increment();
            log.warn("Pedido {} rejeitado: estoque insuficiente para o produto {}", rejeitado.getId(), novo.produtoId());
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Estoque insuficiente (pedido " + rejeitado.getId() + " rejeitado)");
        } catch (HttpClientErrorException.NotFound e) {
            log.warn("Produto {} não existe no estoque", novo.produtoId());
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Produto não encontrado");
        } catch (RestClientException e) {
            log.error("Falha ao comunicar com o app-estoque: {}", e.getMessage(), e);
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "app-estoque indisponível");
        }

        Pedido aprovado = repository.save(new Pedido(novo.produtoId(), novo.quantidade(), Pedido.Status.APROVADO));
        pedidosAprovados.increment();
        itensVendidos.increment(novo.quantidade());
        log.info("Pedido {} aprovado: produto={}, quantidade={}", aprovado.getId(), novo.produtoId(), novo.quantidade());
        return aprovado;
    }

    @Observed(name = "pedidos.listar", contextualName = "pedido-service#listar")
    public List<Pedido> listarRecentes() {
        return repository.findTop50ByOrderByIdDesc();
    }

    @Observed(name = "pedidos.buscar", contextualName = "pedido-service#buscar")
    public Pedido buscar(Long id) {
        return repository.findById(id).orElseThrow(() -> new PedidoNaoEncontradoException(id));
    }
}
