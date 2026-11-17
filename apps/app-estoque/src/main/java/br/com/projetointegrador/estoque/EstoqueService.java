package br.com.projetointegrador.estoque;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.observation.annotation.Observed;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Regras de negócio do estoque + métricas de negócio (ponto adicional).
 *
 * Métricas expostas em /actuator/prometheus:
 *  - estoque_reservas_total{resultado="sucesso|insuficiente"}  (Counter)
 *  - estoque_unidades_reservadas_total                          (Counter)
 *  - estoque_reposicoes_total                                   (Counter)
 *  - estoque_reserva_tempo_seconds_*                            (Timer)
 *  - estoque_produtos_abaixo_minimo                             (Gauge)
 *  - estoque_unidades_disponiveis                               (Gauge)
 */
@Service
public class EstoqueService {

    private static final Logger log = LoggerFactory.getLogger(EstoqueService.class);

    private final ProdutoRepository repository;
    private final Counter reservasSucesso;
    private final Counter reservasInsuficientes;
    private final Counter unidadesReservadas;
    private final Counter reposicoes;
    private final Timer tempoReserva;
    private final AtomicLong produtosAbaixoMinimo = new AtomicLong();
    private final AtomicLong unidadesDisponiveis = new AtomicLong();

    public EstoqueService(ProdutoRepository repository, MeterRegistry registry) {
        this.repository = repository;

        this.reservasSucesso = Counter.builder("estoque.reservas")
                .description("Total de pedidos de reserva de estoque, por resultado")
                .tag("resultado", "sucesso")
                .register(registry);
        this.reservasInsuficientes = Counter.builder("estoque.reservas")
                .description("Total de pedidos de reserva de estoque, por resultado")
                .tag("resultado", "insuficiente")
                .register(registry);
        this.unidadesReservadas = Counter.builder("estoque.unidades.reservadas")
                .description("Total de unidades de produto reservadas (baixadas do estoque)")
                .register(registry);
        this.reposicoes = Counter.builder("estoque.reposicoes")
                .description("Total de reposições de estoque realizadas")
                .register(registry);
        this.tempoReserva = Timer.builder("estoque.reserva.tempo")
                .description("Tempo para processar uma reserva de estoque")
                .register(registry);

        // Gauges leem valores em memória (atualizados a cada operação),
        // assim o scrape do Prometheus não gera consultas ao banco.
        Gauge.builder("estoque.produtos.abaixo.minimo", produtosAbaixoMinimo, AtomicLong::get)
                .description("Quantidade de produtos com estoque abaixo do mínimo")
                .register(registry);
        Gauge.builder("estoque.unidades.disponiveis", unidadesDisponiveis, AtomicLong::get)
                .description("Soma das unidades disponíveis de todos os produtos")
                .register(registry);
    }

    /** Popula o banco na primeira execução e inicializa os gauges. */
    @EventListener(ApplicationReadyEvent.class)
    @Transactional
    public void inicializar() {
        if (repository.count() == 0) {
            repository.saveAll(List.of(
                    new Produto("Notebook", 50, 10),
                    new Produto("Mouse", 200, 30),
                    new Produto("Teclado", 120, 20),
                    new Produto("Monitor", 40, 8),
                    new Produto("Headset", 80, 15)));
            log.info("Banco de estoque populado com 5 produtos iniciais");
        }
        atualizarGauges();
    }

    @Observed(name = "estoque.listar", contextualName = "estoque-service#listar")
    @Transactional(readOnly = true)
    public List<Produto> listar() {
        return repository.findAll();
    }

    @Observed(name = "estoque.buscar", contextualName = "estoque-service#buscar")
    @Transactional(readOnly = true)
    public Produto buscar(Long id) {
        return repository.findById(id).orElseThrow(() -> new ProdutoNaoEncontradoException(id));
    }

    @Observed(name = "estoque.reservar", contextualName = "estoque-service#reservar")
    @Transactional
    public Produto reservar(Long id, int quantidade) {
        return tempoReserva.record(() -> {
            Produto produto = buscar(id);
            if (produto.getQuantidade() < quantidade) {
                reservasInsuficientes.increment();
                log.warn("Estoque insuficiente para o produto {} ({}): pedido={}, disponível={}",
                        id, produto.getNome(), quantidade, produto.getQuantidade());
                throw new EstoqueInsuficienteException("Estoque insuficiente para o produto " + id);
            }
            produto.setQuantidade(produto.getQuantidade() - quantidade);
            repository.save(produto);
            reservasSucesso.increment();
            unidadesReservadas.increment(quantidade);
            log.info("Reservadas {} unidade(s) do produto {} ({}); restante={}",
                    quantidade, id, produto.getNome(), produto.getQuantidade());
            atualizarGauges();
            return produto;
        });
    }

    @Observed(name = "estoque.repor", contextualName = "estoque-service#repor")
    @Transactional
    public Produto repor(Long id, int quantidade) {
        Produto produto = buscar(id);
        produto.setQuantidade(produto.getQuantidade() + quantidade);
        repository.save(produto);
        reposicoes.increment();
        log.info("Reposição de {} unidade(s) do produto {} ({}); total={}",
                quantidade, id, produto.getNome(), produto.getQuantidade());
        atualizarGauges();
        return produto;
    }

    private void atualizarGauges() {
        repository.flush();
        produtosAbaixoMinimo.set(repository.contarAbaixoDoMinimo());
        unidadesDisponiveis.set(repository.somarUnidades());
    }
}
