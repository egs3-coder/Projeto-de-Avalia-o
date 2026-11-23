package br.com.hemotrack.observabilidade;

import io.micrometer.observation.ObservationPredicate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.server.observation.ServerRequestObservationContext;

/**
 * Ajustes de observabilidade (Projeto de Avaliacao - Infraestrutura de Comunicacao).
 * Evita traces sem valor no Tempo, mantendo so os que comecam numa requisicao HTTP.
 */
@Configuration
public class ObservabilidadeConfig {

    @Bean
    ObservationPredicate filtrarObservacoesSemValor() {
        return (nome, contexto) -> {
            // Chamadas do Prometheus em /actuator/** (scrape a cada 15 s)
            if (contexto instanceof ServerRequestObservationContext servidor) {
                return !servidor.getCarrier().getRequestURI().startsWith("/actuator");
            }
            // Tarefas agendadas (atualizacao dos gauges e rotina de validade)
            if ("tasks.scheduled.execution".equals(nome)) {
                return false;
            }
            // Consultas JDBC "soltas", fora de uma requisicao (inicializacao, tarefas agendadas)
            if (nome.startsWith("jdbc") && contexto.getParentObservation() == null) {
                return false;
            }
            return true;
        };
    }
}
