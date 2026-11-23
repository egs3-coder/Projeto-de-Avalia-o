package br.com.hemotrack.observabilidade;

import br.com.hemotrack.model.StatusBolsa;
import br.com.hemotrack.model.StatusRequisicao;
import br.com.hemotrack.model.TipoSanguineo;
import br.com.hemotrack.repository.BolsaRepository;
import br.com.hemotrack.repository.RequisicaoRepository;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import java.time.LocalDate;
import java.util.EnumMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * Gauges de negocio (ponto adicional): fotografia do estoque e das requisicoes.
 * Os valores ficam em memoria e sao atualizados a cada 15 s; assim o scrape do Prometheus
 * nunca dispara consultas ao banco.
 *
 *  - hemotrack_estoque_bolsas_disponiveis{tipo_sanguineo}   bolsas disponiveis e dentro da validade
 *  - hemotrack_estoque_bolsas_vencendo                      bolsas disponiveis que vencem em ate 7 dias
 *  - hemotrack_requisicoes_por_status{status}               requisicoes em cada etapa do fluxo
 */
@Component
public class MetricasEstoque {

    private final BolsaRepository bolsaRepository;
    private final RequisicaoRepository requisicaoRepository;
    private final Map<TipoSanguineo, AtomicLong> disponiveisPorTipo = new EnumMap<>(TipoSanguineo.class);
    private final Map<StatusRequisicao, AtomicLong> requisicoesPorStatus = new EnumMap<>(StatusRequisicao.class);
    private final AtomicLong vencendo = new AtomicLong();

    public MetricasEstoque(BolsaRepository bolsaRepository, RequisicaoRepository requisicaoRepository,
                           MeterRegistry registry) {
        this.bolsaRepository = bolsaRepository;
        this.requisicaoRepository = requisicaoRepository;

        for (TipoSanguineo tipo : TipoSanguineo.values()) {
            AtomicLong valor = new AtomicLong();
            disponiveisPorTipo.put(tipo, valor);
            Gauge.builder("hemotrack.estoque.bolsas.disponiveis", valor, AtomicLong::get)
                    .description("Bolsas disponiveis e dentro da validade, por tipo sanguineo")
                    .tag("tipo_sanguineo", tipo.name())
                    .register(registry);
        }
        for (StatusRequisicao status : StatusRequisicao.values()) {
            AtomicLong valor = new AtomicLong();
            requisicoesPorStatus.put(status, valor);
            Gauge.builder("hemotrack.requisicoes.por.status", valor, AtomicLong::get)
                    .description("Quantidade de requisicoes em cada status do fluxo")
                    .tag("status", status.name())
                    .register(registry);
        }
        Gauge.builder("hemotrack.estoque.bolsas.vencendo", vencendo, AtomicLong::get)
                .description("Bolsas disponiveis que vencem nos proximos 7 dias (risco de descarte)")
                .register(registry);
    }

    @Scheduled(initialDelay = 5_000, fixedDelay = 15_000)
    public void atualizar() {
        LocalDate hoje = LocalDate.now();
        for (Map.Entry<TipoSanguineo, AtomicLong> item : disponiveisPorTipo.entrySet()) {
            item.getValue().set(bolsaRepository.countByStatusAndTipoSanguineoAndDataValidadeGreaterThanEqual(
                    StatusBolsa.DISPONIVEL, item.getKey(), hoje));
        }
        for (Map.Entry<StatusRequisicao, AtomicLong> item : requisicoesPorStatus.entrySet()) {
            item.getValue().set(requisicaoRepository.countByStatus(item.getKey()));
        }
        vencendo.set(bolsaRepository.countByStatusAndDataValidadeBetween(StatusBolsa.DISPONIVEL, hoje, hoje.plusDays(7)));
    }
}
